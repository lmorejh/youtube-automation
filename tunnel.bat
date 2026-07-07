@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] 로컬 서버 시작...
start "youtube-automation-server" cmd /c run.bat

echo [2/2] Cloudflare 터널 연결 중... 아래에 표시되는 https://???.trycloudflare.com 주소로 어디서든 접속하세요.
echo      (주소는 터널을 새로 켤 때마다 바뀝니다. 접속 시 비밀번호는 .env의 APP_PASSWORD)
echo.
cloudflared tunnel --url http://localhost:8600
