@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist .venv (
    echo [1/3] 가상환경 생성 중...
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv .venv
)

echo [2/3] 패키지 확인 중...
.venv\Scripts\python.exe -m pip install -q -r requirements.txt

echo [3/3] 서버 시작: http://localhost:8600
start "" http://localhost:8600
.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8600
