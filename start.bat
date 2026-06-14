@echo off
title 视频音频提取工具
cd /d "%~dp0"

set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

echo.
echo ================================================
echo   视频音频提取工具
echo ================================================
echo.

"%PYTHON%" start.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 启动失败，请尝试手动运行:
    echo   python start.py
    echo.
    pause
)
