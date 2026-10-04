# Kazamata Neri (风又音理) AI Companion & QQ Bot

<div align="center">

<img src="web/static/img/avatar.png" width="160" height="160" alt="Kazamata Neri Avatar" style="border-radius: 50%; box-shadow: 0 8px 24px rgba(0,0,0,0.3);" />

<h3>An Immersive Galgame-Canon AI Companion & QQ Robot System</h3>

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-brightgreen)](https://www.python.org/)
[![Protocol](https://img.shields.io/badge/Protocol-OneBot%20v11-orange)](https://github.com/botuniverse/onebot-11)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorStore-red)](https://www.trychroma.com/)

**Language / 语言切换**:  
👉 **[English](#-english-version)** | **[简体中文](#-中文版-chinese-version)** 👈

</div>

---

## 🌐 English Version

### 📖 Introduction

**Kazamata Neri (风又音理)** is one of the central heroines in the acclaimed visual novel *Ginkiho - Train of the Stars and White Journey* (*星空列车与白的旅行* / *Shiraya*).

This project delivers a **production-grade, Galgame-canon AI companion and OneBot v11 role-play bot**. Unlike generic AI character setups that slip into third-person "fairy-tale narrator" clichés, this system establishes a genuine, deeply bonded first-person relationship between Neri and the user / her brother (*Akira Shirogane* / 钟城 晓). 

Powered by **Large Language Models (OpenAI-compatible)**, **GPT-SoVITS simultaneous voice interpretation**, an **offline local vector memory network (BGE-small-zh-v1.5)**, a **hot-reloadable microkernel plugin architecture**, and a **modern glassmorphism WebUI**, NeriBot brings authentic character emotional resonance into your daily chats.

---

### ✨ Key Features

- 🎭 **Authentic Galgame-Canon Persona (Tidebound Framework)**
  - Rejects third-person storybook cliches. Firmly roots Neri's memories in her canonical past: the Iwate art studio and the 500-yen promise, the cold March rain and heart donation to Mashiro, Akira's summer heatstroke and organ donation, and the enduring train reality: *"Wherever Mashiro goes, the train and our journey follow."*
  - Strict negative constraints prevent robotic greetings, emoji leakage, and unearned familial terms with strangers.
- 🎙️ **Simultaneous Voice Interpretation Dual-Track Protocol**
  - Features an invisible Japanese phonetic audio track generated alongside conversational Chinese.
  - Automatically filters emojis and stage directions to protect voice engines from phoneme clipping and artifacts.
- 🧠 **Offline Semantic Vector Memory Network**
  - Bundled with a lightweight, offline embedding model (`bge-small-zh-v1.5`, ~90MB) for 100% zero-network vector retrieval.
  - Includes Ebbinghaus decay curves, cross-session recall, and knowledge graph persistence.
- 🔌 **Microkernel Architecture & Hot-Reloadable Plugins**
  - Built with formal lifecycle management (`Init -> Enable -> Disable -> Destroy`).
  - Extensible event buses, communication adapters (OneBot v11, Telegram, etc.), and custom vector memory drivers.
- 🖥️ **Glassmorphism WebUI Control Center**
  - Real-time chat with single-message recall, instant context flushing, and sandbox-isolated parameter overrides (temperature, token limits).
  - Live Token usage statistics with per-model pricing, dynamic theme/wallpaper switching, background audio player, and stardust cursor FX.
- 🔒 **Zero Data Leakage & Security Ready**
  - The open-source distribution is completely scrubbed of personal QQ numbers, private passwords, API keys, and chat histories.

---

### 🚀 Quick Start (Windows)

#### Method 1: One-Click Automated Setup (Recommended)

1. **Initialize the Environment**:
   Double-click **`install.bat`**.
   - Automatically detects Python (prefers Python 3.10 ~ 3.12) and creates an isolated `.venv` virtual environment.
   - Automatically installs all core dependencies from the official or Tsinghua mirror.
   - Generates a default secure `config/config.json` based on template.

2. **Launch Services**:
   - **All-in-One (Bot + GPT-SoVITS TTS)**: Double-click **`start_all.bat`**.
   - **Bot & WebUI Only**: Double-click **`start.bat`**.
   - **GPT-SoVITS TTS Only**: Double-click **`start_tts.bat`**.

3. **Open Management Console**:
   Navigate your browser to: **`http://127.0.0.1:8088`**
   - Default Administrator Password: `admin`
   - Navigate to **System Configuration** to configure your LLM Base URL and API Key.

---

### 🤖 QQ Bot Connection (OneBot v11)

NeriBot communicates via the standard **OneBot v11 Reverse WebSocket** protocol. It works out-of-the-box with **NapCatQQ**, **Lagrange**, and **LLOneBot**.

Example with **NapCatQQ**:
1. Open NapCat WebUI (typically `http://127.0.0.1:6099/webui`).
2. Go to **Network Configuration** -> **Add Configuration** -> Select **Reverse WebSocket (ws_reverse)**.
3. Configure the endpoints:
   - **URL**: `ws://127.0.0.1:8088/onebot/v11/ws`
   - **Access Token**: Leave empty (or match `onebot.access_token` in `config/config.json`).
4. Save the configuration. NapCat will connect instantly. The status indicator on the WebUI banner will turn **🟢 Online** and display Neri's QQ number and nickname!

---

### 🔊 GPT-SoVITS TTS Integration

1. Launch NeriBot and open the WebUI console.
2. Go to the **TTS Voice Settings** tab.
3. Enter your local GPT-SoVITS root directory (e.g., `D:\GPT-SoVITS\GPT-SoVITS-v2pro`).
4. Click **Install Patch** — NeriBot will automatically inject CORS & crash-prevention patches (`api_v2.py`), link reference audio (`ner0092.wav`), and generate `start_tts.bat`.
5. Click **Launch TTS Service** to start voice synthesis!

---

### 📁 Directory Structure

```text
.
├── config/                     # Configuration files (config.json protected by .gitignore)
├── data/                       # Runtime persistent data (ChromaDB, TTS reference, UI state)
├── docs/                       # Developer guides & plugin development manual
├── models/                     # Embedded offline models (BGE-small-zh-v1.5)
├── patches/                    # GPT-SoVITS enhancement patch & reference audio
├── plugins/                    # Microkernel plugin directory
├── prompts/                    # Tidebound modular character prompts
├── scripts/                    # Maintenance & memory initialization scripts
├── src/                        # Core backend source code
├── tests/                      # Unit & integration test suites
├── web/                        # Glassmorphism WebUI frontend assets
├── install.bat                 # One-click Windows environment installer
├── start.bat                   # Smart launcher for Bot and WebUI
├── start_all.bat               # Dual-service launcher (TTS + Bot)
├── start_tts.bat               # Standalone GPT-SoVITS launcher
├── LICENSE                     # GNU General Public License v3.0 (GPL-3.0)
└── README.md                   # Bilingual documentation
```

---

<br/>

## 🇨🇳 中文版 (Chinese Version)

### 📖 项目简介

**风又音理 (Kazamata Neri)** 是经典视觉小说《星空列车与白的旅行》(Shiraya) 中的核心女主角之一。

本项目致力于打造一个**高度还原原作情感羁绊、拒绝“说书人”出戏腔调、兼具极高交互拟真度与工程工业级品质**的开源 AI 伴侣机器人系统。支持通过 OneBot v11 协议无缝接入 QQ 等聊天软件，同时提供极具未来感与艺术质感的玻璃拟态 WebUI 管理控制台。

---

### ✨ 核心亮点

- 🎭 **原作全真沉浸人设 (Tidebound 规范)**
  - 彻底摒弃传统 AI 角色常见的“第三方说书人/童话童谣腔”，牢固确立**第一人称“音理”**与用户/哥哥（钟城晓）的深厚羁绊与共同经历。
  - 内置五大原作核心编年史记忆锚点：岩手县画室五百日元誓约、三月冷雨救猫心脏托付、晓的中暑脱水与器官捐献、星空列车决战与真白重生、永恒终局（真白到哪主角团就能到哪）。
- 🎙️ **GPT-SoVITS 拟真同声传译双轨协议**
  - 首创中日双轨隐藏音轨协议，LLM 在流式生成中文亲昵回复的同时，隐蔽输出精准对应的日语假名/罗马音。
  - 自动剥离 Emoji 与生硬括号动作，防止语音合成器出现吞音与杂音，原汁原味还原音理的日常声线与傲娇关切。
- 🧠 **长短期混合记忆网络与离线向量检索**
  - 开箱即用内置轻量级离线向量模型 `bge-small-zh-v1.5`（90MB，零网络依赖），支持记忆重要度衰减、记忆召回、知识图谱与自动持久化。
- 🔌 **微内核插件系统 (Microkernel Architecture)**
  - 拥有严格规范的生命周期管理（Init -> Enable -> Disable -> Destroy），支持热重载、权限控制、事件总线与自定义向量记忆驱动扩展。
- 🖥️ **现代玻璃拟态 WebUI 控制台**
  - 支持单条消息撤回、即时清空上下文、实时 Token 消耗统计（按 ¥/1M 标准计费）、模型温度/输出上限独立调参、动态壁纸、BGM 播放列表与星尘粒子特效。
- 🔒 **严格数据安全与隐私保护**
  - 开源分发版已彻底剔除所有个人敏感信息（QQ号、群号、密钥、聊天日志），开箱即拥有完善的白名单访问控制与 JWT 安全鉴权。

---

### 🚀 快速启动向导 (Windows)

#### 方式一：一键自动安装与启动（推荐）

1. **环境初始化**：
   双击运行根目录下的 **`install.bat`**。
   - 脚本将自动检测 Python 环境（优先检测 Python 3.10 ~ 3.12 并自动创建专属 `.venv` 虚拟环境）；
   - 自动通过清华镜像源安装所有核心运行依赖；
   - 自动根据模板生成安全的 `config/config.json` 配置文件。

2. **启动系统**：
   - **全服务启动（Bot + TTS）**：双击运行 **`start_all.bat`**；
   - **独立启动 Bot 与 Web 控制台**：双击运行 **`start.bat`**；
   - **独立启动 GPT-SoVITS 语音服务**：双击运行 **`start_tts.bat`**。

3. **进入管理控制台**：
   打开浏览器访问：**`http://127.0.0.1:8088`**
   - 默认管理员密码：`admin`
   - 进入【系统配置】页面填入您的 OpenAI 兼容接口 Base URL 与 API Key。

---

### 🤖 QQ 机器人连接配置 (OneBot v11)

本项目通过标准的 **OneBot v11 反向 WebSocket** 协议与 QQ 框架通信，完美兼容 **NapCatQQ**、**Lagrange**、**LLOneBot** 等主流框架。

以 **NapCatQQ** 为例：
1. 打开 NapCat WebUI 管理页面（通常为 `http://127.0.0.1:6099/webui`）；
2. 进入【网络配置】->【添加配置】-> 选择 **反向 WebSocket (ws_reverse)**；
3. 配置参数：
   - **URL / 地址**：`ws://127.0.0.1:8088/onebot/v11/ws`
   - **Token / 密钥**：留空（或与 `config/config.json` 中的 `onebot.access_token` 保持一致）
4. 保存配置后，NapCat 将自动握手连接。WebUI 控制台顶部的状态指示灯将立即变为 **🟢 已连接 (在线)**，并自动同步当前机器人的 QQ 号与昵称！

---

### 🔊 GPT-SoVITS 语音合成集成

系统支持一键自动打补丁与服务接管：

1. 启动项目并进入 WebUI 控制台的【TTS 语音设置】页面；
2. 输入您本地的 GPT-SoVITS 根目录路径（例如 `D:\GPT-SoVITS\GPT-SoVITS-v2pro`）；
3. 点击【安装补丁】按钮，系统将自动注入定制跨域与崩溃防护的 `api_v2.py`，并自动生成专属于您本地路径的 `start_tts.bat`；
4. 点击【一键启动 TTS】即可无缝拉起语音合成引擎！

---

### 📁 目录结构说明

```text
.
├── config/                     # 配置文件目录 (config.json 已受 .gitignore 保护)
├── data/                       # 运行时持久化数据目录 (ChromaDB、参考音频、UI配置)
├── docs/                       # 开发文档与插件微内核指南
├── models/                     # 离线模型资源 (BGE-small-zh-v1.5)
├── patches/                    # GPT-SoVITS 增强补丁与参考音频
├── plugins/                    # 微内核插件扩展目录
├── prompts/                    # Tidebound 规范模块化提示词包
├── scripts/                    # 运维与记忆固化脚本
├── src/                        # 核心后端源码
├── tests/                      # 单元测试与集成测试脚本集
├── web/                        # 前端玻璃拟态单页 WebUI
├── install.bat                 # Windows 一键环境安装向导
├── start.bat                   # 机器人与 WebUI 启动脚本
├── start_all.bat               # 全服务一键启动器 (TTS + Bot)
├── start_tts.bat               # GPT-SoVITS 语音服务启动器
├── LICENSE                     # GNU 通用公共许可证 v3.0 (GPL-3.0)
└── README.md                   # 中英双语项目自述文档
```

---

## 📄 开源许可证与免责声明 (License & Disclaimer)

- **许可证 (License)**: 本项目采用 **[GNU General Public License v3.0 (GPL-3.0)](LICENSE)** 开源许可证。
- **免责声明 (Disclaimer)**: 本项目仅用于技术交流与个人学习用途。角色《风又音理》的人设、台词与声线版权归原制作公司（Tinkle Position）所有。请勿用于商业盈利用途。
