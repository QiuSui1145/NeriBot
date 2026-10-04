@echo off
cd /d "%~dp0"
title 风又音理 QQ 机器人 - 启动控制台

echo ========================================================
echo         风又音理 [Kazamata Neri] QQ 机器人系统
echo ========================================================
echo.

set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"
set "PY_CMD="

:: 1. 优先使用专属虚拟环境 .venv
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    goto check_env
)

:: 2. 检查系统是否有兼容的 py 启动器
py -3.11 -c "exit()" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.11"
    goto check_env
)
py -3.12 -c "exit()" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto check_env
)
py -3.10 -c "exit()" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.10"
    goto check_env
)

:: 3. 检查系统全局 python
where python >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto check_env
)

:: 4. 检查通用 py 启动器
where py >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py"
    goto check_env
)

echo [错误] 未检测到 Python 运行环境！
echo 请先双击运行 install.bat 安装环境，或手动安装 Python 3.10 ~ 3.12 并加入系统 PATH。
pause
exit /b 1

:check_env
echo [环境] 使用 Python: %PY_CMD%

:: 2. 自动检测核心依赖
"%PY_CMD%" -c "import fastapi, uvicorn, chromadb, sentence_transformers, httpx, requests" >nul 2>nul
if not errorlevel 1 goto deps_ok

echo.
echo ========================================================
echo [提示] 检测到部分运行依赖尚未安装或不完整。
echo [提示] 建议先双击 install.bat 运行一键配置向导。
echo 正在尝试自动通过清华镜像源安装依赖，请稍候...
echo ========================================================
"%PY_CMD%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [警告] 依赖自动安装出现错误，若启动失败请手动执行: install.bat
) else (
    echo [OK] 依赖安装完成！
)
echo.

:deps_ok
:: 检查 config.json
if not exist "config\config.json" (
    if exist "config\config.example.json" (
        copy "config\config.example.json" "config\config.json" >nul
        echo [提示] 已根据模板自动创建 config\config.json
    )
)

echo [OK] Python 核心依赖检测通过！
echo [Web] 控制台地址: http://127.0.0.1:8088
echo.

:: 3. 检查 GPT-SoVITS 语音服务状态 (9880 端口)
netstat -ano | findstr :9880 >nul 2>nul
if not errorlevel 1 goto tts_ok

echo [提示] GPT-SoVITS 语音服务 [9880 端口] 尚未运行。
echo        可在 WebUI 控制台的【TTS 语音设置】页中点击【一键启动 TTS】，
echo        或直接双击运行 start_tts.bat 启动语音引擎。
goto tts_done

:tts_ok
echo [OK] GPT-SoVITS 语音服务 [端口 9880] 在线正常！

:tts_done
echo.
echo 正在启动机器人与 WebUI 主服务...
echo ========================================================
echo.

chcp 65001 >nul
"%PY_CMD%" -u main.py

if errorlevel 1 (
    chcp 936 >nul
    echo.
    echo [x] 机器人异常退出，退出码: %errorlevel%
)

echo.
pause