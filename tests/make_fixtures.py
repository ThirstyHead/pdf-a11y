#!/usr/bin/env python3
"""Build the committed PDF test fixtures. Run once, then commit the outputs.

    .venv/bin/python tests/make_fixtures.py

Fixtures (tests/fixtures/):
  clean.pdf         - tagged + marked + lang + title + displayDocTitle + outline
                      + image /Alt + balanced BDC/EMC; expect 0 findings
  fixable.pdf       - untagged; missing lang/title/displayDocTitle/outline;
                      image w/o Alt; expect 6 findings (tagging itself is the
                      unfixable root cause in 0.1.0)
  violations.pdf    - tagged but weak: heading level skip (H1->H3) and a table
                      row without TH; expect exactly 2 tag-tree-weak findings
  marked-notree.pdf - /Marked true but no StructTreeRoot;
                      expect exactly one 1.3.1 finding (tag-tree-missing)
  tagged-nooutline.pdf - tagged + marked + complete catalog but NO outline;
                      headings exist in the tree, so outline-missing is the
                      only finding and it is derivable (fixable=True)
  bread.pdf         - copy of examples/No Knead Bread-print.pdf (real-world sample)

All fixtures are generated with pikepdf only (base-14 Helvetica, no embedding),
so CI is hermetic: no external downloads, no AI in the loop.

Note: pikepdf refuses to overwrite an open input file, so each builder writes
the base doc to a temp path, closes it, then applies DocModel mutations and
saves the final bytes in one pass.
"""
import shutil
from pathlib import Path

import pikepdf

from pdf_a11y.docmodel import DocModel, new_dict

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
FIX.mkdir(exist_ok=True)

# -- content streams ----------------------------------------------------------
# Plain (no marked content): for fixable / marked-notree.
CONTENT_PLAIN = (
    b"q\n"
    b"BT /F1 18 Tf 72 720 Td (Big Title) Tj ET\n"
    b"BT /F1 12 Tf 72 692 Td (Body text line one.) Tj 0 -16 Td (Body text line two.) Tj ET\n"
    b"120 120 0 0 72 520 /Im1 Do\n"
    b"Q\n"
)

# Marked content (balanced BDC/EMC), one unit per structure element:
# M1 = H1, M2 = P, M3 = Figure (the image).
CONTENT_MARKED = (
    b"q\n"
    b"/M1 BDC BT /F1 18 Tf 72 720 Td (Big Title) Tj ET EMC\n"
    b"/M2 BDC BT /F1 12 Tf 72 692 Td (Body text line one.) Tj 0 -16 Td (Body text line two.) Tj ET EMC\n"
    b"/M3 BDC 120 120 0 0 72 520 /Im1 Do EMC\n"
    b"Q\n"
)

# violations: M1=H1, M2=H3, M3=P, M4/M5=TD (table has a row but no TH).
CONTENT_VIOLATIONS = (
    b"q\n"
    b"/M1 BDC BT /F1 18 Tf 72 720 Td (Section One) Tj ET EMC\n"
    b"/M2 BDC BT /F1 15 Tf 72 692 Td (Subsection) Tj ET EMC\n"
    b"/M3 BDC BT /F1 12 Tf 72 664 Td (Body paragraph text.) Tj ET EMC\n"
    b"/M4 BDC BT /F1 12 Tf 72 620 Td (Cell one) Tj ET EMC\n"
    b"/M5 BDC BT /F1 12 Tf 160 620 Td (Cell two) Tj ET EMC\n"
    b"Q\n"
)

# scan: a page that is ONLY an image (no BT/Tj text) -> 0 extractable text (a "scan").
CONTENT_SCAN = b"q\n120 120 0 0 72 520 /Im1 Do\nQ\n"


def _base_doc(content, with_image=True):
    """One-page PDF with Helvetica text (and optionally /Im1). Not saved."""
    doc = pikepdf.new()
    res = {"/Font": pikepdf.Dictionary({"/F1": pikepdf.Name("/Helvetica")})}
    if with_image:
        # Raw 120x120 RGB image (pikepdf 10 has no pikepdf.Image helper).
        img = pikepdf.Stream(doc, b"\x00" * (120 * 120 * 3))
        img["/Type"] = pikepdf.Name("/XObject")
        img["/Subtype"] = pikepdf.Name("/Image")
        img["/Width"] = 120
        img["/Height"] = 120
        img["/ColorSpace"] = pikepdf.Name("/DeviceRGB")
        img["/BitsPerComponent"] = 8
        res["/XObject"] = pikepdf.Dictionary({"/Im1": img})
    page = pikepdf.Page(pikepdf.Dictionary({
        "/Type": pikepdf.Name("/Page"),
        "/MediaBox": pikepdf.Array([0, 0, 612, 792]),
        "/Resources": pikepdf.Dictionary(res),
        "/Contents": pikepdf.Stream(doc, content),
    }))
    doc.pages.append(page)
    return doc


