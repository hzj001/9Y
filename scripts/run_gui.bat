@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动六合彩分析工具...
python lhc_gui.py
if errorlevel 1 (
    echo.
    echo 启动失败，请确认已安装 Python 并执行: pip install -r requirements.txt
    pause
)
