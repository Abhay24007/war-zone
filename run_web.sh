#!/usr/bin/env bash
# Serve WAR ZONE in the browser on http://localhost:8000
set -e
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
python3 -m pygbag .
