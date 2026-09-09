# pdf-a11y

Audit and remediate PDF files against **WCAG 2.1/2.2 AA** and **PDF/UA-1 (ISO 14289-1)** standards — standalone, deterministic, no AI in the loop.

Part of the **Four-Tool Office & Document Accessibility Suite**:
- `docx-a11y`: Word documents (.docx)
- `pptx-a11y`: PowerPoint presentations (.pptx)
- `xslx-a11y`: Excel workbooks (.xlsx)
- `pdf-a11y`: Portable Document Format (.pdf)

`pdf-a11y` is a rule-based auditor over the PDF object structure (catalog, page resources, marked content streams, `/StructTreeRoot`). It reports every barrier with a WCAG success criterion and persona impact mapping, supports interactive author triage, applies deterministic remediations without ever touching the source file, and renders accessible reports in Markdown, HTML, JSON, and tagged PDF.

---

## Sibling Parity & Feature Matrix

| Feature | `docx-a11y` | `pptx-a11y` | `xslx-a11y` | `pdf-a11y` |
|---|:---:|:---:|:---:|:---:|
| **Root CLI Syntax** | Yes | Yes | Yes | Yes |
| **Deterministic Remediation** | Yes | Yes | Yes | Yes |
| **Source File Immutability (SHA-256)** | Yes | Yes | Yes | Yes |
| **Interactive Author Triage** | Yes | Yes | Yes | Yes |
| **PySide6 Desktop GUI** | Yes | Yes | Yes | Yes |
| **Multi-Format Reports (MD/HTML/PDF/JSON)** | Yes | Yes | Yes | Yes |
| **SMACSS 6-Theme Suite** | Yes | Yes | Yes | Yes |
| **Social Model Language Enforcement** | Yes | Yes | Yes | Yes |
| **Acrobat / Assistant Guidance Notes** | N/A | N/A | N/A | Yes |

---

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"

# 1. Audit and generate Markdown report
pdf-a11y document.pdf

# 2. Audit and fix (source file remains strictly untouched)
pdf-a11y document.pdf --fix --format md,html,pdf,json

# 3. Interactive author triage session (title, language, alt text)
pdf-a11y document.pdf --triage

# 4. Launch PySide6 desktop GUI
pdf-a11y --gui
# or:
pdf-a11y-gui
```

---

## CLI Reference

### Root Command Parity

```bash
pdf-a11y [file] [--gui] [--fix] [--triage] [--format md,html,pdf,json] [--theme THEME] [--output-dir DIR] [--out-pdf OUT]
```

| Flag | Default | Description |
|---|---|---|
| `file` | `None` | Path to `.pdf` file or directory to process |
| `--gui` | `False` | Launch PySide6 desktop application |
| `--fix` | `False` | Apply deterministic remediations without mutating source |
| `--triage` | `False` | Launch interactive author-intent triage session |
| `--format` | `md` | Comma-separated report formats: `md`, `html`, `pdf`, `json` |
| `--theme` | `light` | Report theme: `light`, `dark`, `ocean`, `forest`, `high-contrast`, `print` |
| `--output-dir` | `.` | Output directory for reports and fixed files |
| `--out-pdf` | `None` | Custom output path for remediated PDF (must differ from input) |
| `--batch` | `False` | Process all `.pdf` documents in target directory |

### Subcommand Backward Compatibility

All prior subcommands remain fully supported:
- `pdf-a11y audit FILE [--json] [--report] [--format] [--theme]`
- `pdf-a11y remediate FILE --findings FILE.json --out FILE.fixed.pdf`
- `pdf-a11y fix FILE [--out FILE.fixed.pdf] [--json] [--report]`
- `pdf-a11y rules`

---

## Desktop GUI (`pdf-a11y-gui`)

Launch via `pdf-a11y-gui` or `pdf-a11y --gui`:

- **Drag-and-Drop Batch Processing**: Drag folders or multiple PDF files directly into the window.
- **Background Worker Threads**: PySide6 `QThread` execution (`BatchWorker`, `AuditWorker`, `RemediateWorker`) ensures responsive UI.
- **Interactive Triage Dialog**: Inspect and supply author intent (document title, primary language, alt text for figures, mark decorative elements) in a modal wizard.
- **Multi-Format Export**: One-click generation of Markdown, accessible HTML, tagged PDF, and JSON audit files.
- **Theme Selection**: Preview reports in any of the 6 SMACSS themes.

---

## Immutability & Provenance Guarantee

`pdf-a11y` implements strict SHA-256 pre- and post-condition assertions (`assert_source_unchanged`).
- The source document is **never modified in-place**.
- Remediations write to `<stem>-remediated.pdf` or `--out-pdf`.
- Every audit result and remediation manifest records the exact SHA-256 cryptographic digest of the source file.

---

## Social Model Tone & Assistant Notes

Reports adhere strictly to the social model of disability (barriers arise from document design choices, not user deficits).
- **Prohibited Terminology**: Deficit-based medical language (`"suffer"`, `"wheelchair-bound"`, `"afflicted"`, `"normal users"`) is banned via `assert_social_model_language()`.
- **Persona Mappings**: Findings map to WHO impact personas (e.g., blind screen reader users, keyboard-only navigators, low-vision users).
- **Acrobat Assistant Guidance**: Actionable instructions explain how to verify and modify tags using Adobe Acrobat Pro's Reading Order and Accessibility tools.

---

## License

MIT
