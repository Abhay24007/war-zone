@echo off
REM Serve WAR ZONE in the browser on http://localhost:8000
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m pygbag .
