#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

APP_NAME="pdf-a11y"
VERSION="0.6.0"
DIST_DIR="${REPO_ROOT}/dist"
MACOS_OUT_DIR="${DIST_DIR}/macos"
STAGING_DIR="${DIST_DIR}/dmg-staging"
DMG_PATH="${MACOS_OUT_DIR}/${APP_NAME}-v${VERSION}-macos.dmg"

mkdir -p "${MACOS_OUT_DIR}"
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

echo "==> Building macOS .app bundle using PyInstaller..."
PYINSTALLER_BIN="${REPO_ROOT}/.venv/bin/pyinstaller"
if [ ! -x "${PYINSTALLER_BIN}" ]; then
  PYINSTALLER_BIN="$(command -v pyinstaller || true)"
fi
if [ -z "${PYINSTALLER_BIN}" ]; then
  echo "Error: pyinstaller executable not found."
  exit 1
fi

"${PYINSTALLER_BIN}" --noconfirm --clean "${REPO_ROOT}/packaging/specs/pdf-a11y-gui.spec"

if [ ! -d "${DIST_DIR}/${APP_NAME}.app" ]; then
  echo "Error: ${DIST_DIR}/${APP_NAME}.app was not generated."
  exit 1
fi

echo "==> Ensuring clean ad-hoc code signature across bundle..."
codesign --force --deep -s - "${DIST_DIR}/${APP_NAME}.app"

echo "==> Staging app bundle for DMG creation..."
cp -R "${DIST_DIR}/${APP_NAME}.app" "${STAGING_DIR}/"

echo "==> Creating macOS Disk Image (.dmg)..."
if command -v create-dmg >/dev/null 2>&1; then
  rm -f "${DMG_PATH}"
  # Use create-dmg with --skip-jenkins to avoid AppleScript timeouts in automated/headless sessions
  create-dmg \
    --volname "${APP_NAME} Installer" \
    --volicon "${REPO_ROOT}/packaging/icons/pdf-a11y.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "${APP_NAME}.app" 175 120 \
    --hide-extension "${APP_NAME}.app" \
    --app-drop-link 425 120 \
    --skip-jenkins \
    --overwrite \
    "${DMG_PATH}" \
    "${STAGING_DIR}" || {
      echo "create-dmg encountered an error, falling back to hdiutil..."
      hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}"
    }
else
  echo "create-dmg not found; using macOS native hdiutil..."
  hdiutil create -volname "${APP_NAME}" -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}"
fi

echo "==> DMG built successfully at: ${DMG_PATH}"
