@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== Grading Platform =====
echo Open: http://127.0.0.1:8780/teacher.html
echo (AI grading / Classroom features need the Cockpit at http://127.0.0.1:8770)
echo Close this window to stop the server.
start "" http://127.0.0.1:8780/teacher.html
set "PY=python"
for /d %%D in ("%~dp0..\*") do if exist "%%D\runtime\python\python.exe" set "PY=%%D\runtime\python\python.exe"
"%PY%" "%~dp0server.py"
echo.
echo Server stopped.
pause
