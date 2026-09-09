# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

SPEC_ROOT = Path(SPECPATH)
REPO_ROOT = SPEC_ROOT.parent.parent

datas = collect_data_files('pdf_a11y') + collect_data_files('engine_a11y')

excludes = [
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'shiboken6',
    'tkinter',
    'unittest',
    'matplotlib',
    'scipy',
    'pdf_a11y.gui',
    'engine_a11y.gui',
]

a = Analysis(
    [str(REPO_ROOT / 'packaging' / 'entrypoints' / 'cli_main.py')],
    pathex=[str(REPO_ROOT / 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'engine_a11y',
        'engine_a11y.criteria_config',
        'engine_a11y.findings',
        'fitz',
        'pikepdf',
        'pdfplumber',
        'wcag_contrast_ratio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='pdf-a11y',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
