"""Run with:  python test_engine.py   (or: pytest -q)

Simulates thousands of games and checks the promises the game depends on:
real clues are true, fake clues are false, the secret is never eliminated,
options are valid, and scoring behaves.
"""
import random
import statistics

import game_engine as ge


def names(n):
    return [f"P{i}" for i in range(1, n + 1)]


def test_clue_truth_and_candidates():
    for seed in range(1500):
        n = random.Random(seed).randint(ge.MIN_PLAYERS, 15)
        hi = random.Random(seed + 1).choice((50, 100, 200))
        g = ge.new_game(names(n), seed=seed, hi=hi)
        assert 1 <= g.secret <= hi
        prev = None
        for r in range(ge.ROUNDS):
            assert set(g.clues[r]) == set(g.players)
            for p in g.players:
                assert g.secret in g.clues[r][p].matches, "true clue must hold for the secret"
                assert g.clues[r][p].is_true
                fake = g.fakes[r][p]
                assert fake is not None and not fake.is_true
                assert g.secret not in fake.matches, "fake clue must be false for the secret"
            poss = g.possible_after[r]
            assert g.secret in poss
            if prev is not None:
                assert poss <= prev, "candidate pool can only shrink"
            prev = poss
        # the final pool is never a giveaway of size 1 unless the range is tiny
        assert len(g.possible_after[-1]) >= 2


def test_options():
    for seed in range(1500):
        n = random.Random(seed).randint(3, 15)
        g = ge.new_game(names(n), seed=seed)
        o = g.options
        assert len(o) == ge.OPTION_COUNT == len(set(o))
        assert g.secret in o and o == sorted(o)
        assert all(g.low <= x <= g.high for x in o)


def test_clue_card_text_never_repeats():
    """A player should never receive the same clue card twice in one game."""
    for seed in range(500):
        g = ge.new_game(names(15), seed=seed, hi=(50, 100, 200)[seed % 3])
        card_text = [
            clue.text
            for r in range(ge.ROUNDS)
            for clue in (*g.clues[r].values(), *g.fakes[r].values())
        ]
        assert len(card_text) == len(set(card_text)), "clue cards must be unique per game"


def test_scoring_bands():
    assert ge.points_for_guess(47, 47) == 5
    assert ge.points_for_guess(47, 52) == 3
    assert ge.points_for_guess(47, 41) == 1
    assert ge.points_for_guess(47, 58) == 0
    assert ge.points_for_guess(47, 53) == 1  # 6 away -> next band


def test_bluff_rules_and_round_scoring():
    g = ge.new_game(names(5), seed=7)
    assert ge.bluff_cap(5) == 2
    assert g.use_bluff(0, "P1") and g.use_bluff(0, "P2")
    assert not g.can_bluff(0, "P3"), "cap of 2 per round for 5 players"
    assert g.bluff_block_reason(0, "P3")
    assert not g.use_bluff(1, "P1"), "one bluff per player per game"
    assert g.clue_seen(0, "P1") is g.fakes[0]["P1"]
    assert g.clue_seen(0, "P3") is g.clues[0]["P3"]
    votes = {"P1": "P3", "P2": "P3", "P3": "P1", "P4": "P1", "P5": "P2"}
    pts = g.score_round(0, votes)
    # P3 honest, trusted twice: +2.  P1/P2 pointed at honest P3: +1 each.
    # P1 fooled two players: +4 (plus +1 good read).  P2 fooled one: +2 (plus +1).
    assert pts == {"P1": 5, "P2": 3, "P3": 2, "P4": 0, "P5": 0}, pts
    assert g.fingers[0]["P1"] == 2 and g.fingers[0]["P3"] == 2


def test_flop_penalty_and_vote_validation():
    g = ge.new_game(names(4), seed=3)
    g.use_bluff(0, "P1")
    pts = g.score_round(0, {"P1": "P2", "P2": "P3", "P3": "P4", "P4": "P2"})
    assert pts["P1"] == 1 - 1, "pointed at honest P2 (+1) but nobody fell for the bluff (-1)"
    h = ge.new_game(names(4), seed=3)
    for bad in ({"P1": "P1", "P2": "P3", "P3": "P4", "P4": "P2"},   # self vote
                {"P1": "P2", "P2": "P3", "P3": "P4"},                # missing voter
                {"P1": "PX", "P2": "P3", "P3": "P4", "P4": "P2"}):   # unknown target
        try:
            h.score_round(0, bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad}")


def test_two_player_game_and_bluff_call():
    g = ge.new_game(names(2), seed=12)
    assert ge.bluff_cap(2) == 1
    assert g.use_bluff(0, "P1")
    points = g.score_round(0, {"P1": "P2", "P2": None})
    # P1 trusts honest P2 (+1), but P2 calls P1's bluff, so it flops (-1).
    assert points == {"P1": 0, "P2": 1}


def test_bluff_can_beat_honesty():
    """A bluff that fools people out-earns the same votes going to an honest player."""
    g = ge.new_game(names(5), seed=5)
    g.use_bluff(0, "P1")
    fooled = g.score_round(0, {"P1": "P2", "P2": "P1", "P3": "P1", "P4": "P1", "P5": "P2"})["P1"]
    h = ge.new_game(names(5), seed=5)
    honest = h.score_round(0, {"P1": "P2", "P2": "P1", "P3": "P1", "P4": "P1", "P5": "P2"})["P1"]
    assert fooled > honest, (fooled, honest)


def test_full_game_flow_and_winner():
    g = ge.new_game(names(5), seed=11)
    ring = {p: g.players[(i + 1) % 5] for i, p in enumerate(g.players)}
    for r in range(ge.ROUNDS):
        g.score_round(r, ring)
    for p in g.players:
        g.submit_pick(p, g.secret if p == "P3" else g.options[0])
    totals = g.totals()
    assert totals["P3"] >= 5 + 3  # exact guess + trust and good-read points
    assert g.leaderboard()[0][1] == max(totals.values())
    assert g.winners()
    assert g.good_reads() == {p: ge.ROUNDS for p in g.players}
    assert g.bluff_fools() == {p: 0 for p in g.players}


def test_validation():
    assert ge.new_game(["A", "B"], seed=1)
    for bad in (["A"], ["A", "A"], ["A", ""]):
        try:
            ge.new_game(bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad}")


def report():
    """Not an assertion: shows how quickly the pool narrows for group sizes."""
    print("\nCandidates left after each round (average of 300 games, range 1-100)")
    for n in (3, 5, 8, 15):
        rows = [[len(x) for x in ge.new_game(names(n), seed=s).possible_after] for s in range(300)]
        avg = [round(statistics.mean(col), 1) for col in zip(*rows)]
        print(f"  {n:>2} players: {avg}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
    report()
