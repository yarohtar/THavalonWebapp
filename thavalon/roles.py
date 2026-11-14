"""The roles, and what each player is told about the others when the game
starts (their role info).

A role is identified by its name: two Merlin objects are equal. The
generic Servants and Minions are numbered so several can be dealt. Each
role has one shared instance below (`merlin`, `mordred`, ...), and
`string_to_role` finds it by name.

`Role.get_info(deal)` looks at a finished deal (dealing.AvalonBuilder: who
has which role, and the game's RuleSet) and returns the role's info as a
dict, e.g. {'allegiance': 'Good', 'seen': [players Merlin sees]}. Some info
is random (who Uther stalks, the order players are listed in), drawn from
`deal.rng`.

`transform_if_lonely(deal)` is how a role changes when its partner wasn't
dealt (Merlin without Percival becomes Nilrem, ...), at the player counts
the rules say.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from thavalon.ruleset import RuleSet, DEFAULT as DEFAULT_RULES

if TYPE_CHECKING:
    from thavalon.dealing import AvalonBuilder


class Role:
    name : str          # set by every concrete role

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other) -> bool:
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))

    def allegiance(self) -> str:
        return "none"

    def is_base_role(self) -> bool:
        """False for roles that only arise by transforming (Nilrem, ...):
        they are never dealt directly."""
        return True

    def can_appear(self, num_players : int, rules : RuleSet | None = None) -> bool:
        """Whether this role can be dealt in a game of this size."""
        allowed = (rules or DEFAULT_RULES).can_appear(str(self), num_players)
        return True if allowed is None else allowed

    def get_info(self, deal : AvalonBuilder) -> dict:
        return {'allegiance': self.allegiance()}

    def transform_if_lonely(self, deal : AvalonBuilder) -> Role:
        return self

    def _lonely_here(self, deal : AvalonBuilder) -> bool:
        """Whether this game's size is one where this role transforms."""
        return len(deal.players) in deal.rules.lonely_counts(str(self))


class NumberedRole(Role):
    """A generic role that several players can have (Servant, Minion)."""
    index : int

    def __init__(self, index : int):
        self.index = index

    def __eq__(self, other) -> bool:
        return isinstance(other, type(self)) and self.index == other.index

    def __hash__(self):
        return hash(str(self) + str(self.index))


# ---------------------------------------------------------------- Good

class GoodRole(Role):
    def allegiance(self) -> str:
        return "Good"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        if nilrem in deal and deal.rules['Nilrem.known']:
            info['nilrem'] = deal[nilrem]
        return info


class SoC(NumberedRole, GoodRole):
    name = "Servant of Camelot"


class Merlin(GoodRole):
    name = "Merlin"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        rules = deal.rules
        seen = [deal[role] for role in deal
                if (rules.gareth(role.team, 'merlin_sees') if isinstance(role, Gareth)
                    else role.allegiance() == "Evil" and rules.merlin_sees(str(role)))]
        # Good roles Merlin may see as Evil come last (before shuffling).
        for good in (lancelot, balin):
            if good in deal and rules.merlin_sees(str(good)):
                seen.append(deal[good])
        deal.rng.shuffle(seen)
        info['seen'] = seen
        add_gareth_role(info, deal, 'merlin_knows_role')
        return info

    def transform_if_lonely(self, deal : AvalonBuilder) -> Role:
        if self._lonely_here(deal) and percival not in deal:
            return nilrem
        return self


class Nilrem(GoodRole):
    name = "Nilrem"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info.pop('nilrem', None)
        return info

    def is_base_role(self) -> bool:
        return False


class Percival(GoodRole):
    name = "Percival"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info['seen'] = deal.get_players_with_roles(roles_named(deal.rules.percival_sees()))
        return info

    def transform_if_lonely(self, deal : AvalonBuilder) -> Role:
        if self._lonely_here(deal) and not any(
                string_to_role[r] in deal for r in deal.rules.percival_sees()):
            return galahad
        return self


class Galahad(GoodRole):
    name = "Galahad"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info['evil_roles'] = [role for role in deal if role.allegiance() == "Evil" and (
            not isinstance(role, Gareth) or deal.rules['Galahad.sees_gareth'])]
        return info

    def is_base_role(self) -> bool:
        return False


