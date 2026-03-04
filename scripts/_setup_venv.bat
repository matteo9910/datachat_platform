@echo off
set LOGFILE=%~dp0..\backend\logs\_setup.log

echo === Setting up Python virtual environment === > "%LOGFILE%" 2>&1
py -3.11 --version >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11 not found via py -3.11 >> "%LOGFILE%" 2>&1
    exit /b 1
)

echo Creating venv... >> "%LOGFILE%" 2>&1
cd /d "%~dp0..\backend"
py -3.11 -m venv venv >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Failed to create venv >> "%LOGFILE%" 2>&1
    exit /b 1
)

echo Installing dependencies... >> "%LOGFILE%" 2>&1
call venv\Scripts\activate.bat >> "%LOGFILE%" 2>&1
python --version >> "%LOGFILE%" 2>&1
pip install --upgrade pip >> "%LOGFILE%" 2>&1
pip install psycopg2-binary==2.9.9 pandas==2.2.0 python-dotenv==1.0.1 >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo ERROR: Failed to install dependencies >> "%LOGFILE%" 2>&1
    exit /b 1
)

echo. >> "%LOGFILE%" 2>&1
echo === Running dataset import === >> "%LOGFILE%" 2>&1
cd /d "%~dp0.."
python scripts\import_kaggle_dataset.py >> "%LOGFILE%" 2>&1

echo. >> "%LOGFILE%" 2>&1
echo === SETUP COMPLETE === >> "%LOGFILE%" 2>&1
