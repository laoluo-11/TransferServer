#!/bin/bash
# Bumi TransferServer - Jetson 一键启动
# 放到 /home/noetix/ 下，chmod +x start_jetson.sh
# 运行: ./start_jetson.sh    停止: Ctrl+C

set -e

BUMI_HOME="/home/noetix"
SDK_BUILD_DIR="${BUMI_HOME}/noetix_sdk_bumi/build"
SDK_CONFIG="${BUMI_HOME}/noetix_sdk_bumi/config/dds.xml"

# 检查 SDK .so（模糊匹配，兼容不同 Python 版本）
if ! ls "${SDK_BUILD_DIR}"/highcontrol_py*.so >/dev/null 2>&1; then
    echo "[ERROR] SDK .so not found in ${SDK_BUILD_DIR}"
    echo "        Build the SDK first: cd ~/noetix_sdk_bumi && ./build.sh"
    exit 1
fi

export BUMI_BRIDGE_MODE=bumi
export BUMI_SERVER_BASE_URL=ws://127.0.0.1:8000
export BUMI_SDK_BUILD_DIR="${SDK_BUILD_DIR}"
export CYCLONEDDS_URI="file://${SDK_CONFIG}"
export BUMI_ROBOT_ID=bumi_001
export BUMI_CONTROL_MODE=highcontrol
export BUMI_DDS_HOST=192.168.55.101
export BUMI_DDS_DOMAIN_ID=0

echo "=============================================="
echo "  Bumi TransferServer (Jetson)"
echo "=============================================="
echo "  SDK:       ${SDK_BUILD_DIR}"
echo "  DDS:       ${CYCLONEDDS_URI}"
echo "  Bridge:    ${BUMI_BRIDGE_MODE}"
echo "  Cloud:     ${BUMI_SERVER_BASE_URL}"
echo "=============================================="

cleanup() {
    echo ""
    echo "[STOP] Shutting down..."
    kill $CLOUD_PID 2>/dev/null || true
    wait $CLOUD_PID 2>/dev/null || true
    echo "[STOP] Done."
    exit 0
}
trap cleanup INT TERM

# Step 1: 启动 cloud (后台)
echo ""
echo "[1/2] Starting cloud..."
cd "${BUMI_HOME}"
python3 -m uvicorn cloud.app.main:app --host 127.0.0.1 --port 8000 &
CLOUD_PID=$!
sleep 3

if ! kill -0 $CLOUD_PID 2>/dev/null; then
    echo "[ERROR] Cloud failed to start"
    exit 1
fi
echo "       OK (PID $CLOUD_PID)"

# Step 2: 启动 robot-agent (前台)
echo "[2/2] Starting robot-agent..."
cd "${BUMI_HOME}/robot-agent"
python3 -m agent.main

cleanup