class Lover(GoodRole):
    """Tristan and Iseult know each other; alone, they become Uther."""
    def partner(self) -> Role:
        raise NotImplementedError

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        partner = self.partner()
        info['lover'] = deal[partner] if partner in deal else 'unloved'
        return info

    def transform_if_lonely(self, deal : AvalonBuilder) -> Role:
        if self._lonely_here(deal) and self.partner() not in deal:
            return uther
        return self


class Tristan(Lover):
    name = "Tristan"

    def partner(self) -> Role:
        return iseult


class Iseult(Lover):
    name = "Iseult"

    def partner(self) -> Role:
        return tristan


class Uther(GoodRole):
    name = "Uther"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        other_goods = [role for role in deal
                       if role.allegiance() == "Good" and role != uther and role != nilrem]
        # Nobody to stalk can only happen with unusual settings.
        info['stalked_good'] = (deal[deal.rng.sample(other_goods, 1)[0]]
                                if other_goods else None)
        return info

    def is_base_role(self) -> bool:
        return False


class Arthur(GoodRole):
    name = "Arthur"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        rules = deal.rules
        info['good_roles'] = [
            role for role in deal if role.allegiance() == "Good"
            and (not isinstance(role, Gareth) or rules['Arthur.sees_gareth'])
            and (role != balin or rules['Arthur.sees_balin'])]
        return info


class Lancelot(GoodRole):
    name = "Lancelot"


class Guinevere(GoodRole):
    name = "Guinevere"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info['seen'] = deal.get_players_with_roles(roles_named(deal.rules.guinevere_sees()))
        return info

    def transform_if_lonely(self, deal : AvalonBuilder) -> Role:
        if self._lonely_here(deal) and not any(
                string_to_role[r] in deal for r in deal.rules.guinevere_sees()):
            return ygraine
        return self


class Ygraine(GoodRole):
    name = "Ygraine"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        evils = [role for role in deal if role.allegiance() == "Evil" and role != mordred]
        # None when Mordred is the only Evil player.
        info['stalked_evil'] = deal[deal.rng.sample(evils, 1)[0]] if evils else None
        return info

    def is_base_role(self) -> bool:
        return False


class Gawain(GoodRole):
    name = "Gawain"

    def get_info(self, deal : AvalonBuilder) -> dict:
        """Three players, at least one of them Good, in random order."""
        info = super().get_info(deal)
        goods = [role for role in deal if role.allegiance() == "Good" and role != gawain]
        if not goods or len(deal.role_to_player) < 4:
            info['seen'] = []
            return info
        good_seen = deal.rng.sample(goods, 1)[0]
        everyone_else = [role for role in deal if role != gawain and role != good_seen]
        seen = deal.rng.sample(everyone_else, 2)
        seen.append(good_seen)
        deal.rng.shuffle(seen)
        info['seen'] = [deal[role] for role in seen]
        return info


class Balin(GoodRole):
    """Good, but wins only if they played at least one Fail (by default).
    Evil see Balin as one of them; Agravaine is told who Balin is."""
    name = "Balin the Savage"


# ---------------------------------------------------------------- Evil

class EvilRole(Role):
    def allegiance(self) -> str:
        return "Evil"

    def get_visible_evils(self, deal : AvalonBuilder) -> list[str]:
        return deal.get_players_with_roles(visible_evil_roles(deal, self))

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info['other_evils'] = self.get_visible_evils(deal)
        # Told that an Oberon lurks, when they don't see Oberon themselves.
        info['oberon'] = (oberon in deal and deal.rules['Oberon.announced']
                          and not deal.rules['Oberon.seen_by_evil'])
        add_gareth_role(info, deal, 'evil_knows_role')
        return info


class MoM(NumberedRole, EvilRole):
    name = "Minion of Mordred"


class Mordred(EvilRole):
    name = "Mordred"


class Morgana(EvilRole):
    name = "Morgana"


class Maelegant(EvilRole):
    name = "Maelegant"


class Agravaine(EvilRole):
    name = "Agravaine"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        if balin in deal and deal.rules['Balin.agravaine_knows']:
            info['balin'] = deal[balin]
        return info


