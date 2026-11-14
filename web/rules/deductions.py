"""What a player can work out about Gareth and Balin from their role info
(shown on the Role tab under "What you can work out").

Everyone knows which of Gareth and Balin could be dealt (the host's
selection, the player count and the rules) and how many Evil players there
are. A player's role info then rules some possibilities out. We list the
possible deals ("worlds": Gareth Good, Gareth Evil, Balin, ...), keep those
in which this player would have been told exactly what they were told, and
say what is true in all of them.

Only start-of-game information is used, so the notes never change during a
game and never depend on anything the player wasn't told.
"""
from __future__ import annotations

from dataclasses import dataclass

from markupsafe import Markup

from thavalon.dealing import num_extras, possible_extras
from thavalon.ruleset import RuleSet
from web.rules.pages import expand

GARETH, BALIN = "Gareth", "Balin the Savage"
BALIN_LINK = "[[Balin the Savage|Balin]]"


@dataclass(frozen=True)
class World:
    gareth : str | None      # Gareth's team, or None if Gareth isn't dealt
    balin : bool


def worlds(possible : list[str], exclusive : bool) -> list[World]:
    """Every deal of Gareth / Balin the game could have."""
    teams = ("Good", "Evil")
    if possible == [GARETH, BALIN]:
        if exclusive:
            return [World(t, False) for t in teams] + [World(None, True)]
        return [World(t, True) for t in teams]
    if possible == [GARETH]:
        return [World(t, False) for t in teams]
    if possible == [BALIN]:
        return [World(None, True)]
    return []


def _evil_sees_gareth(rules : RuleSet, w : World) -> bool:
    return w.gareth is not None and rules.gareth(w.gareth, "evil_sees")


def _red_sees_balin(rules : RuleSet, w : World, role : str) -> bool:
    return w.balin and rules["Balin.evil_sees"] and not (
        role == "Agravaine" and rules["Balin.agravaine_knows"])


def observation(role : str, rules : RuleSet, w : World):
    """What `role` would be told about Gareth and Balin in world `w`
    (anything hashable; only compared between worlds)."""
    told_gareth = lambda who: w.gareth is not None and rules.gareth(w.gareth, f"{who}_knows_role")
    if role == GARETH:
        return w.gareth is not None
    if role == BALIN:
        return w.balin
    if role == "Arthur":
        return (w.balin and rules["Arthur.sees_balin"],
                w.gareth == "Good" and rules["Arthur.sees_gareth"])
    if role == "Galahad":
        return w.gareth == "Evil" and rules["Galahad.sees_gareth"]
    if role == "Merlin":
        return told_gareth("merlin")
    if role == "Colgrevance":        # sees roles
        return (_evil_sees_gareth(rules, w), w.balin and rules["Balin.evil_sees"])
    if role == "Agravaine":
        extra = int(_evil_sees_gareth(rules, w)) + int(_red_sees_balin(rules, w, role))
        return (extra, w.balin and rules["Balin.agravaine_knows"], told_gareth("evil"))
    # Other Evil players: how many extra players they see among the Evil.
    extra = int(_evil_sees_gareth(rules, w)) + int(_red_sees_balin(rules, w, role))
    return (extra, told_gareth("evil"))


@dataclass
class Setup:
    """The public facts deductions start from."""
    possible : list[str]      # of GARETH, BALIN: those that can be dealt
    exclusive : bool          # only one of them is dealt
    num_evils : int           # Evil players, not counting Gareth
    actual : World            # the real deal (to read what this player was told)


def setup_of(game) -> Setup | None:
    """The Setup of a running AvalonGame (None: no game)."""
    state = game.controller.state if game.controller else None
    if state is None:
        return None
    n, rules = len(state.seating), state.rules
    possible = [str(r) for r in possible_extras(n, game.roles_in_game, rules)]
    gareth = state.player_with_role(GARETH)
    return Setup(possible = possible,
                 exclusive = num_extras(n, game.roles_in_game, rules) < len(possible),
                 num_evils = sum(r.allegiance() == "Evil" and str(r) != GARETH
                                 for r in state.roles.values()),
                 actual = World(state.allegiance(gareth) if gareth else None,
                                state.player_with_role(BALIN) is not None))


