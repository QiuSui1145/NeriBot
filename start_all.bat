@echo off
cd /d "%~dp0"
title 风又音理 - 全服务启动器

echo ========================================================
echo       风又音理 [Kazamata Neri] 全服务启动器
echo ========================================================
echo.

:: 检查 9880 端口是否已经在运行
netstat -ano | findstr :9880 >nul 2>nul
if not errorlevel 1 goto tts_already_running

echo 步骤 1/2: 正在后台拉起 GPT-SoVITS 语音服务...
start "GPT-SoVITS TTS Engine" "%~dp0start_tts.bat"

echo 正在等待语音引擎端口 9880 联通...
set count=0
:wait_loop
ping 127.0.0.1 -n 2 >nul
netstat -ano | findstr :9880 >nul 2>nul
if not errorlevel 1 goto tts_ready
set /a count+=1
if %count% geq 8 (
    echo [提示] 语音服务正在后台预热加载模型，主程序继续启动...
    goto start_bot
)
goto wait_loop

:tts_already_running
echo [OK] 检测到 GPT-SoVITS 语音服务已经在运行中 [端口 9880 已就绪]，跳过重复启动。
goto start_bot

:tts_ready
echo [OK] GPT-SoVITS 语音服务端口已就绪！

:start_bot
echo.
echo 步骤 2/2: 正在启动机器人与 WebUI 主服务...
echo ========================================================
call "%~dp0start.bat"