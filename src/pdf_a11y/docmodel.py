"""Document model: one open, in-memory PDF shared by audit rules and remediation.

Built on pikepdf (low-level object surgery). Reads only; fixes go through the
explicit set_* / structure-tree helpers. pikepdf 10.x gotchas handled here:

  * every dictionary key MUST be a PdfName with a leading '/', so both
    ``member`` (tests) and ``key`` (builds) normalize;
  * ``open_metadata()`` must be used as a context manager to mutate XMP;
  * stream content is read with ``read_bytes()`` (filters auto-applied).
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pikepdf


def member(d, key):
    """True if pikepdf dict/stream ``d`` contains ``key`` (slash-normalized)."""
    if d is None:
        return False
    if not isinstance(key, str):
        key = str(key)
    if not key.startswith("/"):
        key = "/" + key
    try:
        return key in d
    except TypeError:
        return False


def key(d, key):
    """Dict entry or None, with slash-normalized keys."""
    if d is None:
        return None
    if not isinstance(key, str):
        key = str(key)
    if not key.startswith("/"):
        key = "/" + key
    try:
        return d[key]
    except (TypeError, KeyError, IndexError):
        return None


def new_dict(pairs=None):
    """pikepdf.Dictionary with all keys normalized to '/...' form."""
    out = {}
    for k, v in (pairs or {}).items():
        if not isinstance(k, str):
            k = str(k)
        if not k.startswith("/"):
            k = "/" + k
        out[k] = v
    return pikepdf.Dictionary(out)


def norm_name(s):
    """'/H1' -> 'H1'; '/Image28' -> 'Image28'; None -> None."""
    if s is None:
        return None
    s = str(s)
    return s[1:] if s.startswith("/") else s


def _xobj_images(doc, page_no, page):
    """Resolve page images including Resources inherited from /Pages nodes.

    Returns list of (xobj_name, image_dict, declaring_resource, declaring_owner).
    declaring_owner is the page or ancestor node that owns the dict, so fixes
    mutate the right place.
    """
    out = []
    chain = []  # (resource, owner) from page up to root
    node = page
    while node is not None:
        res = key(node, "Resources")
        if res is not None:
            chain.append((res, node))
        node = key(node, "Parent")
    seen = set()
    for res, owner in reversed(chain):  # page-local wins over ancestors
        xobjs = key(res, "XObject")
        if xobjs is None:
            continue
        for nm, obj in xobjs.items():
            name = norm_name(nm)
            if name in seen:
                continue
            if str(key(obj, "Subtype")) == "/Image":
                seen.add(name)
                out.append((name, obj, res, owner))
    return out


@dataclass
class OutlineEntry:
    level: int
    title: str
    page: int  # 0-based


@dataclass
class DocModel:
    path: Path
    doc: pikepdf.Pdf
    catalog: object
    pages: list
    images: list = field(default_factory=list)     # [(page, name, obj, res, owner)]
    outlines: list = field(default_factory=list)   # [OutlineEntry]
    _meta: Optional[object] = field(default=None, repr=False)

    # -- lifecycle ----------------------------------------------------------
    @classmethod
    def open(cls, path) -> "DocModel":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        doc = pikepdf.open(str(path))
        m = cls(path, doc, doc.Root, list(doc.pages))
        m._load()
        return m

    def _load(self):
        for pi, page in enumerate(self.pages):
            for name, obj, res, owner in _xobj_images(self.doc, pi, page):
                self.images.append((pi, name, obj, res, owner))
        self.outlines = self._load_outline()

    def close(self):
        try:
            self.doc.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- reading helpers ------------------------------------------------------
    def _load_outline(self):
        out = []
        ol = key(self.catalog, "Outlines")
        first = key(ol, "First")
        cur, n = first, 0
        while cur is not None and n < 10000:
            try:
                lvl = self._outline_level(ol, cur)
                title = str(key(cur, "Title") or "")
                page_no = self._dest_page(key(cur, "Dest"))
                if title:
                    out.append(OutlineEntry(lvl, title, page_no))
            except Exception:
                pass
            nxt = key(cur, "Next")
            if nxt is None and nxt == cur:
                break
            cur = nxt
            n += 1
        return out

    def _outline_level(self, ol, item):
        depth = 0
        node = item
        while node is not None:
            node = key(node, "Parent")
            depth += 1
            if node is None or node is ol:
                break
            # guard against cycles
            if depth > 64:
                break
        return max(1, min(depth, 64))

    def _dest_page(self, dest) -> int:
        """Resolve /Dest (explicit array or name) to a 0-based page index."""
        if dest is None:
            return 0
        d = dest
        # name destinations: /Dest may be a name -> resolve via Dests
        if not isinstance(d, list):
            name = norm_name(d)
            for bag in (key(self.catalog, "Dests"), key(self.doc.trailer, "Dests")):
                if bag is not None and member(bag, name):
                    d = key(bag, name)
                    break
            if not isinstance(d, list):
                return 0
        page_ref = d[0]
        for i, p in enumerate(self.pages):
            if p is page_ref:
                return i
        return 0

    def content_bdc_counts(self):
        """(bdc, emc, marked_image_count) over all page content streams."""
        bdc = emc = img_refs = 0
        for page in self.pages:
            for data in self._page_content_bytes(page):
                s = data.decode("latin-1", "replace")
                bdc += len(re.findall(r"(?<![A-Za-z])BDC(?![A-Za-z])", s))
                emc += len(re.findall(r"(?<![A-Za-z])EMC(?![A-Za-z])", s))
                img_refs += len(re.findall(r"^\s*/\S+\s+Do\s*$", s, re.M))
        return bdc, emc, img_refs

    def _page_content_bytes(self, page):
        c = key(page, "Contents")
        if c is None:
            return []
        try:
            if isinstance(c, pikepdf.Array):
                return [bytes(x.read_bytes()) for x in c]
            return [bytes(c.read_bytes())]
        except Exception:
            return []

    def has_lang(self):
        v = key(self.catalog, "Lang")
        if v is None:
            return False
        return bool(str(v).strip())

    def lang(self):
        v = key(self.catalog, "Lang")
        return str(v).strip() if v is not None else None

    def is_marked(self):
        mi = key(self.catalog, "MarkInfo")
        if mi is None:
            return False
        return bool(key(mi, "Marked"))

    def display_doc_title(self):
        vp = key(self.catalog, "ViewerPreferences")
        if vp is None:
            return False
        return bool(key(vp, "DisplayDocTitle"))

    def info_title(self):
        info = key(self.doc.trailer, "Info")
        if info is None:
            return None
        t = key(info, "Title")
        return str(t).strip() if t is not None else None

    def xmp_title(self):
        with self._meta_ro() as meta:
            v = meta.get("dc:title")
        try:
            return str(v).strip() if v else None
        except Exception:
            return None

    def title(self):
        """Best-known document title: /Info, then XMP, then None."""
        t = self.info_title()
        if t:
            return t
        t = self.xmp_title()
        if t:
            return t
        return None

    def struct_tree(self):
        st = key(self.catalog, "StructTreeRoot")
        return st if st is not None else None

    def walk_struct(self, st):
        """Yield (depth, S_name, alt, has_P, element_or_mcid) for the K tree."""
        def rec(k, depth):
            K = key(k, "K")
            kids = K if isinstance(K, pikepdf.Array) else ([K] if K is not None else [])
            for child in kids:
                if isinstance(child, pikepdf.Array):
                    yield from rec(child, depth + 1)
                elif isinstance(child, int):
                    yield (depth, None, None, True, child)
                else:
                    alt = key(child, "Alt")
                    has_p = member(child, "P")
                    yield (depth, norm_name(key(child, "S")),
                           str(alt) if alt is not None else None, has_p, child)
                    yield from rec(child, depth + 1)
        yield from rec(st, 0)

    def heading_levels(self, st):
        """(level, alt) in document order for /H1../H6 structural elements."""
        out = []
        for _, s, alt, _, _ in self.walk_struct(st):
            if s and re.fullmatch(r"H[1-6]", s):
                out.append((int(s[1]), str(alt or "")))
        return out

    def table_stats(self, st):
        """Rows: (table_idx, n_rows, n_header_rows) for /Table elements."""
        tables = []
        ti = 0
        def rec(k):
            nonlocal ti
            K = key(k, "K")
            kids = K if isinstance(K, pikepdf.Array) else ([K] if K is not None else [])
            for child in kids:
                if isinstance(child, pikepdf.Array):
                    rec(child)
                elif isinstance(child, int):
                    continue
                else:
                    s = norm_name(key(child, "S"))
                    if s == "Table":
                        ti += 1
                        nrows = nh = 0
                        for _, cs, _, _, _ in self.walk_struct(child):
                            if cs == "TR":
                                nrows += 1
                            elif cs == "TH":
                                nh += 1
                        tables.append((ti, nrows, nh))
                    rec(child)
        rec(st)
        return tables

    def image_alt(self, img_obj):
        a = key(img_obj, "Alt")
        return str(a).strip() if a is not None else None

    # -- writing helpers (remediation) ----------------------------------------
    def _meta_ro(self):
        m = self.doc.open_metadata(set_pikepdf_as_editor=False)
        return m

    def set_lang(self, code):
        self.catalog["/Lang"] = code

    def set_marked(self, marked=True):
        mi = key(self.catalog, "MarkInfo")
        if mi is None:
            mi = new_dict({"/Marked": marked})
            self.catalog["/MarkInfo"] = mi
        else:
            mi["/Marked"] = True if marked else False

    def set_display_doc_title(self, on=True):
        vp = key(self.catalog, "ViewerPreferences")
        if vp is None:
            vp = new_dict({"/DisplayDocTitle": on})
            self.catalog["/ViewerPreferences"] = vp
        else:
            vp["/DisplayDocTitle"] = True if on else False

    def set_title(self, title):
        """Set /Info /Title and XMP dc:title to the same value."""
        if "/Info" not in self.doc.trailer:
            self.doc.trailer["/Info"] = new_dict()
        info = self.doc.trailer["/Info"]
        info["/Title"] = title
        meta = self.doc.open_metadata()
        with meta:
            meta["dc:title"] = title
        self._meta = None

    def set_image_alt(self, page_no, name, text, decorative=False):
        for (pi, nm, obj, res, owner) in self.images:
            if pi == page_no and nm == name:
                if decorative:
                    obj["/Type"] = "/Metadata"
                else:
                    obj["/Alt"] = text
                return True
        return False

    def set_outline(self, entries):
        """Set the document outline (TOC) in-memory (pure pikepdf, no second
        writer pass). entries: [(level, title, page_no_0based), ...].

        Builds a standard /Outlines tree: root /First//Last//Count, each item
        /Title//Dest//Parent, siblings linked by /Next, /Count = number of
        visible descendants (positive; all items open) or -1 for leaves.
        """
        if not entries or not self.pages:
            return False

        # Resolve dest per entry (top-left of the page).
        resolved = []
        for lvl, title, page_no in entries:
            page = self.pages[page_no] if 0 <= page_no < len(self.pages) else self.pages[0]
            top = 792.0
            try:
                mb = key(page, "MediaBox")
                if mb is not None:
                    top = float(mb[3])
            except Exception:
                pass
            dest = pikepdf.Array([page.obj, pikepdf.Name("/XYZ"), 0.0, top, 0])
            resolved.append((max(1, min(int(lvl), 64)), str(title), dest))

        n = len(resolved)
        # Build parent/children relationships from levels (a classic TOC
        # "mountain"). Level strictly increases along a parent chain.
        parent_of = [-1] * n
        children_of = [[] for _ in range(n)]
        stack = []  # indices with strictly increasing levels
        for i in range(n):
            while stack and resolved[stack[-1]][0] >= resolved[i][0]:
                stack.pop()
            if stack:
                p = stack[-1]
                parent_of[i] = p
                children_of[p].append(i)
            stack.append(i)

        # Visible-descendant count for an item = 1 (itself) + sum(children).
        memo = {}

        def count(i):
            if i in memo:
                return memo[i]
            c = children_of[i]
            memo[i] = 1 + sum(count(j) for j in c)
            return memo[i]

        root = self.doc.make_indirect(new_dict({"/Type": "/Outlines"}))
        node_objs = {}
        last_node = {}   # i -> last child node object (for /Next chaining)

        def build(i):
            """Create the node dict for item i, wire children, return the node."""
            node = self.doc.make_indirect(new_dict({"/Title": resolved[i][1],
                                                    "/Dest": resolved[i][2],
                                                    "/Parent": root}))
            node_objs[i] = node
            c = children_of[i]
            if c:
                built = []
                for j in c:
                    child_node = build(j)
                    built.append(child_node)
                node["/First"] = built[0]
                for jn, kn in zip(built, built[1:]):
                    jn["/Next"] = kn
                node["/Last"] = built[-1]
                node["/Count"] = pikepdf.Integer(count(i))
            else:
                node["/Count"] = pikepdf.Integer(-1)
            last_node[i] = node
            return node

        root_children = [i for i in range(n) if parent_of[i] == -1]
        if not root_children:
            return False
        prev = None
        for i in root_children:
            node = build(i)
            if prev is not None:
                prev["/Next"] = node
            prev = node
        root["/First"] = node_objs[root_children[0]]
        root["/Last"] = node_objs[root_children[-1]]
        root["/Count"] = pikepdf.Integer(sum(count(i) for i in root_children))
        self.catalog["/Outlines"] = root
        self.outlines = [OutlineEntry(lvl, title, page_no)
                         for (lvl, title, page_no) in entries]
        return True

    def save(self, out_path):
        out_path = Path(out_path)
        self.doc.save(str(out_path), linearize=False)
        self.path = out_path
        self.catalog = self.doc.Root
        self.pages = list(self.doc.pages)
        self._load()
