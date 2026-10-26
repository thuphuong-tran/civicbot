@echo off
chcp 65001 >nul
title CivicBot - Kiem tra demo
cd /d "%~dp0"
REM Doc ADMIN_API_KEY va mat khau MySQL tu .env
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if "%%A"=="ADMIN_API_KEY" set ADMIN_API_KEY=%%B
    if "%%A"=="MYSQL_PASSWORD" set MYSQL_PASSWORD=%%B
    if "%%A"=="MYSQL_USER" set MYSQL_USER=%%B
)
if "%MYSQL_USER%"=="" set MYSQL_USER=civicbot

echo ===== DEMO 1: 3 CONTAINER DANG CHAY =====
docker compose ps
echo.
echo ===== DEMO 1: BACKEND KET NOI MYSQL (/health) =====
curl -s http://localhost:8000/health
echo.
echo.
echo ===== DEMO 1: DU LIEU TRONG MYSQL =====
docker exec civicbot-mysql mysql --default-character-set=utf8mb4 -u%MYSQL_USER% -p%MYSQL_PASSWORD% civicbot -e "SELECT COUNT(*) AS so_thu_tuc FROM procedures; SELECT procedure_code, name FROM procedures LIMIT 14; SELECT COUNT(*) AS so_cau_hoi_da_luu FROM chat_history;"
echo.
echo ===== DEMO 3: CHAY KIEM THU (quick) =====
curl -s -X POST http://localhost:8000/api/system-tests/run -H "Content-Type: application/json" -H "X-Admin-Key: %ADMIN_API_KEY%" -d "{\"suite\":\"quick\"}" > test_result.json
python -c "import json;d=json.load(open('test_result.json',encoding='utf-8'));print('Tong:',d.get('total'),'PASS:',d.get('passed'),'FAIL:',d.get('failed'));[print(r['status'],r['test_id'],r['name']) for r in d.get('results',[])]" 2>nul || type test_result.json
echo.
pause
