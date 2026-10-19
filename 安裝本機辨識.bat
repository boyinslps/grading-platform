@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== 安裝本機白板辨識（RapidOCR，離線、不送 AI）=====
echo 需要網路，約 320 MB，幾分鐘；裝完之後辨識不需要網路。
set "PY="
if exist "%~dp0runtime\python\python.exe" set "PY=%~dp0runtime\python\python.exe"
if not defined PY for /d %%D in ("%~dp0..\*") do if exist "%%D\runtime\python\python.exe" set "PY=%%D\runtime\python\python.exe"
if not defined PY (
  echo [錯誤] 找不到可攜 Python（runtime\python）。
  pause
  exit /b 1
)
"%PY%" "%~dp0install_ocr.py"
echo.
pause
