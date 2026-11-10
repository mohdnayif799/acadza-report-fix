"""Confidence is computed from independent checks (documented in PROMPTS.md)."""

from engine.confidence import penalise, score


def test_each_agreeing_check_halves_the_doubt():
    assert score([]) == 0.5
    assert score([("a", True)]) == 0.75
    assert score([("a", True), ("b", True)]) == 0.88
    assert score([("a", True), ("b", True), ("c", True)]) == 0.94
    assert score([("a", True)] * 4) == 0.97


def test_any_disagreement_caps_at_a_coin_flip():
    assert score([("a", True), ("b", True), ("c", False)]) == 0.5
    assert score([("a", False)]) == 0.5


def test_one_check_alone_can_never_reach_the_auto_apply_floor():
    assert score([("only one model said so", True)]) < 0.8


def test_guard_rejection_penalty_has_a_floor():
    assert penalise(0.94) == 0.79
    assert penalise(0.35) == 0.3
