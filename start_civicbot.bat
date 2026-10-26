@echo off
chcp 65001 >nul
title CivicBot - Khoi dong he thong
cd /d "%~dp0"

echo ========================================
echo        DANG KHOI DONG CIVICBOT
echo ========================================
echo.

docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop chua duoc khoi dong.
    echo Vui long mo Docker Desktop roi chay lai file nay.
    pause
    exit /b 1
)

if not exist ".env" (
    echo Chua co file .env - dang tao tu .env.example ...
    copy ".env.example" ".env" >nul
    echo HAY MO FILE .env, DIEN GEMINI_API_KEY VA ADMIN_API_KEY ROI CHAY LAI.
    notepad ".env"
    pause
    exit /b 1
)

echo Dang build va khoi dong cac container...
docker compose up -d --build
if errorlevel 1 (
    echo Khong the khoi dong CivicBot. Kiem tra Docker Desktop va docker-compose.yml.
    pause
    exit /b 1
)

echo Dang cho he thong san sang...
timeout /t 10 /nobreak >nul
docker compose ps

start "" "http://localhost:5173"
echo.
echo Giao dien : http://localhost:5173
echo Backend   : http://localhost:8000/docs
echo Kiem tra  : chay demo_check.bat
pause
