"""Tests for the media-no-alt rule (SC 1.2.x time-based media alternatives).

Layered:
  * unit tests of ``DocModel.media_items`` (form XObjects, Screen annotations,
    catalog embedded files; inherited Resources; images excluded);
  * rule-level tests on real PDFs (finding shape, /Alt suppression,
    --media-placeholder fixability, deterministic fix);
  * remediation/CLI integration (fix_one, ``pdf-a11y fix --media-placeholder``);
  * characterization: every committed fixture yields zero media findings.
"""
import pikepdf
import pytest

from pdf_a11y import audit as audit_mod
from pdf_a11y.audit import audit_file
from pdf_a11y.docmodel import DocModel, key
from pdf_a11y.rules import AuditContext, RULES, RULES_BY_ID

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def _dict(**kw):
    return pikepdf.Dictionary({(k if k.startswith("/") else "/" + k): v
                               for k, v in kw.items()})


def _page(d):
    p = pikepdf.Page(_dict(Type="/Page",
                           MediaBox=pikepdf.Array([0, 0, 612, 792])))
    d.pages.append(p)
    return p


def _add_form(d, page, name="FormMedia", alt=None):
    form = d.make_stream(b"q 1 0 0 1 0 0 cm Q",
                         _dict(Type="/XObject", Subtype="/Form",
                               BBox=pikepdf.Array([0, 0, 320, 180]),
                               Resources=pikepdf.Dictionary()))
    form = d.make_indirect(form)
    if alt is not None:
        form["/Alt"] = alt
    res = key(page, "Resources")
    if res is None:
        page.obj["/Resources"] = _dict(XObject=_dict(**{name: form}))
    else:
        xobjs = key(res, "XObject")
        if xobjs is None:
            res["/XObject"] = _dict(**{name: form})
        else:
            xobjs["/" + name] = form
    return form


def _add_screen_annot(d, page, title="Video", alt=None):
    ann = d.make_indirect(_dict(Type="/Annot", Subtype="/Screen",
                                Rect=pikepdf.Array([72, 72, 372, 252]),
                                T=title))
    if alt is not None:
        ann["/Alt"] = alt
    annots = key(page, "Annots")
    if annots is None:
        page.obj["/Annots"] = pikepdf.Array([ann])
    else:
        annots.append(ann)
    return ann


def _add_embedded_file(d, filename="clip.mp3", alt=None):
    fs = d.make_stream(b"RIFFfakeaudio", _dict(Type="/EmbeddedFile"))
    spec = d.make_indirect(_dict(Type="/Filespec", F=filename, EF=_dict(F=fs)))
    if alt is not None:
        spec["/Alt"] = alt
    ef = key(d.Root, "EmbeddedFiles")
    if ef is None:
        d.Root["/EmbeddedFiles"] = _dict(
            Names=pikepdf.Array([filename, spec]))
    else:
        key(ef, "Names").extend([filename, spec])
    return spec


def _save(d, tmp_path, name="media.pdf"):
    path = tmp_path / name
    d.save(str(path))
    return path


# ---------------------------------------------------------------------------
# DocModel.media_items
# ---------------------------------------------------------------------------

def test_media_items_empty(tmp_path):
    d = pikepdf.new()
    _page(d)
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        assert dm.media_items() == []


