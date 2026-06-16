#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3.7}"
PACKAGE_NAME="${PACKAGE_NAME:-lscure-ai-report-server-ubuntu16}"
BUILD_ROOT="build/ubuntu16"
PACKAGE_DIR="${BUILD_ROOT}/${PACKAGE_NAME}"
TARBALL="${BUILD_ROOT}/${PACKAGE_NAME}.tar.gz"
INSTALLER="${BUILD_ROOT}/${PACKAGE_NAME}.run"

echo "Using Python: $(${PYTHON_BIN} --version 2>&1)"

rm -rf "${BUILD_ROOT}" build/pyinstaller dist/ai_report_server
mkdir -p "${BUILD_ROOT}"

"${PYTHON_BIN}" -m venv "${BUILD_ROOT}/venv"
# shellcheck disable=SC1091
source "${BUILD_ROOT}/venv/bin/activate"
python -m pip install --upgrade "pip<24" wheel setuptools
python -m pip install -r requirements-ubuntu16.txt
python -m pip install "pyinstaller==5.13.2"

pyinstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name ai_report_server \
  --distpath dist \
  --workpath build/pyinstaller \
  --paths back_skin_msd_simulation \
  --add-data "back_skin_msd_simulation/assets:back_skin_msd_simulation/assets" \
  --add-data "back_skin_msd_simulation/report_assets:back_skin_msd_simulation/report_assets" \
  --add-data "back_skin_msd_simulation/user_data:back_skin_msd_simulation/user_data" \
  --add-data "lscure_report_interface:lscure_report_interface" \
  --add-data "骨骼图片.png:." \
  --hidden-import ai_report_server \
  --hidden-import report_generator \
  --hidden-import spatial_temporal_alignment \
  --hidden-import coordinate_alignment \
  --hidden-import force_analysis \
  --hidden-import pressure_recommender \
  --hidden-import back_region_map \
  packaging/packaged_ai_report_server.py

mkdir -p "${PACKAGE_DIR}"
cp -a dist/ai_report_server/. "${PACKAGE_DIR}/"
cp packaging/start_server.sh "${PACKAGE_DIR}/start_server.sh"
chmod +x "${PACKAGE_DIR}/start_server.sh"
chmod +x "${PACKAGE_DIR}/ai_report_server"
cp -a README.md AI_REPORT_LINUX_README.md UBUNTU16_PACKAGING.md BOSS_UBUNTU16_INSTALL.md "${PACKAGE_DIR}/"
find "${PACKAGE_DIR}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${PACKAGE_DIR}" -type f -name "*.pyc" -delete

tar -C "${BUILD_ROOT}" -czf "${TARBALL}" "${PACKAGE_NAME}"

cat packaging/installer_stub.sh "${TARBALL}" > "${INSTALLER}"
chmod +x "${INSTALLER}"

echo
echo "Package created:"
echo "  ${TARBALL}"
echo "  ${INSTALLER}"
echo
echo "Test on Ubuntu 16:"
echo "  ./${PACKAGE_NAME}.run"
echo "  ~/.local/bin/lscure-ai-report-server"
