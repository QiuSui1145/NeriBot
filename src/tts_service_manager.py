"""
GPT-SoVITS 本地服务管理、补丁安装与一键自动化启动模块。
"""

import os
import sys
import time
import socket
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


class TTSServiceManager:
    """负责 GPT-SoVITS 本地服务管理、补丁安装与启动脚本自动化配置。"""

    def __init__(self, bot_root: Optional[Path] = None):
        self.bot_root = bot_root or Path(__file__).resolve().parent.parent
        self.log_file = self.bot_root / "cache" / "tts_service.log"
        self._process: Optional[subprocess.Popen] = None

    def is_port_in_use(self, port: int = 9880, host: str = "127.0.0.1") -> bool:
        """检测目标端口是否已被监听 (即服务是否在线)。"""
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取当前 TTS 服务健康状态。"""
        from src.config import config_manager
        cfg = config_manager.config.tts
        port = 9880
        try:
            import urllib.parse
            parsed = urllib.parse.urlparse(cfg.api_url)
            if parsed.port:
                port = parsed.port
        except Exception:
            pass

        running = self.is_port_in_use(port)
        return {
            "running": running,
            "port": port,
            "api_url": cfg.api_url,
            "gpt_sovits_dir": getattr(cfg, "gpt_sovits_dir", ""),
            "gpt_weights_path": getattr(cfg, "gpt_weights_path", ""),
            "sovits_weights_path": getattr(cfg, "sovits_weights_path", ""),
            "mode": cfg.mode,
            "enabled": cfg.enabled,
        }

    def switch_weights(self, gpt_weights_path: Optional[str] = None, sovits_weights_path: Optional[str] = None) -> Dict[str, Any]:
        """在线热切换或保存 GPT 与 SoVITS 模型权重路径。"""
        from src.config import config_manager
        import urllib.parse
        import requests

        cfg = config_manager.config.tts
        if gpt_weights_path is not None:
            cfg.gpt_weights_path = gpt_weights_path.strip()
        if sovits_weights_path is not None:
            cfg.sovits_weights_path = sovits_weights_path.strip()
        config_manager.save()

        # 如果 target_dir 下存在 tts_infer.yaml，则同步写入以便下一次启动读取
        try:
            target_dir = Path(getattr(cfg, "gpt_sovits_dir", "")).resolve()
            infer_yaml = target_dir / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
            if infer_yaml.exists():
                lines = infer_yaml.read_text(encoding="utf-8").splitlines()
                new_lines = []
                in_default = False
                for line in lines:
                    if line.strip() == "default:":
                        in_default = True
                    elif line and not line.startswith(" ") and not line.startswith("\t"):
                        in_default = False
                    
                    if in_default and "t2s_weights_path:" in line and cfg.gpt_weights_path:
                        indent = len(line) - len(line.lstrip())
                        new_lines.append(f"{' ' * indent}t2s_weights_path: {cfg.gpt_weights_path.replace(os.sep, '/')}")
                    elif in_default and "vits_weights_path:" in line and cfg.sovits_weights_path:
                        indent = len(line) - len(line.lstrip())
                        new_lines.append(f"{' ' * indent}vits_weights_path: {cfg.sovits_weights_path.replace(os.sep, '/')}")
                    else:
                        new_lines.append(line)
                infer_yaml.write_text("\n".join(new_lines), encoding="utf-8")
        except Exception as e:
            print(f"[TTSManager] 同步 tts_infer.yaml 提示: {e}")

        running = self.is_port_in_use(9880)
        messages = []

        if running:
            # 1. 尝试热切换 GPT 权重
            if cfg.gpt_weights_path:
                try:
                    q = urllib.parse.quote(cfg.gpt_weights_path)
                    res = requests.get(f"http://127.0.0.1:9880/set_gpt_weights?weights_path={q}", timeout=45)
                    if res.status_code == 200:
                        messages.append("GPT 权重已在线热重载生效")
                    else:
                        messages.append(f"GPT 权重热重载提示: {res.text}")
                except Exception as e:
                    messages.append(f"GPT 权重切换异常: {e}")

            # 2. 尝试热切换 SoVITS 权重
            if cfg.sovits_weights_path:
                try:
                    q = urllib.parse.quote(cfg.sovits_weights_path)
                    res = requests.get(f"http://127.0.0.1:9880/set_sovits_weights?weights_path={q}", timeout=45)
                    if res.status_code == 200:
                        messages.append("SoVITS 权重已在线热重载生效")
                    else:
                        messages.append(f"SoVITS 权重热重载提示: {res.text}")
                except Exception as e:
                    messages.append(f"SoVITS 权重切换异常: {e}")
        else:
            messages.append("模型权重路径已更新并持久化保存，将在下次启动 TTS 服务时自动载入")

        return {
            "status": "success",
            "running": running,
            "message": "；".join(messages),
            "gpt_weights_path": cfg.gpt_weights_path,
            "sovits_weights_path": cfg.sovits_weights_path
        }


    def install_patch(self, gpt_sovits_dir_str: str) -> Dict[str, Any]:
        """将定制补丁文件与配置自动安装到指定的 GPT-SoVITS 目录，并自动生成对应的启动脚本。"""
        if not gpt_sovits_dir_str or not gpt_sovits_dir_str.strip():
            raise ValueError("GPT-SoVITS 根目录不能为空！")

        target_dir = Path(gpt_sovits_dir_str.strip()).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            raise FileNotFoundError(f"目录不存在: {target_dir}")

        # 检查是否为合法的 GPT-SoVITS 目录
        has_api = (target_dir / "api_v2.py").exists() or (target_dir / "api.py").exists()
        has_pkg = (target_dir / "GPT_SoVITS").exists()
        if not (has_api or has_pkg):
            raise ValueError("指定目录未检测到 api_v2.py 或 GPT_SoVITS 核心文件夹，请确认是否为 GPT-SoVITS 根目录！")

        # 1. 备份原有的 api_v2.py
        target_api_v2 = target_dir / "api_v2.py"
        backup_api_v2 = target_dir / "api_v2.py.bak"
        if target_api_v2.exists() and not backup_api_v2.exists():
            try:
                shutil.copy2(target_api_v2, backup_api_v2)
                print(f"[TTSManager] 已备份原有 api_v2.py -> {backup_api_v2}")
            except Exception as e:
                print(f"[TTSManager] 备份原有 api_v2.py 提示: {e}")

        # 2. 覆盖复制定制补丁 api_v2.py
        patch_src = self.bot_root / "patches" / "gpt_sovits" / "api_v2.py"
        if not patch_src.exists():
            raise FileNotFoundError(f"项目中缺少补丁文件: {patch_src}")
        shutil.copy2(patch_src, target_api_v2)
        print(f"[TTSManager] 成功安装定制 api_v2.py 到 {target_api_v2}")

        # 3. 复制参考音频 (若目标目录缺少)
        ref_audio_src = self.bot_root / "patches" / "gpt_sovits" / "ref_audio" / "ner0092.wav"
        if ref_audio_src.exists():
            dest_ref_dir = target_dir / "ref_audio"
            dest_ref_dir.mkdir(parents=True, exist_ok=True)
            dest_ref_file = dest_ref_dir / "ner0092.wav"
            if not dest_ref_file.exists():
                shutil.copy2(ref_audio_src, dest_ref_file)

        # 4. 自动生成或更新 start_tts.bat 脚本
        self.generate_start_tts_script(target_dir)

        # 5. 更新 config.json 中的 gpt_sovits_dir
        from src.config import config_manager
        config_manager.config.tts.gpt_sovits_dir = str(target_dir)
        config_manager.save()

        return {
            "status": "success",
            "message": f"定制补丁已成功安装至 {target_dir}，并已自动生成 start_tts.bat 启动脚本！",
            "gpt_sovits_dir": str(target_dir),
        }

    def generate_start_tts_script(self, gpt_sovits_dir: Path):
        """自动在 Bot 根目录生成/更新精准契合该 GPT-SoVITS 目录的 start_tts.bat。"""
        start_bat_path = self.bot_root / "start_tts.bat"

        # 判断 runtime python
        runtime_python = gpt_sovits_dir / "runtime" / "python.exe"
        py_exec = f'"{runtime_python}"' if runtime_python.exists() else "python"

        bat_content = f"""@echo off
