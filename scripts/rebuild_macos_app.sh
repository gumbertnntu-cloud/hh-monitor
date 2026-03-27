#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/HH Monitor.app"
MACOS_DIR="${APP_DIR}/Contents/MacOS"
RESOURCES_DIR="${APP_DIR}/Contents/Resources"
ICON_SOURCE_DEFAULT="${ROOT_DIR}/assets/icons/icon_imagegen_1.png"
ICON_SOURCE="${1:-${ICON_SOURCE_DEFAULT}}"
ICONSET_DIR="${ROOT_DIR}/tmp/AppIcon.iconset"

mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"

cat > "${APP_DIR}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>hh-monitor-launcher</string>
  <key>CFBundleIdentifier</key>
  <string>local.hh.monitor</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIconName</key>
  <string>AppIcon</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>HH Monitor</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

cat > "${MACOS_DIR}/hh-monitor-launcher" <<'LAUNCHER'
#!/usr/bin/env zsh
set -euo pipefail
setopt nonomatch

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/launcher.log"

mkdir -p "${LOG_DIR}"
exec >> "${LOG_FILE}" 2>&1
echo "---- $(date '+%Y-%m-%d %H:%M:%S') launcher start ----"
echo "PROJECT_ROOT=${PROJECT_ROOT}"

translated="$(sysctl -in sysctl.proc_translated 2>/dev/null || echo 0)"
if [[ "${translated}" == "1" ]]; then
  echo "RUNNING_UNDER_ROSETTA=1; restarting launcher as arm64"
  exec /usr/bin/arch -arm64 /bin/zsh "$0" "$@"
fi

if [[ ! -d "${PROJECT_ROOT}/src/hh_monitor" ]]; then
  osascript -e "display dialog \"Не найдена папка проекта: ${PROJECT_ROOT}\" buttons {\"OK\"} default button \"OK\""
  echo "ERROR: src/hh_monitor not found"
  exit 1
fi

typeset -a CANDIDATES
CANDIDATES=(
  "${PROJECT_ROOT}/.venv/bin/python"
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/Current/bin/python3"
  "/usr/bin/python3"
)

for extra in /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
  CANDIDATES+=("${extra}")
done

PYTHON_BIN=""
for candidate in "${CANDIDATES[@]}"; do
  if [[ -x "${candidate}" ]]; then
    echo "TRY_PYTHON=${candidate}"
    PYTHON_BIN="${candidate}"
    break
  fi
done

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "ERROR: no python executable found"
  osascript -e 'display dialog "Python 3 не найден. Установите Python 3.11+ и зависимости проекта." buttons {"OK"} default button "OK"'
  exit 1
fi

echo "SELECTED_PYTHON=${PYTHON_BIN}"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"
"${PYTHON_BIN}" -m hh_monitor.app
exit_code=$?
echo "APP_EXIT_CODE=${exit_code}"
if [[ ${exit_code} -ne 0 ]]; then
  osascript -e "display dialog \"Приложение завершилось с ошибкой (код ${exit_code}). Откройте logs/launcher.log\" buttons {\"OK\"} default button \"OK\""
fi
exit ${exit_code}
LAUNCHER

chmod +x "${MACOS_DIR}/hh-monitor-launcher"

if [[ -f "${ICON_SOURCE}" ]]; then
  rm -rf "${ICONSET_DIR}"
  mkdir -p "${ICONSET_DIR}" "${RESOURCES_DIR}"
  sips -z 16 16 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_16x16.png" >/dev/null
  sips -z 32 32 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_32x32.png" >/dev/null
  sips -z 64 64 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_128x128.png" >/dev/null
  sips -z 256 256 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_256x256.png" >/dev/null
  sips -z 512 512 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "${ICON_SOURCE}" --out "${ICONSET_DIR}/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "${ICONSET_DIR}" -o "${RESOURCES_DIR}/AppIcon.icns"
  echo "App icon set from: ${ICON_SOURCE}"
else
  echo "Icon source not found: ${ICON_SOURCE}"
fi

echo "App bundle rebuilt: ${APP_DIR}"
