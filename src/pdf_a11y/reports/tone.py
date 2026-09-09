"""Social model language assertions, persona impact mappings, and Acrobat notes."""
import re
from typing import Dict

WHO_MAP: Dict[str, str] = {
    "title-missing": "Screen reader navigators and cognitive users identifying open document context",
    "display-doctitle-off": "Screen reader navigators expecting window title bars to state the document name",
    "language-missing": "Text-to-speech synthesizers selecting correct pronunciation rules and phonemes",
    "language-malformed": "Text-to-speech synthesizers selecting correct pronunciation rules and phonemes",
    "tag-tree-missing": "Assistive technologies requiring structured DOM trees for linear document reading",
    "tag-tree-weak": "Screen reader navigators needing predictable parent-child element relationships",
    "image-alt-missing": "Blind and low-vision readers who rely on text descriptions for graphical content",
    "decorative-undeclared": "Screen reader users subjected to unnecessary speech clutter from decorative assets",
    "media-no-alt": "Assistive technology users encountering embedded audio/video elements",
    "outline-missing": "Keyboard and screen reader navigators jumping between major document sections",
    "color-contrast": "Low-vision and color-blind readers requiring sufficient luminance contrast against page background",
    "link-text-vague": "Screen reader users navigating via standalone 'Links List' dialogs",
}

# SC-based WHO mappings for WCAG criteria
SC_WHO_MAP: Dict[str, str] = {
    "1.1.1": "People who are blind or have low vision and rely on screen readers or braille displays",
    "1.2.1": "People who are deaf or hard of hearing (captions) and people who are blind (audio descriptions)",
    "1.3.1": "People who use screen readers or rely on clear, predictable structure to read",
    "1.3.2": "People who use screen readers or keyboard navigation experiencing content in logical reading order",
    "1.4.3": "People with low vision, color vision differences, or reading in bright light",
    "1.4.12": "People who need expanded line, word, or letter spacing to read comfortably",
    "2.4.1": "People who navigate by structure and skip repeated material",
    "2.4.2": "People who rely on document titles to identify and distinguish materials",
    "2.4.4": "People who choose links from a list or listen to links out of context",
    "2.4.5": "Keyboard and screen reader navigators using bookmarks and outlines to locate sections",
    "3.1.1": "People using speech-to-text, automated translation, or screen readers with correct pronunciation",
    "4.1.2": "People using assistive technologies requiring standard names, roles, and values",
}

ACROBAT_ASSISTANT_NOTES: Dict[str, str] = {
    "tag-tree-missing": (
        "Adobe Acrobat Pro's built-in Accessibility Checker passes documents with minimal tags even if "
        "untagged content annotations exist on the page. Under PDF/UA-1 and WCAG 2.1 SC 1.3.1, every "
        "meaningful content element must belong to a formal Structure Tree Root."
    ),
    "title-missing": (
        "Adobe Acrobat often checks metadata dictionaries for a title string without verifying whether "
        "the ViewerPreferences dictionary specifies /DisplayDocTitle true. WCAG 2.1 SC 2.4.2 requires "
        "both the title metadata and window bar display flag to be enabled."
    ),
    "color-contrast": (
        "Adobe Acrobat Pro's built-in Accessibility Checker does not automatically evaluate text contrast "
        "across rendered PDF content streams, delegating contrast entirely to manual user verification. "
        "Under WCAG 2.1 SC 1.4.3, automated contrast validation must verify a minimum 4.5:1 ratio."
    ),
    "outline-missing": (
        "Adobe Acrobat Pro only warns for missing bookmarks/outlines on documents exceeding 20 pages. "
        "However, under WCAG 2.1 SC 2.4.5, multi-page reference documents require outline hierarchies "
        "regardless of arbitrary page thresholds."
    ),
}

DISALLOWED_MEDICAL_TERMS = [
    "suffering from",
    "afflicted with",
    "confined to a wheelchair",
    "wheelchair-bound",
    "retarded",
    "handicapped",
    "invalid",
    "normal person",
    "normal people",
    "healthy person",
    "crippled",
    "victim of",
]


def assert_social_model_language(text: str) -> None:
    """Enforces social model of disability language across all generated reporting text."""
    lower = text.lower()
    for term in DISALLOWED_MEDICAL_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", lower):
            raise AssertionError(f"Language violation: Found outdated or medicalized deficit term '{term}'")
