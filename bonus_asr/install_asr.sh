#!/usr/bin/env bash
# Sets up the optional ASR dependencies in an isolated virtual environment.
# Keeps the mandatory submission / evaluation environment completely clean.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv-asr"
MODEL_DIR="${SCRIPT_DIR}/model"

echo "=== LiveRecall Bonus Feature: ASR Setup ==="
echo "Creating isolated ASR virtual environment in ${VENV_DIR}..."
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

pip install --upgrade pip
pip install -r "${SCRIPT_DIR}/requirements-asr.txt"

# Download lightweight Vosk small English model if not already present
if [ ! -d "${MODEL_DIR}" ]; then
    echo "Downloading compact Vosk English model (approx 40 MB)..."
    TMP_ZIP="/tmp/vosk-model-small.zip"
    URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    if command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "${TMP_ZIP}" "${URL}"
    else
        curl -L -o "${TMP_ZIP}" "${URL}"
    fi
    python3 -m zipfile -e "${TMP_ZIP}" "/tmp"
    mv /tmp/vosk-model-small-en-us-0.15 "${MODEL_DIR}"
    rm -f "${TMP_ZIP}"
    echo "Vosk model successfully extracted to ${MODEL_DIR}"
else
    echo "Vosk model already present at ${MODEL_DIR}"
fi

# Link standalone ffmpeg from imageio-ffmpeg if available
PY_FFMPEG=$("${VENV_DIR}/bin/python3" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null || true)
if [ -n "${PY_FFMPEG}" ] && [ -f "${PY_FFMPEG}" ]; then
    ln -sf "${PY_FFMPEG}" "${VENV_DIR}/bin/ffmpeg"
    echo "Linked standalone ffmpeg binary to ${VENV_DIR}/bin/ffmpeg"
fi

echo ""
echo "=== ASR Environment Ready! ==="
echo "To run the 3-minute video lecture demonstration:"
echo "  ./bonus_asr/run_bonus_demo.sh"

