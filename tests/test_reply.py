"""Reply post-processing: no model calls."""

from engine.reply import _change_summary, tidy_maths


def test_tidy_maths_replaces_ascii_powers_and_greek():
    assert tidy_maths("theta_1 - theta_2 = 2pi, so t^2 = 16") == "θ1 - θ2 = 2π, so t² = 16"
    assert tidy_maths("tan^-1(4)") == "tan⁻¹(4)"


def test_tidy_maths_leaves_words_alone():
    assert tidy_maths("spinach and pipes") == "spinach and pipes"


def test_change_summary_shows_short_text_edits_only():
    edit = {"field": "question", "find": "Canolla", "replace": "Canola"}
    assert _change_summary(edit) == "question: 'Canolla' -> 'Canola'"
    assert _change_summary({"field": "answer", "find": "C", "replace": "A"}) is None
    assert _change_summary(None) is None
