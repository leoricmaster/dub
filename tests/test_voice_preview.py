from dub.voice_preview import (
    DEFAULT_PREVIEW_EMOTIONS,
    DEFAULT_PREVIEW_VOICES,
    expand_matrix,
)


def test_expand_matrix_is_cartesian_product():
    # Candidates appear in voices-x-emotions order; the baseline anchor is
    # always appended last (see test_expand_matrix_appends_baseline_anchor_when_missing).
    assert expand_matrix(["a", "b"], ["calm"]) == [
        ("a", "calm"),
        ("b", "calm"),
        ("presenter_male", "neutral"),
    ]


def test_expand_matrix_multiple_emotions():
    assert expand_matrix(["a"], ["calm", "fluent"]) == [
        ("a", "calm"),
        ("a", "fluent"),
        ("presenter_male", "neutral"),
    ]


def test_expand_matrix_appends_baseline_anchor_when_missing():
    result = expand_matrix(["male-qn-jingying"], ["calm"])
    assert result[-1] == ("presenter_male", "neutral")
    assert ("presenter_male", "neutral") in result


def test_expand_matrix_does_not_duplicate_anchor_when_present():
    result = expand_matrix(["presenter_male"], ["neutral"])
    assert result.count(("presenter_male", "neutral")) == 1


def test_defaults_are_non_empty():
    assert "presenter_male" in DEFAULT_PREVIEW_VOICES
    assert DEFAULT_PREVIEW_EMOTIONS == ["calm"]