def _tmp_path(name):
    return FIX / f"_tmp_{name}"


def _base_to_tmp(name, content, with_image=True):
    """Write the base doc to a temp path and return it (doc closed)."""
    path = _tmp_path(name)
    doc = _base_doc(content, with_image)
    doc.save(str(path))
    doc.close()
    return path


# -- structure-tree helpers ----------------------------------------------------

def _new_root_el(doc):
    """Document root element; /P points to itself (single-root document)."""
    root_el = doc.make_indirect(new_dict({
        "S": pikepdf.Name("/Document"),
        "K": pikepdf.Array([]),
    }))
    root_el["/P"] = root_el
    return root_el


def _make_el(doc, s, mcid, parent, alt=None):
    """Leaf structure element associated with marked-content id `mcid`."""
    d = {"S": pikepdf.Name(s), "K": mcid, "P": parent}
    if alt is not None:
        d["Alt"] = alt
    return doc.make_indirect(new_dict(d))


def _finalize_root(doc, root_el, mcids):
    """Attach StructTreeRoot (K, ParentTree, Mcids) to the catalog."""
    page_roots = new_dict({
        "Nums": pikepdf.Array([0, pikepdf.Array([root_el])])})
    str_tree_root = doc.make_indirect(new_dict({
        "Type": pikepdf.Name("/StructTreeRoot"),
        "K": root_el,
        "ParentTree": page_roots,
        "Mcids": pikepdf.Array(mcids),
    }))
    doc.Root["/StructTreeRoot"] = str_tree_root


# -- fixtures ------------------------------------------------------------------

def make_clean():
    """Tagged + marked + complete catalog + image /Alt + balanced BDC/EMC.
    Oracle: audit -> 0 findings, PASS."""
    final = FIX / "clean.pdf"
    tmp = _base_to_tmp("clean", CONTENT_MARKED)
    with DocModel.open(tmp) as dm:
        dm.set_lang("en")
        dm.set_title("Clean Fixture")
        dm.set_display_doc_title(True)
        dm.set_marked(True)
        dm.set_outline([(1, "Big Title", 0)])
        dm.set_image_alt(0, "Im1", "A square")
        pdoc = dm.doc
        root_el = _new_root_el(pdoc)
        h1 = _make_el(pdoc, "/H1", 1, root_el, alt="Big Title")
        p = _make_el(pdoc, "/P", 2, root_el)
        fig = _make_el(pdoc, "/Figure", 3, root_el, alt="A square")
        root_el["/K"] = pikepdf.Array([h1, p, fig])
        _finalize_root(pdoc, root_el, [1, 2, 3])
        dm.save(final)
    tmp.unlink()


def make_fixable():
    """Untagged, no lang/title/displayDocTitle/outline, image w/o /Alt.
    Oracle: audit -> exactly 6 findings (see test_fixable_finding_set)."""
    final = FIX / "fixable.pdf"
    tmp = _base_to_tmp("fixable", CONTENT_PLAIN)
    tmp.rename(final)


def make_marked_notree():
    """fixable + /MarkInfo /Marked true (inconsistent tagged claim).
    Oracle: exactly one 1.3.1 finding = tag-tree-missing."""
    final = FIX / "marked-notree.pdf"
    tmp = _base_to_tmp("marked-notree", CONTENT_PLAIN)
    with DocModel.open(tmp) as dm:
        dm.set_marked(True)
        dm.save(final)
    tmp.unlink()


