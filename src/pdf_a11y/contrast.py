"""WCAG relative-luminance contrast math.

Uses the wcag-contrast-ratio library when available; otherwise falls back
to an equivalent W3C implementation so the package works with zero deps
beyond the PDF stack.
"""
from typing import Optional, Tuple


def hex_to_rgb(hexstr: str) -> Optional[Tuple[int, int, int]]:
    """Parse '#RRGGBB' or 'RRGGBB' into (r, g, b) ints, or None if malformed."""
    if hexstr is None:
        return None
    s = hexstr.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


def _lum_impl(fg: Tuple[int, int, int], bg: Tuple[int, int, int]) -> float:
    def L(rgb):
        chans = []
        for c in rgb:
            cs = c / 255.0
            chans.append(cs / 12.92 if cs <= 0.04045 else ((cs + 0.055) / 1.055) ** 2.4)
        return 0.2126 * chans[0] + 0.7152 * chans[1] + 0.0722 * chans[2]

    l1, l2 = L(fg), L(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def contrast_ratio(fg, bg) -> float:
    """Return WCAG contrast ratio (1.0..21.0) between two (r, g, b) tuples."""
    try:
        import wcag_contrast_ratio  # noqa: F401
        from wcag_contrast_ratio import relative_luminance  # type: ignore
        l1 = relative_luminance("#%02X%02X%02X" % fg)
        l2 = relative_luminance("#%02X%02X%02X" % bg)
        hi, lo = max(l1, l2), min(l1, l2)
        return (hi + 0.05) / (lo + 0.05)
    except Exception:
        return _lum_impl(fg, bg)


THRESHOLD_NORMAL = 4.5   # WCAG 1.4.3 AA
THRESHOLD_LARGE = 3.0    # WCAG 1.4.3 AA large text