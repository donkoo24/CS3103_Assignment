#!/usr/bin/env bash
# Runs a live demonstration of Section 17 Real-Lecture ASR Integration:
# 1. Starts the LiveRecall server (solution_server.py)
# 2. Instructs the user to open the student browser client
# 3. Streams 3 minutes of lecture audio into the streaming ASR source
# 4. Cleans up server on Ctrl+C / exit

set -e

PORT=8765
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "=========================================================="
echo "    CS3103 LiveRecall: Real-Lecture ASR Demonstration     "
echo "=========================================================="

# Auto-setup on new environment if not yet installed
if [ ! -d "${ROOT_DIR}/bonus_asr/.venv-asr" ] || [ ! -d "${ROOT_DIR}/bonus_asr/model" ]; then
    echo "ASR virtual environment or model not found."
    echo "Bootstrapping isolated ASR environment via bonus_asr/install_asr.sh..."
    bash "${ROOT_DIR}/bonus_asr/install_asr.sh"
    echo ""
fi

# Detect python interpreters
if [ -f "${ROOT_DIR}/.venv/bin/python3" ]; then
    PY_SERVER="${ROOT_DIR}/.venv/bin/python3"
elif [ -f "${ROOT_DIR}/bonus_asr/.venv-asr/bin/python3" ]; then
    PY_SERVER="${ROOT_DIR}/bonus_asr/.venv-asr/bin/python3"
else
    PY_SERVER="python3"
fi

if [ -d "${ROOT_DIR}/bonus_asr/.venv-asr/bin" ]; then
    export PATH="${ROOT_DIR}/bonus_asr/.venv-asr/bin:${PATH}"
    PY_ASR="${ROOT_DIR}/bonus_asr/.venv-asr/bin/python3"
else
    PY_ASR="python3"
fi

# Check if solution_server is already running
if lsof -Pi :${PORT} -sTCP:LISTEN -t >/dev/null ; then
    echo "LiveRecall server is already running on port ${PORT}."
    SERVER_PID=""
else
    echo "Starting LiveRecall solution_server.py on port ${PORT}..."
    export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH}"
    "${PY_SERVER}" solution_server.py --port ${PORT} &
    SERVER_PID=$!
    sleep 1.5
fi

cleanup() {
    echo ""
    echo "Stopping demo..."
    if [ -n "${SERVER_PID}" ]; then
        echo "Terminating server (PID ${SERVER_PID})..."
        kill "${SERVER_PID}" 2>/dev/null || true
    fi
    echo "Done."
}
trap cleanup EXIT INT TERM

echo ""
echo "----------------------------------------------------------"
echo "1. OPEN YOUR BROWSER CLIENT TO VIEW LIVE CAPTIONS:"
echo "   file://${ROOT_DIR}/client/index.html"
echo "   (or serve client/ with: python -m http.server 8000 --directory client)"
echo "----------------------------------------------------------"
echo ""
read -p "Press [Enter] once your browser client is opened and connected..."

echo ""
echo "Streaming 3-minute real-lecture audio through ASR pipeline..."
echo "Watch the browser client: provisional revisions will appear in italics,"
echo "and finalize into solid sentences as the lecturer pauses."
echo ""

# Detect input audio/video (defaults to my_lecture.mp4)
INPUT_FILE="${1:-${ROOT_DIR}/bonus_asr/my_lecture.mp4}"
if [ ! -f "${INPUT_FILE}" ]; then
    echo "Error: Input media file not found: ${INPUT_FILE}"
    echo "Please place a lecture video at bonus_asr/my_lecture.mp4 or specify a path as argument."
    exit 1
fi

ENGINE_ARG="--engine auto"
if [ -d "${ROOT_DIR}/bonus_asr/model" ]; then
    ENGINE_ARG="--engine vosk --model-path ${ROOT_DIR}/bonus_asr/model"
fi

echo ""
echo "Input media: ${INPUT_FILE}"
echo "ASR Engine:  ${ENGINE_ARG}"
echo ""

# Check if input is video or audio
if [[ "${INPUT_FILE}" == *.mp4 || "${INPUT_FILE}" == *.mkv || "${INPUT_FILE}" == *.avi ]]; then
    MEDIA_ARG="--video ${INPUT_FILE}"
else
    MEDIA_ARG="--audio ${INPUT_FILE}"
fi

# Run ASR source
export PYTHONPATH="${ROOT_DIR}/bonus_asr:${ROOT_DIR}:${PYTHONPATH}"
"${PY_ASR}" "${ROOT_DIR}/bonus_asr/asr_source.py" \
    --uri "ws://127.0.0.1:${PORT}" \
    ${MEDIA_ARG} \
    ${ENGINE_ARG} \
    --speed 1.0

echo ""
echo "Demonstration complete!"

