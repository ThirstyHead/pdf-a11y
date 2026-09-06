# Theme layer contract (SMACSS, plain CSS, no build step)

Deterministic assembly order for `theme_css(name)`:

1. **settings/tokens** — `<theme>/tokens.css` (10 custom properties)
2. **objects** — `_layout/objects.css` (shared, theme-independent)
3. **units** — `_layout/units.css` (shared components: `.report`,
   `.summary-banner`, `.finding`, `table.report-table`, `nav.toc`, `.sev*`)
4. **components/overrides** — `<theme>/overrides.css` (optional)

Output starts with the marker comment `/* pdf-a11y theme: <name> */`.

## Token vocabulary (10, all required in tokens.css)

`--bg --fg --muted --accent --link --code-bg
 --sev-critical --sev-serious --sev-moderate --sev-minor`

Contrast gate (enforced by `tests/test_reports_html.py`):
`fg` vs `bg` and every `--sev-*` vs `--bg` must be >= 4.5:1 (WCAG 1.4.3 AA).
Severity is additionally signalled by weight + underline (`.sev`), so color
is never the only cue (needed for the 1c print rendering too).

## Theme manifest (theme.json)

`{"name": str, "label": str, "mode": "light"|"dark", "default": bool}`

Exactly one bundled theme has `"default": true` (light).

## User themes

`<config-dir>/themes/<name>/{tokens.css, theme.json, [overrides.css]}` —
same shape. On name collision the user theme **wins** (merged first in
`available_themes`, resolved first in `theme_css`).