cd /d "{gpt_sovits_dir}"
title GPT-SoVITS 语音合成服务 [端口 9880]

echo ========================================================
echo       GPT-SoVITS 语音合成 API 服务 [端口 9880]
echo ========================================================
echo.
echo 工作目录: {gpt_sovits_dir}
echo 接口地址: http://127.0.0.1:9880/tts
echo 正在启动语音合成服务...
echo ========================================================
echo.

set "PATH={gpt_sovits_dir}\\runtime;%PATH%"
set "PYTHONUNBUFFERED=1"
set "PYTHONIOENCODING=utf-8"

chcp 65001 >nul
{py_exec} api_v2.py -a 0.0.0.0 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml

if errorlevel 1 (
    chcp 936 >nul
    echo.
    echo [x] TTS 服务异常退出，退出码: %errorlevel%
)

echo.
pause
"""
        crlf_content = bat_content.strip().replace('\r\n', '\n').replace('\n', '\r\n') + '\r\n'
        with open(start_bat_path, 'wb') as f:
            f.write(crlf_content.encode('gbk'))
        print(f"[TTSManager] 已更新 start_tts.bat: {start_bat_path}")

    def start_service(self) -> Dict[str, Any]:
        """一键在后台启动 GPT-SoVITS 服务。"""
        if self.is_port_in_use(9880):
            return {"status": "already_running", "message": "TTS 服务已在运行中 (端口 9880 已就绪)"}

        from src.config import config_manager
        cfg = config_manager.config.tts
        gpt_sovits_dir = Path(getattr(cfg, "gpt_sovits_dir", r"D:\GPT-SoVITS\GPT-SoVITS-v2pro-20250604"))

        if not gpt_sovits_dir.exists():
            raise FileNotFoundError(f"找不到 GPT-SoVITS 根目录: {gpt_sovits_dir}，请先在界面设置并安装补丁！")

        runtime_python = gpt_sovits_dir / "runtime" / "python.exe"
        python_exe = str(runtime_python) if runtime_python.exists() else "python"

        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_out = open(self.log_file, "a", encoding="utf-8")

        cmd = [
            python_exe,
            "api_v2.py",
            "-a", "0.0.0.0",
            "-p", "9880",
            "-c", "GPT_SoVITS/configs/tts_infer.yaml"
        ]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if runtime_python.exists():
            env["PATH"] = f"{runtime_python.parent};" + env.get("PATH", "")

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        self._process = subprocess.Popen(
            cmd,
            cwd=str(gpt_sovits_dir),
            stdout=log_out,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=creationflags,
        )

        for _ in range(5):
            time.sleep(1.0)
            if self.is_port_in_use(9880):
                return {"status": "success", "message": "GPT-SoVITS 服务已成功启动并在端口 9880 就绪！"}

        return {"status": "starting", "message": "GPT-SoVITS 服务已在后台拉起，模型加载中，请稍候约 5-10 秒..."}

    def stop_service(self) -> Dict[str, Any]:
        """停止正在运行的 GPT-SoVITS 服务。"""
        # 首先尝试通过 /control 接口友好退出
        try:
            import requests
            requests.get("http://127.0.0.1:9880/control?command=exit", timeout=2)
            time.sleep(1.0)
        except Exception:
            pass

        # 如果端口依然被占用，查找占用 9880 的 PID 并强制终止
        if self.is_port_in_use(9880):
            try:
                out = subprocess.check_output('netstat -ano | findstr :9880', shell=True).decode()
                pids = set()
                for line in out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and "LISTENING" in line:
                        pids.add(parts[-1])
                for pid in pids:
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            except Exception as e:
                print(f"[TTSManager] 终止进程失败: {e}")

        time.sleep(1.0)
        is_stopped = not self.is_port_in_use(9880)
        return {
            "status": "success" if is_stopped else "failed",
            "message": "TTS 服务已停止" if is_stopped else "未能完全停止，请手动检查 9880 端口占用"
        }

    def get_logs(self, max_lines: int = 80) -> str:
        """获取最近运行日志。"""
        if not self.log_file.exists():
            return "暂无 TTS 运行日志。"
        try:
            lines = self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-max_lines:])
        except Exception as e:
            return f"读取日志失败: {e}"


tts_service_manager = TTSServiceManager()
