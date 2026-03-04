@echo off
cd /d "c:\Users\TF536AC\OneDrive - EY\WORK\ai_engineer_poc_orchestrator"
py -3.11 --version > _output.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> _output.txt 2>&1
