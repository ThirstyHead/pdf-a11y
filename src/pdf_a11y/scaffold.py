"""Deterministic tag-tree scaffolding for untagged PDFs.

Pure/deterministic: same input bytes -> same plan + same output stream. No AI.

Given an untagged PDF, scaffold:
  1. Splits each page's content stream into BT/ET text units (string-literal
     aware, tracking the graphics-state CTM via q/Q/cm).
  2. Measures each unit (device font size + baseline position) and matches a
     PyMuPDF span to recover the rendered text (Alt).
  3. Assigns structure roles (H1..H6/P) from font-size tiers.
  4. Emits a plan that ``DocModel.build_scaffold`` turns into a StructTreeRoot
     + BDC/EMC marked content, making the document tagged.

A scaffolded document passes this tool's audit but is a deterministic
best-effort structure (reading order follows the content stream). Review it in
a tag editor before PDF/UA certification.
"""
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Tuple

IDENTITY: Tuple[float, float, float, float, float, float] = (
    1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# Byte sets for the content-stream scanner.
_WS = {0x20, 0x09, 0x0A, 0x0D, 0x00, 0x0C}
_DELIM = {0x20, 0x09, 0x0A, 0x0D, 0x00, 0x0C,
          0x28, 0x29, 0x3C, 0x3E, 0x5B, 0x5D, 0x7B, 0x7D, 0x2F, 0x25}


def _is_digit(b: int) -> bool:
    return 0x30 <= b <= 0x39


def _is_number_start(b: int, data: bytes, i: int) -> bool:
    if _is_digit(b) or b == 0x2E:  # digit or '.'
        return True
    if b in (0x2B, 0x2D):  # '+' / '-' only if followed by digit or '.'
        j = i + 1
        return j < len(data) and (_is_digit(data[j]) or data[j] == 0x2E)
    return False


# -- matrix helpers (PDF 2x3: a b c d e f) ------------------------------------
def _mat_mul(m1, m2):
    """m1 * m2 (PDF matrix concatenation), both 2x3 tuples."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _mat_point(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _mat_scale_x(m):
    a, b = m[0], m[1]
    return (a * a + b * b) ** 0.5


# -- content-stream scanner ----------------------------------------------------
def _scan(data: bytes) -> List[dict]:
    """Single-pass scan of a page content stream.

    Returns one record per top-level BT..ET span:
      {"start": off_of_BT, "end": off_past_ET, "ctm": ..., "tm": ..., "tf": ...}

    String-literal/hex/comment/name aware, so BT/ET inside data are ignored.
    Tracks the graphics-state CTM (q/Q/cm) and, per unit, the last Tm and Tf.
    A BT with no closing ET yields nothing.
    """
    units: List[dict] = []
    n = len(data)
    i = 0
    ctm_stack = [IDENTITY]
    nums: List[float] = []
    in_unit = False
    unit_start = 0
    unit_ctm = IDENTITY
    unit_tm = IDENTITY
    unit_tf = 1.0
    ldepth = 0
    state = 0  # 0 normal, 1 literal, 2 hex, 3 comment
    while i < n:
        ch = data[i]
        if state == 0:
            if ch == 0x28:  # '(' literal string
                state, ldepth = 1, 1
                i += 1
                continue
            if ch == 0x3C:  # '<' hex string or dict '<<'
                if i + 1 < n and data[i + 1] == 0x3C:
                    i += 2
                    continue
                state = 2
                i += 1
                continue
            if ch == 0x3E:  # '>' or '>>'
                if i + 1 < n and data[i + 1] == 0x3E:
                    i += 2
                    continue
                i += 1
                continue
            if ch == 0x25:  # '%' comment
                state = 3
                i += 1
                continue
            if ch == 0x2F:  # '/' name
                i += 1
                while i < n and data[i] not in _DELIM:
                    i += 1
                continue
            if ch in _WS or ch in (0x5B, 0x5D, 0x7B, 0x7D):
                i += 1
                continue
            if _is_number_start(ch, data, i):
                j = i
                if data[j] in (0x2B, 0x2D):
                    j += 1
                while j < n and (_is_digit(data[j]) or data[j] == 0x2E):
                    j += 1
                try:
                    nums.append(float(data[i:j].decode("latin-1")))
                except ValueError:
                    pass
                if len(nums) > 16:
                    nums.pop(0)
                i = j
                continue
            # operator word
            wstart = i
            j = i
            while j < n and data[j] not in _DELIM:
                j += 1
            word = data[i:j].decode("latin-1", "replace")
            i = j
            if word == "BT":
                if not in_unit:
                    in_unit = True
                    unit_start = wstart
                    unit_ctm = ctm_stack[-1]
                    unit_tm = IDENTITY
                    unit_tf = 1.0
            elif word == "ET":
                if in_unit:
                    units.append({"start": unit_start, "end": i,
                                  "ctm": unit_ctm, "tm": unit_tm, "tf": unit_tf})
                    in_unit = False
            elif word == "Tm" and in_unit:
                if len(nums) >= 6:
                    unit_tm = tuple(nums[-6:])
            elif word == "Tf" and in_unit:
                if len(nums) >= 1:
                    unit_tf = nums[-1]
            elif word == "cm":
                if len(nums) >= 6:
                    ctm_stack[-1] = _mat_mul(tuple(nums[-6:]), ctm_stack[-1])
            elif word == "q":
                ctm_stack.append(ctm_stack[-1])
            elif word == "Q":
                if len(ctm_stack) > 1:
                    ctm_stack.pop()
            continue
        if state == 1:  # literal string
            if ch == 0x5C:  # backslash escapes next byte
                i += 2
                continue
            if ch == 0x28:  # nested '('
                ldepth += 1
                i += 1
                continue
            if ch == 0x29:  # ')'
                ldepth -= 1
                if ldepth <= 0:
                    state = 0
                i += 1
                continue
            i += 1
            continue
        if state == 2:  # hex string
            if ch == 0x3E:
                state = 0
            i += 1
            continue
        if state == 3:  # comment
            if ch == 0x0A:
                state = 0
            i += 1
            continue
    return units


def _scan_units(data: bytes) -> List[dict]:
    """Scan a page content stream into one record per text object (line).

    Unlike ``_scan`` (one record per top-level BT..ET span), this emits a unit
    for each text object so that producers that pack several lines into a
    single BT..ET (PyMuPDF Story, WeasyPrint) scaffold correctly. A text
    object begins at a ``Tm`` or ``Td`` and runs to the next ``Tm``/``Td`` (or
    ``ET``). ``Tf`` is graphics state and persists across BT/ET, so each unit
    records the size in effect at the object's first text-painting op — not a
    per-block value that resets at BT (which is what made inherited-font lines
    read as 1.0pt).

    Returns records ``{"start","end","ctm","tm","tf"}`` in stream order whose
    ``[start,end)`` regions tile each BT..ET span (non-overlapping, strictly
    increasing) so ``DocModel.build_scaffold`` can wrap each in BDC/EMC. ``tm``
    is the text matrix (the ``Tm`` value, or IDENTITY for ``Td``-positioned
    objects, matching the historical Td behavior). A BT..ET with no Tm/Td
    yields a single unit spanning the whole block.
    """
    units: List[dict] = []
    n = len(data)
    i = 0
    ctm_stack = [IDENTITY]
    nums: List[float] = []
    group_start = -1          # offset of the current operator's first operand
    tf = 1.0                  # persistent font size (graphics state)
    in_bt = False
    bt_start = 0
    objs: List[dict] = []     # completed text objects of the current block
    obj: Dict[str, Any] = {}  # the text object being accumulated
    ldepth = 0
    state = 0  # 0 normal, 1 literal, 2 hex, 3 comment
    while i < n:
        ch = data[i]
        if state == 0:
            if ch == 0x28:  # '(' literal string
                state, ldepth = 1, 1
                i += 1
                continue
            if ch == 0x3C:  # '<' hex string or dict '<<'
                if i + 1 < n and data[i + 1] == 0x3C:
                    i += 2
                    continue
                state = 2
                i += 1
                continue
            if ch == 0x3E:  # '>' or '>>'
                if i + 1 < n and data[i + 1] == 0x3E:
                    i += 2
                    continue
                i += 1
                continue
            if ch == 0x25:  # '%' comment
                state = 3
                i += 1
                continue
            if ch == 0x2F:  # '/' name
                i += 1
                while i < n and data[i] not in _DELIM:
                    i += 1
                continue
            if ch in _WS or ch in (0x5B, 0x5D, 0x7B, 0x7D):
                i += 1
                continue
            if _is_number_start(ch, data, i):
                if group_start < 0:
                    group_start = i
                j = i
                if data[j] in (0x2B, 0x2D):
                    j += 1
                while j < n and (_is_digit(data[j]) or data[j] == 0x2E):
                    j += 1
                try:
                    nums.append(float(data[i:j].decode("latin-1")))
                except ValueError:
                    pass
                if len(nums) > 16:
                    nums.pop(0)
                i = j
                continue
            # operator word
            wstart = i
            j = i
            while j < n and data[j] not in _DELIM:
                j += 1
            word = data[i:j].decode("latin-1", "replace")
            i = j
            op_start = group_start if group_start >= 0 else wstart
            if word == "BT":
                in_bt = True
                bt_start = op_start
                objs = []
                obj = {}
            elif word == "ET":
                if in_bt:
                    if obj:
                        objs.append(obj)
                    ctm = ctm_stack[-1]
                    if not objs:
                        # no Tm/Td in the block: one unit for the whole span
                        units.append({"start": bt_start, "end": i,
                                      "ctm": ctm, "tm": IDENTITY, "tf": tf})
                    else:
                        for k in range(len(objs)):
                            s = objs[k]["start"]
                            e = (objs[k + 1]["start"]
                                 if k + 1 < len(objs) else i)
                            otf = objs[k]["tf"]
                            units.append({"start": s, "end": e,
                                          "ctm": objs[k]["ctm"],
                                          "tm": objs[k]["tm"],
                                          "tf": otf if otf is not None else tf})
                    in_bt = False
                    obj = {}
            elif word == "Tm" and in_bt:
                if len(nums) >= 6:
                    if obj:
                        objs.append(obj)
                    obj = {"start": op_start, "tm": tuple(nums[-6:]),
                           "ctm": ctm_stack[-1], "tf": None}
            elif word == "Td" and in_bt:
                if len(nums) >= 2:
                    if obj:
                        objs.append(obj)
                    # Td is a relative move; keep tm=IDENTITY (historical Td
                    # behavior) so Td-based documents scaffold as before.
                    obj = {"start": op_start, "tm": IDENTITY,
                           "ctm": ctm_stack[-1], "tf": None}
            elif word == "Tf":
                if len(nums) >= 1:
                    tf = nums[-1]
            elif word in ("Tj", "TJ", "'", '"') and in_bt:
                # first text-paint of the object fixes its font size
                if obj and obj.get("tf") is None:
                    obj["tf"] = tf
            elif word == "cm":
                if len(nums) >= 6:
                    ctm_stack[-1] = _mat_mul(tuple(nums[-6:]), ctm_stack[-1])
            elif word == "q":
                ctm_stack.append(ctm_stack[-1])
            elif word == "Q":
                if len(ctm_stack) > 1:
                    ctm_stack.pop()
            nums = []
            group_start = -1
            continue
        if state == 1:  # literal string
            if ch == 0x5C:  # backslash escapes next byte
                i += 2
                continue
            if ch == 0x28:  # nested '('
                ldepth += 1
                i += 1
                continue
            if ch == 0x29:  # ')'
                ldepth -= 1
                if ldepth <= 0:
                    state = 0
                i += 1
                continue
            i += 1
            continue
        if state == 2:  # hex string
            if ch == 0x3E:
                state = 0
            i += 1
            continue
        if state == 3:  # comment
            if ch == 0x0A:
                state = 0
            i += 1
            continue
    return units


def split_text_units(data: bytes) -> List[slice]:
    """Return slices of the top-level BT..ET spans in ``data`` (string-aware)."""
    return [slice(u["start"], u["end"]) for u in _scan(data)]


# -- units, blocks, plans ------------------------------------------------------
@dataclass
class TextUnit:
    page: int
    start: int
    end: int
    ctm: Tuple[float, ...] = IDENTITY
    tm: Tuple[float, ...] = IDENTITY
    tf: float = 1.0
    alt: str = ""


@dataclass
class Block:
    unit: TextUnit
    role: str  # "H1".."H6" or "P"


@dataclass
class ScaffoldPlan:
    blocks: List[Block] = field(default_factory=list)

    def blocks_by_page(self) -> Dict[int, List[Block]]:
        out: Dict[int, List[Block]] = {}
        for b in self.blocks:
            out.setdefault(b.unit.page, []).append(b)
        return out

    def headings(self) -> List[Block]:
        return [b for b in self.blocks if b.role.startswith("H")]


def unit_device_size(unit: TextUnit) -> float:
    """Rendered font size in device points (Tf * |CTM*Tm| x-scale)."""
    eff = _mat_mul(unit.ctm, unit.tm)
    return unit.tf * _mat_scale_x(eff)


def extract_units(doc_path) -> List[TextUnit]:
    """All text units in (page, stream) order for the whole document.

    One unit per text object (``Tm``/``Td``-positioned line), so producers
    that pack many lines into a single ``BT..ET`` (PyMuPDF Story,
    WeasyPrint) scaffold correctly. ``tf`` is the font size in effect at the
    object's first draw — persistent across ``BT``/``ET`` — never a reset
    1.0 for inherited-font lines.
    """
    from .docmodel import key
    import pikepdf
    with pikepdf.open(str(Path(doc_path))) as doc:
        units: List[TextUnit] = []
        for pi, page in enumerate(doc.pages):
            c = key(page, "Contents")
            if c is None:
                continue
            if isinstance(c, pikepdf.Array):
                data = b"".join(bytes(x.read_bytes()) for x in c)
            else:
                data = bytes(c.read_bytes())
            for u in _scan_units(data):
                units.append(TextUnit(page=pi, start=u["start"], end=u["end"],
                                      ctm=u["ctm"], tm=u["tm"], tf=u["tf"]))
    return units


def fill_unit_alt(units: List[TextUnit], doc_path) -> None:
    """Match each unit to a PyMuPDF span by (page, baseline +/-2pt,
    size +/-0.25); set unit.alt to the span text. No match -> alt stays ''."""
    import pymupdf
    with pymupdf.open(str(Path(doc_path))) as pdf:
        heights = [pdf[pi].rect.height for pi in range(len(pdf))]
        spans_by_page: List[List[dict]] = []
        for pi in range(len(pdf)):
            td: Any = pdf[pi].get_text("dict")  # dict, not str, per fitz docs
            spans = []
            for blk in td["blocks"]:
                for line in blk.get("lines", []):
                    for s in line["spans"]:
                        spans.append(s)
            spans_by_page.append(spans)
        for u in units:
            eff = _mat_mul(u.ctm, u.tm)
            ox, oy = _mat_point(eff, 0, 0)
            u_y = heights[u.page] - oy
            u_x = ox  # device x (bottom-up), fitz uses the same x origin
            u_size = unit_device_size(u)
            # Match spans on the same line (baseline) and size, x-overlap >= 30%,
            # preferring spans that start within 6pt of the unit origin (so a
            # unit rendered after a hanging bullet/marker keeps its own text,
            # and a marker-only unit keeps its marker).
            best: List[dict] = []
            for s in spans_by_page[u.page]:
                if not s["text"].strip():
                    continue
                if abs(s["origin"][1] - u_y) >= 2.0:
                    continue
                if abs(s["size"] - u_size) >= 0.25:
                    continue
                x0, x1 = s["bbox"][0], s["bbox"][2]
                # A unit renders one line; its on-page width is the span's own
                # width when the span starts at the unit origin (a full-line
                # heading/paragraph), else the historical 60pt window (so a
                # hanging bullet/marker unit keeps its short marker).
                unit_right = x1 if abs(x0 - u_x) <= 6.0 else u_x + 60.0
                overlap = max(0.0, min(x1, unit_right) - max(x0, u_x))
                span_w = max(1.0, x1 - x0)
                if overlap < 0.3 * span_w:
                    continue
                best.append(s)
            if best:
                def _start(s: dict) -> float:
                    return abs(s["bbox"][0] - u_x)
                # start-near, then widest (full text over a short lead-in)
                best.sort(key=lambda s: (round(_start(s), 1),
                                         -(s["bbox"][2] - s["bbox"][0]),
                                         s["bbox"][0]))
                u.alt = best[0]["text"].strip()


def _assign_roles(units: List[TextUnit]) -> List[Block]:
    """Size tiers -> roles. Body = median size; a size is a heading tier if
    >= 1.3x body (ranked, capped at 6); everything else (and any 'heading'
    with no matched alt) is P."""
    sizes = [s for s in (unit_device_size(u) for u in units) if s > 0]
    if not sizes:
        return [Block(u, "P") for u in units]
    body = median(sizes)
    rounded = sorted({round(s * 2) / 2 for s in sizes}, reverse=True)
    tiers = [s for s in rounded if s >= 1.3 * body][:6]
    role_by_size = {s: f"H{i + 1}" for i, s in enumerate(tiers)}
    blocks = []
    for u in units:
        ds = unit_device_size(u)
        rs = round(ds * 2) / 2 if ds > 0 else 0
        role = role_by_size.get(rs, "P")
        if role != "P" and not u.alt.strip():
            role = "P"
        blocks.append(Block(u, role))
    return blocks


def build_plan(doc_path) -> ScaffoldPlan:
    """Extract units, fill Alt from PyMuPDF spans, and plan roles."""
    units = extract_units(doc_path)
    fill_unit_alt(units, doc_path)
    return ScaffoldPlan(blocks=_assign_roles(units))