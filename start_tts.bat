@echo off
cd /d "%~dp0"
title GPT-SoVITS 语音合成服务启动器

echo ========================================================
echo       GPT-SoVITS 语音合成 API 服务启动器
echo ========================================================
echo.

set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

"%PY_CMD%" -c "from src.config import config_manager; import os, sys; d = getattr(config_manager.config.tts, 'gpt_sovits_dir', ''); sys.exit(0 if (d and os.path.exists(d)) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [提示] 尚未配置有效的 GPT-SoVITS 根目录！
    echo.
    echo 推荐配置步骤：
    echo 1. 运行 start.bat 打开 WebUI 控制台 (http://127.0.0.1:8088)；
    echo 2. 进入【TTS 语音设置】页，输入本地 GPT-SoVITS 根目录；
    echo 3. 点击【安装补丁】并【一键启动 TTS】即可；
    echo    系统将自动完成定制接口适配并生成本地启动脚本。
    echo.
    echo ========================================================
    pause
    exit /b 1
)

:: 已配置有效目录，调用管理器执行启动
echo 正在拉起 GPT-SoVITS 语音合成服务...
"%PY_CMD%" -c "from src.tts_service_manager import TTSServiceManager; TTSServiceManager().start_service()"

if errorlevel 1 (
    echo [x] 启动出现异常。
    pause
)