"""Tests for social model tone assertions and persona impact mappings."""
import pytest
from pdf_a11y.reports.tone import (
    WHO_MAP,
    ACROBAT_ASSISTANT_NOTES,
    assert_social_model_language,
    DISALLOWED_MEDICAL_TERMS,
)


def test_assert_social_model_language_passes_clean_text():
    clean = (
        "Screen reader navigators and low-vision readers require sufficient luminance contrast. "
        "Alternative text enables people who are blind to access graphical information."
    )
    # Should not raise
    assert_social_model_language(clean)


@pytest.mark.parametrize("term", DISALLOWED_MEDICAL_TERMS)
def test_assert_social_model_language_raises_on_disallowed_terms(term):
    text = f"This document contains barriers for a {term} in modern workflows."
    with pytest.raises(AssertionError, match="Language violation"):
        assert_social_model_language(text)


def test_who_map_and_acrobat_notes_are_populated():
    assert len(WHO_MAP) > 0
    assert "image-alt-missing" in WHO_MAP
    assert "tag-tree-missing" in ACROBAT_ASSISTANT_NOTES
    assert "color-contrast" in ACROBAT_ASSISTANT_NOTES

    # Ensure all strings in WHO_MAP and ACROBAT_ASSISTANT_NOTES satisfy social model
    for k, v in WHO_MAP.items():
        assert_social_model_language(v)
    for k, v in ACROBAT_ASSISTANT_NOTES.items():
        assert_social_model_language(v)