def deductions(role : str, info : dict, rules : RuleSet, setup : Setup | None) -> list[Markup]:
    """Sentences (links expanded) on what this player can conclude."""
    if setup is None or not setup.possible:
        return []
    evil = info.get("allegiance") == "Evil" and role not in ("Colgrevance",)
    if evil and not _red_count_is_reliable(role, rules):
        return []
    all_worlds = worlds(setup.possible, setup.exclusive)
    seen = observation(role, rules, setup.actual)
    left = [w for w in all_worlds if observation(role, rules, w) == seen]
    extra = seen[0] if evil else 0
    if len(left) == len(all_worlds) and role not in (GARETH, BALIN) and not extra:
        return []        # told nothing that narrows it down
    out = []
    if evil and extra:
        out.append(_red_extra_sentence(role, rules, left, extra, "gareth" in info))
    else:
        out += _gareth_sentences(role, left, setup,
                                 knows_who="gareth" in info or role == "Colgrevance")
    if BALIN in setup.possible and role != BALIN and "balin" not in info \
            and not (evil and extra):
        if all(w.balin for w in left):
            out.append(f"{BALIN_LINK} is in this game.")
        elif not any(w.balin for w in left):
            out.append(f"{BALIN_LINK} isn't in this game.")
    return [expand(s) for s in out]


def _red_count_is_reliable(role : str, rules : RuleSet) -> bool:
    """An Evil player can count extras only if they know how many real
    Evil players they should see: Oberon must be seen or announced, and an
    Oberon who doesn't see the others counts nothing."""
    if role == "Oberon":
        return bool(rules["Oberon.sees_evil"])
    return bool(rules["Oberon.seen_by_evil"] or rules["Oberon.announced"])


def _gareth_sentences(role : str, left : list[World], setup : Setup,
                      knows_who : bool = False) -> list[str]:
    if GARETH not in setup.possible or role == GARETH:
        return []
    teams = {w.gareth for w in left}
    if teams == {None}:
        return ["[[Gareth]] isn't in this game."]
    if None in teams:
        return []
    if len(teams) == 1:
        team = teams.pop()
        who = "" if knows_who else ", though you don't know who Gareth is"
        return [f"[[Gareth]] is in this game, and is {team} "
                f"({'blue' if team == 'Good' else 'red'}){who}."]
    return ["[[Gareth]] is in this game, but you can't tell which team Gareth is on."]


def _red_extra_sentence(role : str, rules : RuleSet, left : list[World], extra : int,
                        told_gareth : bool) -> str:
    """For an Evil player who sees more players than there are Evil players."""
    kinds = set()
    for w in left:
        parts = []
        if _evil_sees_gareth(rules, w):
            parts.append(f"{'an Evil' if w.gareth == 'Evil' else 'a Good'} [[Gareth]]")
        if _red_sees_balin(rules, w, role):
            parts.append(f"{BALIN_LINK} (who is Good)")
        kinds.add(" and ".join(parts))
    players = "One of the players" if extra == 1 else f"{extra} of the players"
    if len(kinds) == 1:
        what = kinds.pop()
        tail = ("" if "Balin" in what and "Gareth" not in what
                else " Gareth doesn't see you and doesn't know their own team."
                if "an Evil" in what else "")
        which = "" if told_gareth and "Balin" not in what else ": you can't tell which"
        return (f"{players} you see as Evil {'is' if extra == 1 else 'are'} really {what}"
                f"{which}.{tail}")
    return (f"{players} you see as Evil is really either "
            f"{' or '.join(sorted(kinds, key=lambda k: 'Gareth' not in k))}: you can't tell which, "
            "or who.")
