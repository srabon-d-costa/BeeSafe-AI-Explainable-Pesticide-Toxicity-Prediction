@echo off
setlocal
cd /d "%~dp0.."
echo Starting BeeSafe AI from: %CD%
python -m streamlit run app\app.py
pause