class Colgrevance(EvilRole):
    name = "Colgrevance"

    def get_info(self, deal : AvalonBuilder) -> dict:
        """Sees every Evil role (Oberon included) and who has it."""
        info = super().get_info(deal)
        info['evil_roles'] = {
            deal[role]: role for role in deal if role != colgrevance and (
                role.allegiance() == "Evil" and not isinstance(role, Gareth)
                or isinstance(role, Gareth) and deal.rules.gareth(role.team, 'evil_sees')
                or role == balin and deal.rules['Balin.evil_sees'])}
        return info


class Oberon(EvilRole):
    name = "Oberon"

    def get_visible_evils(self, deal : AvalonBuilder) -> list[str]:
        if not deal.rules['Oberon.sees_evil']:
            return []
        return super().get_visible_evils(deal)

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info['oberon'] = False
        return info


def visible_evil_roles(deal : AvalonBuilder, viewer : Role) -> list[Role]:
    """Roles an Evil player sees as fellow Evil (in the deal's order)."""
    rules = deal.rules
    seen = []
    for role in deal:
        if role == viewer:
            continue
        if isinstance(role, Gareth):
            if rules.gareth(role.team, 'evil_sees'):
                seen.append(role)
        elif role == balin:
            # Agravaine, told who Balin is, isn't fooled.
            if rules['Balin.evil_sees'] and not (viewer == agravaine
                                                 and rules['Balin.agravaine_knows']):
                seen.append(role)
        elif role.allegiance() == "Evil" and (role != oberon or rules['Oberon.seen_by_evil']):
            seen.append(role)
    return seen


# ---------------------------------------------------------------- Gareth

class Gareth(Role):
    """Joins the team of a random player (the Knight); a random player of
    the other team is the Rival. Gareth doesn't know their own team.
    `team` is None until the deal decides it (dealing.choose_gareth_team)."""
    name = "Gareth"
    team : str | None
    knight : str | None
    rival : str | None

    def __init__(self, team : str | None = None,
                 knight : str | None = None, rival : str | None = None):
        self.team = team
        self.knight = knight
        self.rival = rival

    def allegiance(self) -> str:
        return self.team or "none"

    def get_info(self, deal : AvalonBuilder) -> dict:
        # No Nilrem, no fellow Evil: anything more would reveal the team.
        knows = deal.rules['Gareth.knows']
        info = {'allegiance': 'Unknown'}
        if knows in ('both', 'knight'):
            info['knight'] = self.knight
        if knows in ('both', 'rival'):
            info['rival'] = self.rival
        return info


def add_gareth_role(info : dict, deal : AvalonBuilder, rule : str):
    """Tell this player which player is Gareth, if the rules say so."""
    for role in deal:
        if isinstance(role, Gareth) and deal.rules.gareth(role.team, rule):
            info['gareth'] = deal[role]


# ---------------------------------------------------------------- Neutral

class NeutralRole(Role):
    def allegiance(self) -> str:
        return "Neutral"


class Pellinore(NeutralRole):
    name = "Pellinore"


class TheBeast(NeutralRole):
    name = "The Questing Beast"

    def get_info(self, deal : AvalonBuilder) -> dict:
        info = super().get_info(deal)
        info['pellinore'] = deal[pellinore]
        return info


# ---------------------------------------------------------------- the roles

percival = Percival()
galahad = Galahad()
merlin = Merlin()
tristan = Tristan()
iseult = Iseult()
uther = Uther()
arthur = Arthur()
lancelot = Lancelot()
guinevere = Guinevere()
ygraine = Ygraine()
gawain = Gawain()
nilrem = Nilrem()
balin = Balin()

mordred = Mordred()
morgana = Morgana()
maelegant = Maelegant()
agravaine = Agravaine()
colgrevance = Colgrevance()
oberon = Oberon()

gareth = Gareth()

pellinore = Pellinore()
beast = TheBeast()

# Every named role, in the usual order (selection lists and dealing follow it).
all_roles : list[Role] = [
    percival, galahad, merlin, tristan, iseult, uther, arthur, lancelot, guinevere,
    ygraine, gawain, nilrem, balin,
    mordred, morgana, maelegant, agravaine, colgrevance, oberon,
    gareth,
    pellinore, beast,
]

string_to_role : dict[str, Role] = {str(role): role for role in all_roles}


def roles_named(names : list[str]) -> list[Role]:
    return [string_to_role[name] for name in names]