def make_violations():
    """Tagged + marked + complete catalog, but a weak tree: H1->H3 skip and
    a table row without TH.
    Oracle: exactly 2 tag-tree-weak findings."""
    final = FIX / "violations.pdf"
    tmp = _base_to_tmp("violations", CONTENT_VIOLATIONS, with_image=False)
    with DocModel.open(tmp) as dm:
        dm.set_lang("en")
        dm.set_title("Violations Fixture")
        dm.set_display_doc_title(True)
        dm.set_marked(True)
        dm.set_outline([(1, "Section One", 0), (2, "Subsection", 0)])
        pdoc = dm.doc
        root_el = _new_root_el(pdoc)
        h1 = _make_el(pdoc, "/H1", 1, root_el, alt="Section One")
        h3 = _make_el(pdoc, "/H3", 2, root_el, alt="Subsection")
        p = _make_el(pdoc, "/P", 3, root_el)
        table_el = pdoc.make_indirect(new_dict({
            "S": pikepdf.Name("/Table"), "K": pikepdf.Array([]), "P": root_el}))
        tr_el = pdoc.make_indirect(new_dict({
            "S": pikepdf.Name("/TR"), "K": pikepdf.Array([]), "P": table_el}))
        td1 = pdoc.make_indirect(new_dict({
            "S": pikepdf.Name("/TD"), "K": 4, "P": tr_el}))
        td2 = pdoc.make_indirect(new_dict({
            "S": pikepdf.Name("/TD"), "K": 5, "P": tr_el}))
        tr_el["/K"] = pikepdf.Array([td1, td2])
        table_el["/K"] = tr_el
        root_el["/K"] = pikepdf.Array([h1, h3, p, table_el])
        _finalize_root(pdoc, root_el, [1, 2, 3, 4, 5])
        dm.save(final)
    tmp.unlink()


def make_tagged_nooutline():
    """clean.pdf minus the outline: tagged + marked + complete catalog,
    headings present in the tree, no /Outlines.
    Oracle: exactly one finding (outline-missing, fixable=True); default
    fix reaches PASS."""
    final = FIX / "tagged-nooutline.pdf"
    tmp = _base_to_tmp("tagged-nooutline", CONTENT_MARKED)
    with DocModel.open(tmp) as dm:
        dm.set_lang("en")
        dm.set_title("Tagged NoOutline Fixture")
        dm.set_display_doc_title(True)
        dm.set_marked(True)
        dm.set_image_alt(0, "Im1", "A square")
        pdoc = dm.doc
        root_el = _new_root_el(pdoc)
        h1 = _make_el(pdoc, "/H1", 1, root_el, alt="Big Title")
        p = _make_el(pdoc, "/P", 2, root_el)
        fig = _make_el(pdoc, "/Figure", 3, root_el, alt="A square")
        root_el["/K"] = pikepdf.Array([h1, p, fig])
        _finalize_root(pdoc, root_el, [1, 2, 3])
        dm.save(final)
    tmp.unlink()


def make_scan():
    """Image-only page (no extractable text): the OCR test target.
    Oracle: audit reports image-alt + tagging findings (OCR is what would help);
    the fixture is committed so OCR tests are hermetic about file existence."""
    final = FIX / "scan.pdf"
    tmp = _base_to_tmp("scan", CONTENT_SCAN)
    tmp.rename(final)


def make_weak_repairable():
    """clean.pdf's tree with the Paragraph element's /P removed -> exactly one
    tag-tree-weak 'orphaned structure element' finding. After --scaffold
    --repair the orphan is repointed and re-audit is clean.
    Oracle: audit -> exactly 1 tag-tree-weak finding."""
    final = FIX / "weak-repairable.pdf"
    tmp = _base_to_tmp("weak-repairable", CONTENT_MARKED)
    with DocModel.open(tmp) as dm:
        dm.set_lang("en")
        dm.set_title("Weak Repairable Fixture")
        dm.set_display_doc_title(True)
        dm.set_marked(True)
        dm.set_outline([(1, "Big Title", 0)])
        dm.set_image_alt(0, "Im1", "A square")
        pdoc = dm.doc
        root_el = _new_root_el(pdoc)
        h1 = _make_el(pdoc, "/H1", 1, root_el, alt="Big Title")
        p = _make_el(pdoc, "/P", 2, root_el)
        del p[pikepdf.Name("/P")]            # <-- create the orphan
        fig = _make_el(pdoc, "/Figure", 3, root_el, alt="A square")
        root_el["/K"] = pikepdf.Array([h1, p, fig])
        _finalize_root(pdoc, root_el, [1, 2, 3])
        dm.save(final)
    tmp.unlink()


def copy_bread():
    """Real-world sample (subsetted fonts, custom encoding): the hard case."""
    shutil.copy(ROOT / "examples" / "No Knead Bread-print.pdf", FIX / "bread.pdf")


if __name__ == "__main__":
    make_clean()
    make_fixable()
    make_marked_notree()
    make_tagged_nooutline()
    make_violations()
    make_scan()
    make_weak_repairable()
    copy_bread()
    print(f"fixtures written to {FIX}")