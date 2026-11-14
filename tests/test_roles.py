"""What each role is told at the start (role info), and how roles are dealt."""
import random

import pytest

from helpers import T, build, deal, info
from thavalon.dealing import (AvalonBuilder, DEFAULT_TEAM_SIZES, default_double_fail_quest,
                              default_num_evils)

SEVEN = {"a": "Merlin", "b": "Percival", "c": "Servant", "d": "Servant",
         "e": "Mordred", "f": "Morgana", "g": "Minion"}


# ---------------------------------------------------------------- role info

def test_every_role_is_told_its_allegiance():
    b = deal(SEVEN)
    assert [info(b, p)["allegiance"] for p in SEVEN] == ["Good"] * 4 + ["Evil"] * 3


def test_good_players_learn_nilrem_but_nilrem_and_evil_dont():
    b = deal({"a": "Nilrem", "b": "Servant", "c": "Arthur", "d": "Mordred", "e": "Minion"})
    assert info(b, "b")["nilrem"] == "a" and info(b, "c")["nilrem"] == "a"
    assert "nilrem" not in info(b, "a")
    assert "nilrem" not in info(b, "d")
    assert "nilrem" not in info(deal(SEVEN), "c")             # no Nilrem in the game


def test_merlin_sees_default_evils_but_not_mordred():
    b = deal({"a": "Merlin", "b": "Mordred", "c": "Morgana", "d": "Minion",
              "e": "Lancelot", "f": "Balin the Savage", "g": "Agravaine", "h": "Servant"})
    assert sorted(info(b, "a")["seen"]) == ["c", "d", "e", "f", "g"]
    assert "gareth" not in info(b, "a")


def test_percival_sees_merlin_and_morgana():
    assert sorted(info(deal(SEVEN), "b")["seen"]) == ["a", "f"]


def test_galahad_sees_the_evil_roles_not_players():
    b = deal({**SEVEN, "b": "Galahad"})
    assert sorted(map(str, info(b, "b")["evil_roles"])) == \
        ["Minion of Mordred", "Mordred", "Morgana"]


def test_lovers_see_each_other_or_are_unloved():
    b = deal({**SEVEN, "c": "Tristan", "d": "Iseult"})
    assert info(b, "c")["lover"] == "d" and info(b, "d")["lover"] == "c"
    assert info(deal({**SEVEN, "c": "Tristan"}), "c")["lover"] == "unloved"
    assert info(deal({**SEVEN, "c": "Iseult"}), "c")["lover"] == "unloved"


def test_uther_stalks_a_good_player_other_than_nilrem():
    b = deal({"a": "Uther", "b": "Nilrem", "c": "Servant", "d": "Mordred", "e": "Minion"})
    for seed in range(20):
        random.seed(seed)
        assert info(b, "a")["stalked_good"] == "c"
    lonely = deal({"a": "Uther", "b": "Nilrem", "c": "Mordred", "d": "Minion", "e": "Morgana"})
    assert info(lonely, "a")["stalked_good"] is None


def test_ygraine_stalks_an_evil_player_other_than_mordred():
    b = deal({"a": "Ygraine", "b": "Servant", "c": "Mordred", "d": "Morgana", "e": "Servant"})
    for seed in range(20):
        random.seed(seed)
        assert info(b, "a")["stalked_evil"] == "d"
    only_mordred = deal({"a": "Ygraine", "b": "Servant", "c": "Mordred", "d": "Servant",
                         "e": "Servant"})
    assert info(only_mordred, "a")["stalked_evil"] is None


def test_arthur_sees_the_good_roles():
    b = deal({**SEVEN, "c": "Arthur"})
    assert sorted(map(str, info(b, "c")["good_roles"])) == \
        ["Arthur", "Merlin", "Percival", "Servant of Camelot"]


def test_guinevere_sees_lancelot_arthur_and_maelegant():
    b = deal({"a": "Guinevere", "b": "Lancelot", "c": "Arthur", "d": "Maelegant",
              "e": "Mordred", "f": "Servant", "g": "Minion"})
    assert sorted(info(b, "a")["seen"]) == ["b", "c", "d"]


