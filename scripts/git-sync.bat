@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
git push %*
if errorlevel 1 exit /b 1
git pull
echo.
echo push + pull 完成
