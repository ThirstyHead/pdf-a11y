"""Canonical W3C WCAG 2.2 metadata, Understanding URLs, and POUR taxonomy for PDF."""

W3C_UNDERSTANDING = "https://www.w3.org/WAI/WCAG22/Understanding/"
W3C_UNDERSTANDING_BASE = W3C_UNDERSTANDING
W3C_QUICKREF = "https://www.w3.org/WAI/WCAG22/quickref/"

# sc -> (name, level, pour, w3c_url).
# POUR is derived from the SC first digit; 4.x (Robust) is never emitted by
# a rule today — it always renders as "not applicable".
SC_META = {
    "1.1.1": ("Non-text Content", "A", "1 Perceivable",
              W3C_UNDERSTANDING + "non-text-content.html"),
    "1.2.1": ("Audio-only and Video-only (Prerecorded)", "A", "1 Perceivable",
              W3C_UNDERSTANDING + "audio-only-and-video-only-prerecorded.html"),
    "1.3.1": ("Info and Relationships", "A", "1 Perceivable",
              W3C_UNDERSTANDING + "info-and-relationships.html"),
    "1.4.3": ("Contrast (Minimum)", "AA", "1 Perceivable",
              W3C_UNDERSTANDING + "contrast-minimum.html"),
    "1.4.12": ("Text Spacing", "AA", "1 Perceivable",
               W3C_UNDERSTANDING + "text-spacing.html"),
    "2.4.1": ("Bypass Blocks", "A", "2 Operable",
              W3C_UNDERSTANDING + "bypass-blocks.html"),
    "2.4.2": ("Page Titled", "A", "2 Operable",
              W3C_UNDERSTANDING + "page-titled.html"),
    "2.4.4": ("Link Purpose (In Context)", "A", "2 Operable",
              W3C_UNDERSTANDING + "link-purpose-in-context.html"),
    "3.1.1": ("Language of Page", "A", "3 Understandable",
              W3C_UNDERSTANDING + "language-of-page.html"),
}

PRINCIPLES = [
    ("1", "Perceivable"),
    ("2", "Operable"),
    ("3", "Understandable"),
    ("4", "Robust"),
]

POUR_ORDER = ["1", "2", "3", "4"]

POUR_INTROS = {
    "1": ("Perceivable — content only works if people can perceive it: "
          "text alternatives for non-text, captions and transcripts for "
          "media, and contrast and spacing that real eyes can work with."),
    "2": ("Operable — the document should let everyone get around it: a "
          "structure to navigate by, a title to identify it, and link names "
          "that say where they lead."),
    "3": ("Understandable — content should make sense as it is presented, "
          "including declaring the language it is written in."),
    "4": ("Robust — well-formed, consistently structured content keeps "
          "working across assistive technologies as they evolve."),
}
