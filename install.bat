@echo off
cd /d "%~dp0"
title 风又音理 QQ 机器人 - 自动安装环境与依赖

echo ========================================================
echo         风又音理 [Kazamata Neri] 环境初始化向导
echo ========================================================
echo.

set "PY_CMD="

:: 1. 检查已有的 .venv
if exist ".venv\Scripts\python.exe" (
    echo [提示] 检测到已存在虚拟环境: .venv\Scripts\python.exe
    set "PY_CMD=.venv\Scripts\python.exe"
    goto install_deps
)

:: 2. 检查是否有兼容的 py 启动器 (推荐 Python 3.10 ~ 3.12)
py -3.11 -c "exit()" >nul 2>nul
if not errorlevel 1 (
    echo [提示] 检测到 Python 3.11，正在创建专属虚拟环境 .venv ...
    py -3.11 -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PY_CMD=.venv\Scripts\python.exe"
        echo [OK] 专属虚拟环境 .venv 创建成功！
        goto install_deps
    )
)

py -3.12 -c "exit()" >nul 2>nul
if not errorlevel 1 (
    echo [提示] 检测到 Python 3.12，正在创建专属虚拟环境 .venv ...
    py -3.12 -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PY_CMD=.venv\Scripts\python.exe"
        echo [OK] 专属虚拟环境 .venv 创建成功！
        goto install_deps
    )
)

py -3.10 -c "exit()" >nul 2>nul
if not errorlevel 1 (
    echo [提示] 检测到 Python 3.10，正在创建专属虚拟环境 .venv ...
    py -3.10 -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PY_CMD=.venv\Scripts\python.exe"
        echo [OK] 专属虚拟环境 .venv 创建成功！
        goto install_deps
    )
)

:: 3. 检查系统全局 python
where python >nul 2>nul
if not errorlevel 1 (
    echo [提示] 检测到系统全局 Python，正在创建虚拟环境 .venv ...
    python -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PY_CMD=.venv\Scripts\python.exe"
        echo [OK] 专属虚拟环境 .venv 创建成功！
        goto install_deps
    )
)

:: 4. 检查通用 py 启动器
where py >nul 2>nul
if not errorlevel 1 (
    echo [提示] 检测到 Python 启动器 py，正在创建虚拟环境 .venv ...
    py -m venv .venv
    if exist ".venv\Scripts\python.exe" (
        set "PY_CMD=.venv\Scripts\python.exe"
        echo [OK] 专属虚拟环境 .venv 创建成功！
        goto install_deps
    )
)

echo [错误] 未在系统中检测到合适的 Python 环境！
echo 本项目深度学习与向量检索核心（ChromaDB/SentenceTransformers）推荐使用 Python 3.10 ~ 3.12。
echo 请前往官网下载安装 Python (安装时务必勾选 "Add Python to PATH"):
echo https://www.python.org/downloads/
echo.
pause
exit /b 1

:install_deps
echo.
echo [1/3] 正在升级 pip 工具...
"%PY_CMD%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo [2/3] 正在通过清华镜像源安装 requirements.txt 运行依赖...
"%PY_CMD%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo [警告] 部分依赖安装遇到问题，请检查网络连接后重试。
    pause
    exit /b 1
)

echo.
echo.
echo [3/4] 检查离线向量检索模型 (bge-small-zh-v1.5)...
if not exist "models\embedding\bge-small-zh-v1.5\model.safetensors" (
    echo 正在通过国内高速镜像拉取 BGE 离线向量模型...
    "%PY_CMD%" -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', local_dir='models/embedding/bge-small-zh-v1.5')"
)
echo [OK] 离线向量模型检测完成！

echo.
echo [4/4] 检查配置文件与初始数据...
if not exist "config\config.json" (
    if exist "config\config.example.json" (
        copy "config\config.example.json" "config\config.json" >nul
        echo [OK] 已根据模板生成 config\config.json
    )
)

echo.
echo ========================================================
echo        [SUCCESS] 风又音理环境与依赖安装校验完成！
echo ========================================================
echo.
echo 下一步操作提示：
echo 1. 双击运行 start.bat 启动机器人服务与 Web 控制台；
echo 2. 在浏览器中打开: http://127.0.0.1:8088
echo 3. 默认登录管理员密码为: admin
echo 4. 在控制台【系统配置】页面填入您的 LLM API Key；
echo 5. 在【TTS 语音设置】页面配置您的 GPT-SoVITS 根目录。
echo.
pause