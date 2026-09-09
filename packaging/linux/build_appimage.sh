#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"

APP_NAME="pdf-a11y"
VERSION="0.6.0"
DIST_DIR="${REPO_ROOT}/dist"
APP_DIR="${DIST_DIR}/AppDir"
OUT_DIR="${DIST_DIR}/linux"

mkdir -p "${APP_DIR}/usr/bin" \
         "${APP_DIR}/usr/share/applications" \
         "${APP_DIR}/usr/share/icons/hicolor/256x256/apps" \
         "${OUT_DIR}"

echo "==> Building PyInstaller bundle..."
pyinstaller --noconfirm --clean "${REPO_ROOT}/packaging/specs/pdf-a11y-gui.spec"

echo "==> Populating AppDir..."
cp -r "${DIST_DIR}/pdf-a11y-gui/"* "${APP_DIR}/usr/bin/"
cp "${REPO_ROOT}/packaging/linux/pdf-a11y.desktop" "${APP_DIR}/usr/share/applications/"
cp "${REPO_ROOT}/packaging/linux/pdf-a11y.desktop" "${APP_DIR}/"
cp "${REPO_ROOT}/packaging/icons/pdf-a11y.png" "${APP_DIR}/usr/share/icons/hicolor/256x256/apps/"
cp "${REPO_ROOT}/packaging/icons/pdf-a11y.png" "${APP_DIR}/"

cat << 'EOF' > "${APP_DIR}/AppRun"
#!/bin/sh
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH:-}"
exec "${HERE}/usr/bin/pdf-a11y" "$@"
EOF
chmod +x "${APP_DIR}/AppRun"

if command -v appimagetool >/dev/null 2>&1; then
  appimagetool "${APP_DIR}" "${OUT_DIR}/${APP_NAME}-v${VERSION}-x86_64.AppImage"
  echo "==> AppImage built successfully: ${OUT_DIR}/${APP_NAME}-v${VERSION}-x86_64.AppImage"
else
  echo "appimagetool not found on host; AppDir staged at ${APP_DIR} for CI packaging."
fi
