#!/usr/bin/env python3
"""Fake players for testing a game alone.

    python tools/bots.py 6                                   # local server
    python tools/bots.py 6 --url https://avalon.iammerlin.fyi
    python tools/bots.py 4 --game Tintagel --delay 2

Each bot registers, joins the game (automatically if only one game is open,
or the one named with --game), and plays whenever it may act: proposing,
voting, choosing cards, pressing Continue, and sometimes using abilities.
They also vote in votes the host starts by hand.
Bots only act for themselves, so the game still waits for you.

Start the bots, then press "Start New Game" on the host page. They keep
playing new games until you stop them with Ctrl+C. Uses only the standard
library.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

NAMES = ["Bors", "Kay", "Gareth", "Bedivere", "Lamorak", "Gaheris", "Ector",
         "Lionel", "Dagonet", "Pelleas", "Safir", "Tor", "Lucan", "Yvain"]


class Bot:
    def __init__(self, name : str, args):
        self.name = name
        self.args = args
        self.rng = random.Random(f"{name}-{args.seed}")
        jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.http.addheaders = [("User-Agent", "avalon-test-bot")]
        self.game_id = None

    # ---- HTTP ----

    def request(self, path : str, data : dict | None = None):
        body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
        try:
            with self.http.open(self.args.url + path, body, timeout=20) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def log(self, message : str):
        print(f"[{self.name:>9}] {message}", flush=True)

    # ---- joining ----

    def join(self):
        self.request("/register", {"player": self.name})
        if self.args.game:
            status, html = self.request("/games")
            for lobby_id, label in re.findall(
                    r'action="/join/([^"]+)">\s*<button[^>]*>\s*([^<(]+)', html):
                if label.strip() == self.args.game:
                    self.request(f"/join/{lobby_id}", {})
                    break
            else:
                self.log(f'no open game called "{self.args.game}"')
                return False
        else:
            self.request("/")
        return True

    # ---- playing ----

    def run(self):
        while not self.join():
            time.sleep(5)
        self.log("joined, waiting for a game")
        while True:
            try:
                self.step()
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                self.log(f"connection problem: {e}")
                time.sleep(3)
            time.sleep(self.args.poll)

    def step(self):
        status, body = self.request("/game/state")
        if status == 404:
            return                      # no game yet (or not in it)
        if status != 200:
            self.log(f"state: HTTP {status}")
            return
        view = json.loads(body)
        if view["game_id"] != self.game_id:
            self.game_id = view["game_id"]
            self.log(f"new game: I am {view['you']['role']}")
        acts = view.get("actions") or {}
        hv = view.get("host_vote")
        if hv and hv["pending"]:
            path, action, params = "/game/host-vote", "host vote", self.host_vote(view, hv)
        else:
            choice = self.choose(view, acts)
            if choice is None:
                return
            (action, params), path = choice, "/game/action"
        time.sleep(self.rng.uniform(0.3, 1.0) * self.args.delay)
        status, body = self.request(path, dict(action=action, **params))
        if status == 200:
            self.log(f"{action} {params}" if params else action)
        else:
            try:
                error = json.loads(body).get("error")
            except ValueError:
                error = body[:80]
            self.log(f"{action} refused: {error}")

    def choose(self, view, acts) -> tuple[str, dict] | None:
        rng = self.rng
        evil = self.is_evil(view)
        me = self.name

        # Abilities first (sometimes), so they happen before Continue.
        if self.args.abilities:
            for action, field in [("gawain", "target"), ("changeling", "replaced"),
                                  ("sorceress", "next_proposer")]:
                if action in acts and rng.random() < 0.3:
                    return action, {field: rng.choice(acts[action]["choices"])}
            for action in ("betray", "proclaim"):
                if action in acts and rng.random() < 0.5:
                    return action, {}

        if "propose_first_round" in acts and not acts["propose_first_round"].get("current"):
            return "propose_first_round", {"team": self.pick_team(acts["propose_first_round"])}
        if "propose" in acts:
            return "propose", {"team": self.pick_team(acts["propose"])}
        if "vote_first_round" in acts and acts["vote_first_round"].get("current") is None:
            return "vote_first_round", {"proposer": rng.choice(acts["vote_first_round"]["choices"])}
        if "vote" in acts and acts["vote"].get("current") is None:
            team = view["proposals"][-1]["team"]
            approve = rng.random() < (0.8 if me in team else self.args.approve)
            return "vote", {"approve": "1" if approve else "0"}
        if "play_card" in acts:
            cards = acts["play_card"]["cards"]
            if evil and "Fail" in cards and rng.random() < self.args.fail:
                return "play_card", {"card": "Fail"}
            return "play_card", {"card": "Success" if "Success" in cards else rng.choice(cards)}
        if "inquisition" in acts:
            o = acts["inquisition"]
            remove = o["can_remove"] and rng.random() < 0.3
            return "inquisition", {"target": rng.choice(o["choices"]), "remove": "1" if remove else "0"}
        if "lady" in acts:
            return "lady", {"target": rng.choice(acts["lady"]["choices"])}
        if "ready" in acts:
            return "ready", {}
        if "pellinore_guess" in acts:
            return "pellinore_guess", {"target": rng.choice(acts["pellinore_guess"]["choices"])}
        if "assassinate" in acts:
            return "assassinate", {"kind": "merlin",
                                   "targets": rng.choice([p for p in view["seating"] if p != me])}
        return None

    def host_vote(self, view, hv) -> dict:
        """A choice in a vote the host started by hand."""
        if hv["kind"] == "proposal":
            approve = self.rng.random() < (0.8 if self.name in hv["team"] else self.args.approve)
            choice = "approve" if approve else "reject"
        else:
            evil = self.is_evil(view) and self.rng.random() < self.args.fail
            choice = "Fail" if evil else "Success"
        return {"vote": hv["id"], "choice": choice}

    def is_evil(self, view) -> bool:
        return view["you"]["role"] in ("Mordred", "Morgana", "Maelegant", "Agravaine",
                                       "Colgrevance", "Oberon", "Minion of Mordred")

    def pick_team(self, options) -> list[str]:
        players = list(options["players"])
        size = options["team_size"]
        team = [self.name] if self.name in players else []
        rest = [p for p in players if p not in team]
        return team + self.rng.sample(rest, size - len(team))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("count", type=int, help="number of bots (1-9)")
    parser.add_argument("--url", default="http://127.0.0.1:5000",
                        help="server address (default: %(default)s)")
    parser.add_argument("--game", help="name of the game to join, if several are open")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="roughly how many seconds bots take to act (default: %(default)s)")
    parser.add_argument("--poll", type=float, default=1.0,
                        help="seconds between checks for something to do (default: %(default)s)")
    parser.add_argument("--approve", type=float, default=0.5,
                        help="chance of approving a team they're not on (default: %(default)s)")
    parser.add_argument("--fail", type=float, default=0.7,
                        help="chance an Evil bot plays Fail (default: %(default)s)")
    parser.add_argument("--no-abilities", dest="abilities", action="store_false",
                        help="never use role abilities")
    parser.add_argument("--seed", default="0", help="change for different bot behaviour")
    args = parser.parse_args()
    args.url = args.url.rstrip("/")
    if not 1 <= args.count <= len(NAMES):
        sys.exit(f"count must be between 1 and {len(NAMES)}")

    bots = [Bot(f"{name}", args) for name in NAMES[:args.count]]
    for bot in bots:
        threading.Thread(target=bot.run, daemon=True).start()
        time.sleep(0.2)
    print(f"{args.count} bots running against {args.url}. Ctrl+C to stop.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
