# pdf-a11y

Audit and remediate PDF files against **WCAG 2.1/2.2 AA** and **PDF/UA-1 (ISO 14289-1)** standards — standalone, deterministic, no AI in the loop.

Part of the **Four-Tool Office & Document Accessibility Suite**:
- `docx-a11y`: Word documents (.docx)
- `pptx-a11y`: PowerPoint presentations (.pptx)
- `xlsx-a11y`: Excel workbooks (.xlsx)
- `pdf-a11y`: Portable Document Format (.pdf)

`pdf-a11y` is a rule-based auditor over the PDF object structure (catalog, page resources, marked content streams, `/StructTreeRoot`). It reports every barrier with a WCAG success criterion and persona impact mapping, supports interactive author triage, applies deterministic remediations without ever touching the source file, and renders accessible reports in Markdown, HTML, JSON, and tagged PDF.

---

## Installation

### 1. Desktop GUI Application (Pre-built Installers)

Pre-built desktop installers with bundled dependencies (including PySide6/Qt) are available on the [GitHub Releases](https://github.com/ThirstyHead/pdf-a11y/releases) page:

- **macOS (`.dmg`)**:
  1. Download `pdf-a11y-v<version>-macos.dmg` (e.g. `pdf-a11y-v0.6.0-macos.dmg`).
  2. Double-click to mount the disk image.
  3. Drag `pdf-a11y.app` into `/Applications`.
  4. Launch `pdf-a11y` from Spotlight, Launchpad, or the Applications folder.
  > **Note (macOS Gatekeeper)**: Because `pdf-a11y` is an open-source binary distributed outside the Mac App Store without paid Apple Developer notarization, macOS blocks first launch with *“Apple could not verify pdf-a11y is free of malware”*.
  > - **GUI bypass**: Right-click (or Control-click) `pdf-a11y.app` in `/Applications`, select **Open**, and click **Open**. Alternatively, go to **System Settings > Privacy & Security**, scroll down to the **Security** section, and click **Open Anyway**.
  > - **Terminal bypass**: Run `xattr -cr /Applications/pdf-a11y.app` (or `xattr -d com.apple.quarantine ~/Downloads/pdf-a11y-*-macos.dmg` before opening the DMG).
- **Windows (`.exe`)**:
  1. Download `pdf-a11y-setup-v<version>.exe` (e.g. `pdf-a11y-setup-v0.6.0.exe`).
  2. Run the installer wizard to install into `Program Files` and create Start Menu / Desktop shortcuts.
- **Linux (`.AppImage`)**:
  1. Download `pdf-a11y-v<version>-x86_64.AppImage` (e.g. `pdf-a11y-v0.6.0-x86_64.AppImage`).
  2. Make it executable: `chmod +x pdf-a11y-v*-x86_64.AppImage`.
  3. Run directly: `./pdf-a11y-v*-x86_64.AppImage`.

### 2. Standalone Headless CLI Binary (No Python Required)

Single-file headless CLI executables are available on [GitHub Releases](https://github.com/ThirstyHead/pdf-a11y/releases) for agentic workflows, CI/CD pipelines, and terminal environments:

```bash
# Example: Download macOS Apple Silicon standalone CLI binary
curl -LO https://github.com/ThirstyHead/pdf-a11y/releases/latest/download/pdf-a11y-cli-macos-arm64
chmod +x pdf-a11y-cli-macos-arm64
sudo mv pdf-a11y-cli-macos-arm64 /usr/local/bin/pdf-a11y

# Verify installation
pdf-a11y --help
```

### 3. Ephemeral Execution via `uvx`

Run `pdf-a11y` instantly in any environment without managing Python virtual environments:

```bash
# Run headless CLI audit & remediation
uvx pdf-a11y document.pdf --fix --format md,html,pdf,json

# Launch desktop GUI ephemerally
uvx --with "pdf-a11y[gui]" pdf-a11y --gui
```

### 4. Python Package via `pip`

Install into a local Python 3.10+ virtual environment:

```bash
# Headless CLI only (lean, no Qt dependencies)
pip install pdf-a11y

# With PySide6 Desktop GUI support
pip install "pdf-a11y[gui]"

# Full installation (dev, GUI, OCR, packaging)
pip install "pdf-a11y[all]"
```

---

## Sibling Parity & Feature Matrix

| Feature | `docx-a11y` | `pptx-a11y` | `xlsx-a11y` | `pdf-a11y` |
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
