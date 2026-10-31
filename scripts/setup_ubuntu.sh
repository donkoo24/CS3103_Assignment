#!/usr/bin/env bash
set -euo pipefail
# Run in the Ubuntu VM, from the repository root.
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip iproute2
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python submission_check.py
