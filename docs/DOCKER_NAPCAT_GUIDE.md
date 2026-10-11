# Windows 平台下 NapCat (Docker Desktop) 对接与网络互联实战指南

> 本指南专为在 Windows 平台通过 **Docker Desktop** 运行 NapCatQQ，并与宿主机运行的 AI 伴侣机器人（风又音理 NeriBot / 诺瓦 NoirBot）进行 OneBot v11 协议通信的用户编写。

---

## 目录
1. [网络拓扑与关键原理](#1-网络拓扑与关键原理)
2. [使用 Docker Desktop 快速拉起 NapCat](#2-使用-docker-desktop-快速拉起-napcat)
3. [方案一：反向 WebSocket 模式对接（官方强烈推荐）](#3-方案一反向-websocket-模式对接官方强烈推荐)
4. [方案二：正向 WebSocket 模式对接](#4-方案二正向-websocket-模式对接)
5. [多角色双开部署（音理 + 诺瓦 同时运行）](#5-多角色双开部署音理--诺瓦-同时运行)
6. [Windows 常见避坑与故障排查清单](#6-windows-常见避坑与故障排查清单)

---

## 1. 网络拓扑与关键原理

在 Windows + Docker Desktop 架构下，网络边界如下：

```
┌────────────────────────────────────────────────────────┐
│                   Windows 宿主机操作系统                 │
│                                                        │
│  ┌─────────────────────────┐                           │
│  │  Bot 进程 (Python)      │                           │
│  │  WebUI & WebSocket 服务 │                           │
│  │  监听端口: 8088 / 8089  │                           │
│  └───────────▲─────────────┘                           │
│              │                                         │
│              │ (反向WS: host.docker.internal:8088)     │
│              │ (正向WS: 127.0.0.1:3001)                │
│              ▼                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │        Docker Desktop (WSL2 / Linux 虚拟机)       │  │
│  │                                                  │  │
│  │  ┌────────────────────────────────────────────┐  │  │
│  │  │ NapCatQQ 容器 (mlikiowa/napcat-docker)     │  │  │
│  │  │ WebUI 管理: 6099 端口                      │  │  │
│  │  │ 正向 WS 服务: 3001 端口 (可选)              │  │  │
│  │  └────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

> [!CAUTION]
> ### ⚠️ Windows Docker 最核心避坑点
> * **在 Docker 容器内部，`127.0.0.1` 指向容器自己**，绝不能用来访问宿主机！
> * 当 NapCat（容器）需要反向连接宿主机上的 Bot 时，**地址必须填写 `ws://host.docker.internal:8088/onebot/v11/ws`**，而不是 `127.0.0.1`。
> * 当 Bot（宿主机）主动正向连接 NapCat 时，由于 Docker 将端口映射到了宿主机，Bot 直接访问 `ws://127.0.0.1:3001` 即可。

---

## 2. 使用 Docker Desktop 快速拉起 NapCat

### 2.1 准备挂载目录
在 Windows 上创建用于保存 NapCat 配置和 QQ 登录凭据的本地文件夹（例如在 `D:\napcat`）：
```powershell
New-Item -ItemType Directory -Force -Path "D:\napcat\config", "D:\napcat\qq"
```

### 2.2 启动容器（命令行方式）
打开 PowerShell 执行：
```powershell
docker run -d `
  --name napcat `
  --restart always `
  -p 6099:6099 `
  -p 3001:3001 `
  -e ACCOUNT=你的机器人QQ号 `
  -e HTTP_ENABLE=true `
  -e HTTP_PORT=3000 `
  -e WS_ENABLE=true `
  -e WS_PORT=3001 `
  -v D:/napcat/config:/app/napcat/config `
  -v D:/napcat/qq:/root/.config/QQ `
  mlikiowa/napcat-docker:latest
```

### 2.3 或者使用 Docker Compose（推荐）
在本地创建 `docker-compose.yml`：
```yaml
version: '3.8'

services:
  napcat:
    image: mlikiowa/napcat-docker:latest
    container_name: napcat
    restart: always
    environment:
      - ACCOUNT=你的机器人QQ号
      - WS_ENABLE=true
      - WS_PORT=3001
      - NAPCAT_GID=0
      - NAPCAT_UID=0
    ports:
      - "6099:6099"   # NapCat WebUI 配置页面
      - "3001:3001"   # 正向 WebSocket 端口
    volumes:
      - D:/napcat/config:/app/napcat/config
      - D:/napcat/qq:/root/.config/QQ
```
执行启动：
```powershell
docker-compose up -d
```

### 2.4 完成 QQ 登录
1. 浏览器打开 NapCat WebUI 管理控制台：`http://127.0.0.1:6099/webui`；
2. 首次登录根据界面提示扫码或通过日志终端扫码完成 QQ 账号登录。

---

## 3. 方案一：反向 WebSocket 模式对接（官方强烈推荐）

反向 WebSocket 模式下，NapCat 容器主动与宿主机的 Bot 维持长连接，稳定性最高，无需繁琐的端口暴露。

### 第一步：在 NapCat WebUI 中添加反向连接
1. 打开 NapCat WebUI：`http://127.0.0.1:6099/webui`；
2. 依次点击侧边栏 **【网络配置】** -> **【添加配置】**；
3. 选择配置类型为 **【反向 WebSocket (ws_reverse)】**；
4. 填写以下关键参数：
   - **名称**：`NeriBot反向WS`（任意命名）
   - **连接地址 (URL)**：
     - 若对接 **风又音理 (NeriBot)**：
       ```text
       ws://host.docker.internal:8088/onebot/v11/ws
       ```
     - 若对接 **诺瓦 (NoirBot)**：
       ```text
       ws://host.docker.internal:8089/onebot/v11/ws
       ```
   - **重连间隔**：`5000` 毫秒
   - **Token (密钥)**：若 Bot 未设置密码则留空；若在 Bot 的 OneBot 页面设置了 Token，此处必须严格保持一致。
5. 点击 **【保存配置】**。

### 第二步：在 Bot Web 控制台中确认配置
1. 打开 Bot Web 控制台（音理：`http://127.0.0.1:8088` / 诺瓦：`http://127.0.0.1:8089`）；
2. 进入 **【系统设置】** 页，找到 **【OneBot11 网络连接与协议模式】**：
   - **WebSocket 连接模式**：选择 `🌟 双向同时启用` 或 `反向服务端 (reverse_ws)`
   - **服务监听端口**：`8088`（音理）或 `8089`（诺瓦）
   - **反向监听路径**：`/onebot/v11/ws`
   - **OneBot 连接密钥 (Token)**：留空（或与 NapCat 一致）
3. 点击 **【保存 OneBot 连接设定】**。
4. 此时刷新页面，配置会自动回显；顶部状态栏将立即变为 **🟢 已连接 (在线)**，并显示当前登录的 QQ 号与昵称！

---

## 4. 方案二：正向 WebSocket 模式对接

正向 WebSocket 模式下，Bot 主动作为客户端连接 NapCat 容器暴露的端口。

### 第一步：在 NapCat 容器中开启正向 WebSocket
1. 确认 Docker 启动命令包含 `-p 3001:3001` 端口映射；
2. 在 NapCat WebUI 的 **【网络配置】** 中确认已启用 **【正向 WebSocket (ws)】**：
   - 监听 Host：`0.0.0.0`
   - 监听端口：`3001`
   - Token：留空（或按需设置）

### 第二步：在 Bot 控制台中配置
1. 打开 Bot 控制台；
2. 进入 **【系统设置】** -> **【OneBot11 网络连接与协议模式】**：
   - **WebSocket 连接模式**：选择 `正向客户端 (forward_ws)` 或 `🌟 双向同时启用`
   - **正向 WebSocket 目标地址**：
     ```text
     ws://127.0.0.1:3001
     ```
   - **Token**：与 NapCat 保持一致；
3. 点击 **【保存 OneBot 连接设定】**，系统将自动发起实时重连并生效！

---

## 5. 多角色双开部署（音理 + 诺瓦 同时运行）

如果您希望在同一台电脑上同时运行 **风又音理 (Neri)** 和 **诺瓦 (Noir)** 两个不同性格的角色机器人，网络规划如下：

| 配置项 | 风又音理 (NeriBot) | 诺瓦 (NoirBot) |
| :--- | :--- | :--- |
| **项目工作目录** | `D:\gal\Bot` | `D:\gal\NoirBot` |
| **Web 控制台地址** | `http://127.0.0.1:8088` | `http://127.0.0.1:8089` |
| **反向 WS 接收端口** | `8088` | `8089` |
| **NapCat 填写的反向 URL** | `ws://host.docker.internal:8088/onebot/v11/ws` | `ws://host.docker.internal:8089/onebot/v11/ws` |
| **NapCat 容器实例** | 容器 A（如 `napcat-neri`，绑定音理QQ） | 容器 B（如 `napcat-noir`，绑定诺瓦QQ） |
| **NapCat WebUI 端口** | `6099` | `6100` |

> [!TIP]
> 也可以同一个 NapCat 容器同时添加两条反向 WebSocket 配置，一条指向 `8088`，另一条指向 `8089`，这样两个机器人会同时响应同一个 QQ 账号收到的群聊消息。

---

## 6. Windows 常见避坑与故障排查清单

### ❓ 问题 1：NapCat 日志报错 `connect ECONNREFUSED 127.0.0.1:8088`
* **原因**：在 NapCat 容器内填写了 `ws://127.0.0.1:8088/...`，容器尝试连接容器内部自身而不是 Windows 宿主机。
* **解决**：务必将 `127.0.0.1` 替换为 **`host.docker.internal`**！完整地址为 `ws://host.docker.internal:8088/onebot/v11/ws`。

### ❓ 问题 2：NapCat 显示连接超时或一直重试，没有握手成功
* **原因**：Windows Defender 防火墙拦截了来自 Docker 内部虚拟网卡的入站流量。
* **排查方法**：
  在宿主机终端进入 NapCat 容器执行网络测试：
  ```powershell
  docker exec -it napcat curl -I http://host.docker.internal:8088/api/status
  ```
  如果返回 `HTTP/1.1 200 OK` 或 `401 Unauthorized`，说明网络通畅；如果卡死超时，说明被 Windows 防火墙拦截。
* **解决方法**：
  1. 按 `Win + R` 输入 `wf.msc` 打开高级安全 Windows Defender 防火墙；
  2. 点击左侧 **【入站规则】** -> 右侧 **【新建规则】**；
  3. 规则类型选 **【端口】** -> 特定本地端口填 **`8088, 8089`**；
  4. 操作选 **【允许连接】**，配置文件全选（域、专用、公用）；
  5. 命名为 `Bot OneBot WebSocket` 并保存。

### ❓ 问题 3：Bot 控制台终端提示 `[OneBot11] 反向 WS 鉴权失败: 提供的 Token 不匹配，拒绝连接！`
* **原因**：NapCat 与 Bot 的 Token 设置不一致。
* **解决**：在 Bot 的【系统设置】页与 NapCat 的【网络配置】中，要么两边都留空，要么输入一模一样的 Token 字符串。

### ❓ 问题 4：保存了监听端口但刷新页面后没有变化？
* **已在新版中彻底修复**：本系统前端已全面升级配置动态回显与状态校验机制。修改端口后，请记得在终端重启 Bot 进程，以使底层操作系统 socket 重新绑定新的端口！