def test_media_items_form_xobject(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        items = dm.media_items()
    assert len(items) == 1
    kind, loc, _obj = items[0]
    assert kind == "form-xobject"
    assert loc == "page[0] /FormMedia"


def test_media_items_screen_annot(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_screen_annot(d, p, title="Video")
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        items = dm.media_items()
    assert len(items) == 1
    kind, loc, _obj = items[0]
    assert kind == "screen-annot"
    assert "screen annotation" in loc and "Video" in loc
    assert loc.startswith("page[0] ")


def test_media_items_embedded_file(tmp_path):
    d = pikepdf.new()
    _page(d)
    _add_embedded_file(d, filename="clip.mp3")
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        items = dm.media_items()
    assert len(items) == 1
    kind, loc, spec = items[0]
    assert kind == "embedded-file"
    assert "clip.mp3" in loc
    assert str(key(spec, "F")) == "clip.mp3"


def test_media_items_all_three_kinds(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    _add_screen_annot(d, p)
    _add_embedded_file(d)
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        items = dm.media_items()
    assert sorted(kind for kind, _loc, _o in items) == [
        "embedded-file", "form-xobject", "screen-annot"]


def test_media_items_inherited_form(tmp_path):
    """A form XObject declared in a /Pages-ancestor Resources is media for
    every page under it (same inheritance as image XObjects)."""
    d = pikepdf.new()
    p = _page(d)
    form = d.make_stream(b"q Q",
                         _dict(Type="/XObject", Subtype="/Form",
                               BBox=pikepdf.Array([0, 0, 100, 100]),
                               Resources=pikepdf.Dictionary()))
    form = d.make_indirect(form)
    d.Root["/Pages"]["/Resources"] = _dict(XObject=_dict(Shared=form))
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        items = dm.media_items()
    assert [loc for _k, loc, _o in items] == ["page[0] /Shared"]


def test_image_xobject_not_media(tmp_path):
    """Image XObjects are media under SC 1.1.1, not 1.2.x — excluded here."""
    d = pikepdf.new()
    p = _page(d)
    img = d.make_stream(b"\x00",
                        _dict(Type="/XObject", Subtype="/Image",
                              Width=4, Height=4,
                              ColorSpace=pikepdf.Name("/DeviceRGB"),
                              BitsPerComponent=8))
    img = d.make_indirect(img)
    p.obj["/Resources"] = _dict(XObject=_dict(Pix=img))
    path = _save(d, tmp_path)
    with DocModel.open(path) as dm:
        assert dm.media_items() == []
        result = audit_file(str(path))
    assert not [f for f in result["findings"] if f["rule_id"] == "media-no-alt"]


# ---------------------------------------------------------------------------
# Rule: check()
# ---------------------------------------------------------------------------

def test_rule_registered():
    assert "media-no-alt" in RULES_BY_ID
    assert len(RULES) == 18
    r = RULES_BY_ID["media-no-alt"]
    assert r.sc == "1.2.1"
    assert r.severity == "serious"


def test_finding_on_form_without_alt(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    result = audit_file(str(path))
    ms = [f for f in result["findings"] if f["rule_id"] == "media-no-alt"]
    assert len(ms) == 1
    f = ms[0]
    assert f["sc"] == "1.2.1"
    assert f["severity"] == "serious"
    assert f["location"] == "page[0] /FormMedia"
    assert f["severity"] in ("critical", "serious")  # blocking
    assert "Alt" in f["description"]


def test_finding_on_annot_and_embedded_file(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_screen_annot(d, p)
    _add_embedded_file(d)
    path = _save(d, tmp_path)
    result = audit_file(str(path))
    ms = [f for f in result["findings"] if f["rule_id"] == "media-no-alt"]
    assert len(ms) == 2
    locs = {f["location"] for f in ms}
    assert any("screen annotation" in l for l in locs)
    assert any("clip.mp3" in l for l in locs)


def test_screen_annot_title_is_not_alt(tmp_path):
    """/T (the annotation title) is a label, not an alternative — still flagged."""
    d = pikepdf.new()
    p = _page(d)
    _add_screen_annot(d, p, title="Video")
    path = _save(d, tmp_path)
    result = audit_file(str(path))
    assert len([f for f in result["findings"]
                if f["rule_id"] == "media-no-alt"]) == 1


def test_no_finding_when_alt_present(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p, alt="Bar chart of quarterly sales")
    _add_screen_annot(d, p, alt="Intro video with narration transcript below")
    _add_embedded_file(d, alt="Podcast episode 12")
    path = _save(d, tmp_path)
    result = audit_file(str(path))
    assert not [f for f in result["findings"]
                if f["rule_id"] == "media-no-alt"]


def test_default_fixable_false_placeholder_fixable_true(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    plain = audit_file(str(path))
    f = [f for f in plain["findings"] if f["rule_id"] == "media-no-alt"][0]
    assert f["fixable"] is False
    ph = audit_file(str(path),
                    AuditContext(source_name=path.name, media_placeholder=True))
    f = [f for f in ph["findings"] if f["rule_id"] == "media-no-alt"][0]
    assert f["fixable"] is True


def test_deterministic(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    _add_screen_annot(d, p)
    _add_embedded_file(d)
    path = _save(d, tmp_path)
    a = audit_file(str(path))["findings"]
    b = audit_file(str(path))["findings"]
    assert a == b


@pytest.mark.parametrize("fixture",
                         sorted(FIXTURES.glob("*.pdf")), ids=lambda p: p.name)
def test_committed_fixture_no_media_findings(fixture):
    result = audit_file(str(fixture))
    assert not [f for f in result["findings"]
                if f["rule_id"] == "media-no-alt"]


# ---------------------------------------------------------------------------
# Rule: fix() and remediation
# ---------------------------------------------------------------------------

def test_fix_writes_placeholder(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    ctx = AuditContext(source_name=path.name, media_placeholder=True)
    result = audit_file(str(path), ctx)
    f = [f for f in result["findings"] if f["rule_id"] == "media-no-alt"][0]
    rule = RULES_BY_ID["media-no-alt"]
    with DocModel.open(path) as dm:
        assert rule.fix(dm, _mk_finding(f), ctx) is True
        out = tmp_path / "fixed.pdf"
        dm.save(str(out))
    re = audit_file(str(out))
    assert not [x for x in re["findings"] if x["rule_id"] == "media-no-alt"]
    with DocModel.open(out) as dm:
        kind, loc, obj = dm.media_items()[0]
        alt = str(key(obj, "Alt"))
        assert alt.startswith("[MEDIA-ALT-REQUIRED:")
        assert "/FormMedia" in alt


def _mk_finding(d):
    return __import__("pdf_a11y.findings", fromlist=["Finding"]).Finding(**d)


def test_fix_without_placeholder_is_manual(tmp_path):
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    result = audit_file(str(path))
    f = [f for f in result["findings"] if f["rule_id"] == "media-no-alt"][0]
    rule = RULES_BY_ID["media-no-alt"]
    with DocModel.open(path) as dm:
        assert rule.fix(dm, _mk_finding(f),
                        AuditContext(source_name=path.name)) is False


def test_fix_one_applies_placeholder(tmp_path):
    from pdf_a11y.remediate import fix_one
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    out = tmp_path / "fixed.pdf"
    fr = fix_one(str(path), str(out),
                 AuditContext(source_name=path.name, media_placeholder=True))
    assert fr["status"] in ("pass", "fail")
    ms = [f for f in fr["reaudit"]["findings"]
          if f["rule_id"] == "media-no-alt"]
    assert ms == []
    applied = [a for a in fr["remediation"]["applied"]
               if a[0] == "MediaNoAlt"]
    assert len(applied) == 1


def test_cli_fix_media_placeholder(tmp_path, capsys):
    from pdf_a11y.cli import main
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    out = tmp_path / "fixed.pdf"
    rc = main(["fix", str(path), "--media-placeholder", "--out", str(out)])
    assert rc in (0, 1)
    re = audit_file(str(out))
    assert not [f for f in re["findings"] if f["rule_id"] == "media-no-alt"]


def test_cli_fix_default_keeps_media_finding(tmp_path, capsys):
    """Without --media-placeholder the fix is manual: the re-audit still
    reports the (now fixable=False) media finding."""
    from pdf_a11y.cli import main
    d = pikepdf.new()
    p = _page(d)
    _add_form(d, p)
    path = _save(d, tmp_path)
    out = tmp_path / "fixed.pdf"
    rc = main(["fix", str(path), "--out", str(out)])
    assert rc in (0, 1)
    re = audit_file(str(out))
    ms = [f for f in re["findings"] if f["rule_id"] == "media-no-alt"]
    assert len(ms) == 1
    assert ms[0]["fixable"] is False