def test_gawain_sees_three_players_including_a_good_one():
    b = deal({"a": "Gawain", "b": "Servant", "c": "Mordred", "d": "Morgana", "e": "Minion",
              "f": "Agravaine", "g": "Colgrevance", "h": "Oberon", "i": "Maelegant",
              "j": "Minion"})
    for seed in range(30):
        random.seed(seed)
        seen = info(b, "a")["seen"]
        assert len(seen) == len(set(seen)) == 3 and "a" not in seen and "b" in seen


def test_gawain_with_too_few_players_sees_no_one():
    b = deal({"a": "Gawain", "b": "Servant", "c": "Mordred"})
    assert info(b, "a")["seen"] == []
    assert info(deal({"a": "Gawain", "b": "Mordred", "c": "Morgana", "d": "Minion"}),
                "a")["seen"] == []


def test_agravaine_is_told_who_balin_is_and_balin_nothing():
    b = deal({**SEVEN, "c": "Balin the Savage", "g": "Agravaine"})
    assert info(b, "c") == {"allegiance": "Good"}
    assert info(b, "g")["balin"] == "c" and "c" not in info(b, "g")["other_evils"]


def test_evil_see_each_other_but_not_oberon_and_are_told_oberon_lurks():
    b = deal({"a": "Mordred", "b": "Morgana", "c": "Oberon", "d": "Merlin", "e": "Servant",
              "f": "Servant", "g": "Servant"})
    assert sorted(info(b, "a")["other_evils"]) == ["b"] and info(b, "a")["oberon"] is True
    assert sorted(info(b, "c")["other_evils"]) == ["a", "b"] and info(b, "c")["oberon"] is False
    no_oberon = deal(SEVEN)
    assert info(no_oberon, "e")["oberon"] is False


def test_colgrevance_sees_evil_roles_by_player():
    b = deal({"a": "Colgrevance", "b": "Mordred", "c": "Oberon", "d": "Merlin",
              "e": "Servant"})
    assert {p: str(r) for p, r in info(b, "a")["evil_roles"].items()} == \
        {"b": "Mordred", "c": "Oberon"}


def test_the_beast_knows_pellinore_and_pellinore_knows_nothing_more():
    b = deal({**SEVEN, "c": "Pellinore", "d": "The Questing Beast"})
    assert info(b, "d") == {"allegiance": "Neutral", "pellinore": "c"}
    assert info(b, "c") == {"allegiance": "Neutral"}


# ---------------------------------------------------------------- roles

def test_role_identity_is_by_name_and_generic_roles_by_number():
    assert T.Merlin() == T.merlin and hash(T.Merlin()) == hash(T.merlin)
    assert T.SoC(0) == T.SoC(0) and T.SoC(0) != T.SoC(1)
    assert T.MoM(0) != T.MoM(1) and T.MoM(0) != T.SoC(0)
    assert len({T.SoC(0), T.SoC(1), T.MoM(0), T.MoM(0)}) == 3
    assert T.Gareth("Good") == T.gareth and T.Gareth("Evil").allegiance() == "Evil"
    assert T.gareth.allegiance() == "none"


def test_transformed_roles_are_not_base_roles():
    assert {str(r) for r in T.all_roles if not r.is_base_role()} == \
        {"Galahad", "Uther", "Ygraine", "Nilrem"}


def test_string_to_role_knows_every_role():
    assert all(T.string_to_role[str(r)] is r for r in T.all_roles)
    assert T.roles_named(["Merlin", "Oberon"]) == [T.merlin, T.oberon]


# ---------------------------------------------------------------- dealing

@pytest.mark.parametrize("n,evils", [(5, 2), (6, 2), (7, 3), (8, 3), (9, 4), (10, 4)])
def test_default_evil_counts_and_everyone_gets_a_role(n, evils):
    assert default_num_evils(n) == evils
    for seed in range(10):
        b = build(n, [r for r in T.all_roles if r not in (T.gareth, T.balin)], seed=seed)
        assert sorted(b.role_to_player.values()) == sorted(b.players)
        assert sum(r.allegiance() == "Evil" for r in b) == evils


