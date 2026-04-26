@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 优先用 py launcher（Windows 上指向 Python 3），再 fallback 到 python3 / python
where py >nul 2>&1
if %errorlevel% equ 0 (
  py -3 serve.py
  goto :end
)
where python3 >nul 2>&1
if %errorlevel% equ 0 (
  python3 serve.py
  goto :end
)
where python >nul 2>&1
if %errorlevel% equ 0 (
  python serve.py
  goto :end
)
echo.
echo  未检测到 Python 3。请安装 Python 3 后重试。
echo  下载: https://www.python.org/downloads/
echo.
pause
exit /b 1
:end
pause
