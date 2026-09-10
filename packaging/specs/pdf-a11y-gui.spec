# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from engine_a11y.packaging.specs import COMMON_HIDDEN_IMPORTS, COMMON_EXCLUDES

block_cipher = None

# Spec directory is packaging/specs/
SPEC_ROOT = Path(SPECPATH)
REPO_ROOT = SPEC_ROOT.parent.parent

datas = collect_data_files('pdf_a11y') + collect_data_files('engine_a11y')
hiddenimports = sorted(list(set(
    collect_submodules('PySide6')
    + collect_submodules('pdf_a11y.gui')
    + COMMON_HIDDEN_IMPORTS
    + [
        'fitz',
        'pikepdf',
        'pdfplumber',
        'wcag_contrast_ratio',
    ]
)))

excludes = sorted(list(set(COMMON_EXCLUDES)))

a = Analysis(
    [str(REPO_ROOT / 'packaging' / 'entrypoints' / 'gui_main.py')],
    pathex=[str(REPO_ROOT / 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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

icon_path = str(REPO_ROOT / 'packaging' / 'icons' / ('pdf-a11y.icns' if sys.platform == 'darwin' else 'pdf-a11y.ico'))

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pdf-a11y',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pdf-a11y-gui',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='pdf-a11y.app',
        icon=icon_path,
        bundle_identifier='com.thirstyhead.pdf-a11y',
        info_plist={
            'CFBundleName': 'PDF Accessibility Auditor',
            'CFBundleDisplayName': 'PDF Accessibility Auditor',
            'CFBundleGetInfoString': 'Audit and remediate PDF files against WCAG 2.1 AA and PDF/UA-1',
            'CFBundleIdentifier': 'com.thirstyhead.pdf-a11y',
            'CFBundleVersion': '0.6.0',
            'CFBundleShortVersionString': '0.6.0',
            'NSHumanReadableCopyright': 'Copyright (c) 2026 ThirstyHead',
            'NSHighResolutionCapable': True,
        },
    )
