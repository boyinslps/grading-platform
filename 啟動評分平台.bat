@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== Grading Platform =====
echo Open: http://127.0.0.1:8780/teacher.html
echo (AI grading / Classroom features need the Cockpit at http://127.0.0.1:8770)
echo Close this window to stop the server.
set "PY="
if exist "%~dp0runtime\python\python.exe" set "PY=%~dp0runtime\python\python.exe"
if not defined PY for /d %%D in ("%~dp0..\*") do if exist "%%D\runtime\python\python.exe" set "PY=%%D\runtime\python\python.exe"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo.
  echo [錯誤] 找不到可用的 Python（本資料夾沒有 runtime\python，旁邊也沒有工作台，系統也沒裝 Python）。
  echo 請確認 runtime 資料夾有跟著一起複製過來。
  pause
  exit /b 1
)
start "" http://127.0.0.1:8780/teacher.html
"%PY%" "%~dp0server.py"
echo.
echo Server stopped.
pause