def test_default_team_sizes_and_double_fail():
    assert {n: default_double_fail_quest(n) for n in range(5, 11)} == \
        {5: None, 6: None, 7: 4, 8: 4, 9: 4, 10: 4}
    assert DEFAULT_TEAM_SIZES[5] == [2, 3, 2, 3, 3]
    assert DEFAULT_TEAM_SIZES[7] == [2, 3, 3, 4, 4]


def test_chosen_number_of_evils():
    b = build(7, [T.merlin, T.mordred], num_evils=2)
    assert sum(r.allegiance() == "Evil" for r in b) == 2


def test_generic_roles_fill_the_table():
    b = build(7, [])
    assert sum(isinstance(r, T.SoC) for r in b) == 4
    assert sum(isinstance(r, T.MoM) for r in b) == 3


def test_balin_is_always_dealt_when_possible():
    for seed in range(10):
        b = build(9, [T.balin, T.merlin, T.mordred], seed=seed)
        assert T.balin in b
        assert [r.allegiance() for r in b].count("Evil") == 3     # Balin takes an Evil place
    assert T.balin not in build(6, [T.balin])                     # 9 players only by default
    for n in (5, 7, 8, 10):
        assert T.balin not in build(n, [T.balin])


def test_pellinore_and_beast_take_two_good_places_at_nine():
    for seed in range(10):
        b = build(9, [T.pellinore, T.beast], seed=seed)
        assert T.pellinore in b and T.beast in b
        assert sum(r.allegiance() == "Good" for r in b) == 3
        assert sum(r.allegiance() == "Evil" for r in b) == 4


def test_lonely_roles_transform_at_seven_or_more():
    assert T.nilrem in build(7, [T.merlin]) and T.merlin in build(6, [T.merlin])
    assert T.merlin in build(7, [T.merlin, T.percival])
    assert T.galahad in build(7, [T.percival])
    assert T.uther in build(7, [T.tristan]) and T.tristan in build(6, [T.tristan])
    assert T.tristan in build(7, [T.tristan, T.iseult])
    assert T.ygraine in build(7, [T.guinevere])
    assert T.guinevere in build(7, [T.guinevere, T.lancelot])


def test_transformed_roles_selected_directly_are_not_dealt():
    for n in range(5, 11):
        b = build(n, [T.galahad, T.uther, T.ygraine, T.nilrem])
        assert not any(r in b for r in (T.galahad, T.uther, T.ygraine, T.nilrem))


def test_players_are_shuffled_deduplicated_and_proposers_come_first():
    random.seed(3)
    b = AvalonBuilder(["a", "b", "c", "d", "e", "a"], [])
    assert sorted(b.players) == ["a", "b", "c", "d", "e"]
    assert b.get_first_mission_proposers() == b.players[:2]
    assert b.get_second_mission_starter() == b.players[2]


@pytest.mark.parametrize("n", [4, 13])
def test_too_few_or_many_players(n):
    with pytest.raises(AssertionError):
        AvalonBuilder([f"P{i}" for i in range(n)], [])


def test_impossible_evil_count_is_a_readable_error():
    for evils in (0, 5):
        with pytest.raises(ValueError):
            build(5, [], num_evils=evils)


def test_arthur_is_never_gareths_knight_unless_allowed():
    from thavalon.ruleset import RuleSet
    pool = [T.arthur, T.merlin, T.mordred, T.morgana, T.gareth]

    def knights(rules):
        out = set()
        for seed in range(80):
            b = build(9, pool, seed=seed, rules=rules)
            g = next(r for r in b if isinstance(r, T.Gareth))
            out.add(next(str(r) for r in b if b[r] == g.knight))
        return out
    assert "Arthur" not in knights(None)
    assert "Arthur" in knights(RuleSet({"Gareth.arthur_knight": True}))
