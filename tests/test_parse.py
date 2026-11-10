from engine.models import group_reports
from engine.parse import html_to_text, math_block_to_text, split_options


def test_mathml_fraction_and_power():
    m = (
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>q</mi>'
        "<mrow><mn>2</mn><msub><mi>ε</mi><mn>0</mn></msub></mrow></mfrac></math>"
    )
    assert math_block_to_text(m) == "q/(2ε_0)"


def test_encoded_less_than_does_not_break_math_parse(q):
    # AI-WRONG #1: pre-unescaping &#x0003C; broke this parse and looked like a data defect.
    text = html_to_text(q("622df25a").solution_html)
    assert "P_2<P_1" in text


def test_named_html_entities_and_bare_ampersand_inside_math():
    assert math_block_to_text("<math><mo>&there4;</mo><mi>&</mi><mi>x</mi></math>") == "∴&x"


def test_html_superscript_kept_as_caret(q):
    assert "10^-5" in html_to_text(q("6062ec84").question_html)


def test_options_split_ignores_assertion_label_in_stem(q):
    stem, opts = split_options(html_to_text(q("695ee00b").question_html))
    assert stem.startswith("Assertion (A)")
    assert list(opts) == ["A", "B", "C", "D"]
    assert opts["D"].startswith("A is false")


def test_option_labels_inside_mathml(q):
    _, opts = split_options(html_to_text(q("68c9ae5a").question_html))
    assert opts == {"A": "3.1 V", "B": "2.0 V", "C": "5.1 V", "D": "1.1 V"}


def test_blank_and_missing_options(q):
    assert split_options(html_to_text(q("68e87254").question_html))[1]["C"] == ""
    assert list(split_options(html_to_text(q("622f08d7").question_html))[1]) == ["A", "B", "C"]


def test_every_option_question_parses_to_at_least_three_options(questions):
    for question in questions.values():
        if question.qtype != "integerQuestion":
            _, opts = split_options(html_to_text(question.question_html))
            assert len(opts) >= 3, question.id


def test_grouping(reports):
    groups = group_reports(reports)
    assert len(groups) == 39
    assert [r.report_id for r in groups["60f744b3f1b9bc7cc7b4a949"]] == ["R002", "R003", "R001"]
