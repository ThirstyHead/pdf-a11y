"""Tests for packaging, installer specifications, and asset generation in pdf-a11y."""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_packaging_directories_exist():
    packaging = REPO_ROOT / "packaging"
    assert (packaging / "icons").is_dir()
    assert (packaging / "specs").is_dir()
    assert (packaging / "macos").is_dir()
    assert (packaging / "windows").is_dir()
    assert (packaging / "linux").is_dir()


def test_icon_assets_exist():
    icons = REPO_ROOT / "packaging" / "icons"
    assert (icons / "pdf-a11y.svg").is_file()
    assert (icons / "pdf-a11y.png").is_file()
    assert (icons / "pdf-a11y.ico").is_file()
    assert (icons / "pdf-a11y.icns").is_file()


def test_gui_spec_configuration():
    gui_spec = REPO_ROOT / "packaging" / "specs" / "pdf-a11y-gui.spec"
    assert gui_spec.is_file()
    content = gui_spec.read_text(encoding="utf-8")
    assert "pdf_a11y" in content
    assert "engine_a11y" in content
    assert "console=False" in content
    assert "app = BUNDLE" in content
    assert "name='pdf-a11y-gui'" in content


def test_cli_spec_configuration():
    cli_spec = REPO_ROOT / "packaging" / "specs" / "pdf-a11y-cli.spec"
    assert cli_spec.is_file()
    content = cli_spec.read_text(encoding="utf-8")
    assert "cli_main.py" in content
    assert "PySide6" in content  # Excluded
    assert "excludes=" in content
    assert "console=True" in content
    assert "name='pdf-a11y'" in content


def test_macos_dmg_script():
    script = REPO_ROOT / "packaging" / "macos" / "build_dmg.sh"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "create-dmg" in content or "hdiutil" in content
    assert ".app" in content


def test_windows_inno_setup_script():
    iss = REPO_ROOT / "packaging" / "windows" / "pdf-a11y.iss"
    assert iss.is_file()
    content = iss.read_text(encoding="utf-8")
    assert 'MyAppName "pdf-a11y"' in content
    assert "Tasks: desktopicon" in content
    assert "SetupIconFile=" in content
    assert "pdf-a11y-gui" in content
    assert "PrivilegesRequired=lowest" in content
    assert "OutputDir=..\\..\\dist\\windows" in content


def test_linux_packaging_files():
    desktop = REPO_ROOT / "packaging" / "linux" / "pdf-a11y.desktop"
    appimage_sh = REPO_ROOT / "packaging" / "linux" / "build_appimage.sh"
    assert desktop.is_file()
    assert appimage_sh.is_file()
    content = desktop.read_text(encoding="utf-8")
    assert "Categories=Utility;Accessibility;" in content
    appimage_content = appimage_sh.read_text(encoding="utf-8")
    assert "pdf-a11y-gui" in appimage_content


def test_packaging_uses_shared_engine():
    gen_script = (REPO_ROOT / "packaging" / "scripts" / "generate_icons.py").read_text(encoding="utf-8")
    assert "engine_a11y.packaging.icons" in gen_script
    gui_spec = (REPO_ROOT / "packaging" / "specs" / "pdf-a11y-gui.spec").read_text(encoding="utf-8")
    assert "engine_a11y.packaging.specs" in gui_spec
