/**
 * Kazamata Neri (音理) 全息高定 WebUI 核心引擎 v4.5
 * 双轨固化系统 (服务端存储 + IndexedDB 永久本地存储) + 批量多选上传 + 全功能播放器
 */

// ========================================================
// 1. IndexedDB 永久本地存储引擎 (解决未重启服务器时文件刷新丢失问题)
// ========================================================
const NeriDB = {
  db: null,
  async open() {
    if (this.db) return this.db;
    return new Promise((resolve, reject) => {
      const req = indexedDB.open("NeriThemeDB", 1);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains("assets")) {
          db.createObjectStore("assets", { keyPath: "id" });
        }
      };
      req.onsuccess = (e) => {
        this.db = e.target.result;
        resolve(this.db);
      };
      req.onerror = (e) => reject(e);
    });
  },
  async set(id, file) {
    try {
      const db = await this.open();
      return new Promise((resolve, reject) => {
        const tx = db.transaction("assets", "readwrite");
        tx.objectStore("assets").put({ id, file, name: file.name, type: file.type });
        tx.oncomplete = () => resolve();
        tx.onerror = (e) => reject(e);
      });
    } catch (e) {
      console.warn("IndexedDB save error", e);
    }
  },
  async get(id) {
    try {
      const db = await this.open();
      return new Promise((resolve) => {
        const tx = db.transaction("assets", "readonly");
        const req = tx.objectStore("assets").get(id);
        req.onsuccess = () => resolve(req.result ? req.result.file : null);
        req.onerror = () => resolve(null);
      });
    } catch (e) {
      return null;
    }
  },
  async delete(id) {
    try {
      const db = await this.open();
      return new Promise((resolve) => {
        const tx = db.transaction("assets", "readwrite");
        tx.objectStore("assets").delete(id);
        tx.oncomplete = () => resolve();
        tx.onerror = () => resolve();
      });
    } catch (e) {}
  },
  async setConfig(config) {
    try {
      const db = await this.open();
      return new Promise((resolve, reject) => {
        const tx = db.transaction("assets", "readwrite");
        tx.objectStore("assets").put({ id: "__neri_ui_config__", data: JSON.parse(JSON.stringify(config)) });
        tx.oncomplete = () => resolve();
        tx.onerror = (e) => reject(e);
      });
    } catch (e) {
      console.warn("IndexedDB setConfig error", e);
    }
  },
  async getConfig() {
    try {
      const db = await this.open();
      return new Promise((resolve) => {
        const tx = db.transaction("assets", "readonly");
        const req = tx.objectStore("assets").get("__neri_ui_config__");
        req.onsuccess = () => resolve(req.result ? req.result.data : null);
        req.onerror = () => resolve(null);
      });
    } catch (e) {
      return null;
    }
  }
};

// ========================================================
// 2. 高定二次元模态窗与 Toast 系统
// ========================================================
const NeriModal = {
  container: null,
  toastContainer: null,

  init() {
    if (!document.getElementById("neri-modal-backdrop")) {
      const modalHtml = `
        <div id="neri-modal-backdrop">
          <div id="neri-modal-box">
            <h3 id="neri-modal-title"></h3>
            <div id="neri-modal-body"></div>
            <div id="neri-modal-input-wrap" class="mb-4 hidden">
              <input type="text" id="neri-modal-input" class="w-full p-2.5 rounded-lg border text-sm outline-none focus:border-cyan-400 bg-slate-900/80 border-slate-700 text-slate-100">
            </div>
            <div class="flex justify-end gap-2.5" id="neri-modal-actions"></div>
          </div>
        </div>
        <div id="neri-toast-container"></div>
      `;
      document.body.insertAdjacentHTML("beforeend", modalHtml);
    }
    this.container = document.getElementById("neri-modal-backdrop");
    this.toastContainer = document.getElementById("neri-toast-container");
  },

  toast(msg, duration = 2200) {
    this.init();
    const item = document.createElement("div");
    item.className = "neri-toast-item";
    const isErr = /失败|错误|异常|Error/i.test(msg);
    const icon = isErr ? "fa-circle-exclamation text-rose-400" : "fa-sparkles text-cyan-400";
    item.innerHTML = `<i class="fa-solid ${icon}"></i><span>${msg}</span>`;
    this.toastContainer.appendChild(item);
    setTimeout(() => {
      item.style.opacity = "0";
      item.style.transform = "translateY(-10px)";
      item.style.transition = "all 0.3s ease";
      setTimeout(() => item.remove(), 300);
    }, duration);
  },

  alert(msg, title = "提示") {
    this.init();
    return new Promise((resolve) => {
      const isErr = /失败|错误|异常|Error|缺失|未填/i.test(msg + title);
      const isSuccess = /成功|完成|已更新|已生效|已保存|已写入|已重置/i.test(msg + title);
      const icon = isErr ? "fa-solid fa-circle-exclamation text-rose-400" : (isSuccess ? "fa-solid fa-circle-check text-emerald-400" : "fa-solid fa-circle-info text-cyan-400");

      document.getElementById("neri-modal-title").innerHTML = `<i class="${icon}"></i><span>${title}</span>`;
      document.getElementById("neri-modal-body").textContent = msg;
      document.getElementById("neri-modal-input-wrap").classList.add("hidden");
      
      const actions = document.getElementById("neri-modal-actions");
      actions.innerHTML = `
        <button id="neri-btn-modal-ok" class="btn-primary px-5 py-2 text-xs font-bold shadow-md cursor-pointer transition">我知道了</button>
      `;
      this.container.classList.add("show");

      const closeAlert = () => {
        this.container.classList.remove("show");
        document.removeEventListener("keydown", onKeyDown);
        this.container.onclick = null;
        resolve();
      };

      const onKeyDown = (e) => {
        if (e.key === "Enter" || e.key === "Escape") {
          e.preventDefault();
          closeAlert();
        }
      };

      const okBtn = document.getElementById("neri-btn-modal-ok");
      if (okBtn) okBtn.onclick = closeAlert;
      document.addEventListener("keydown", onKeyDown);
      this.container.onclick = (e) => {
        if (e.target === this.container) closeAlert();
      };
    });
  },

  confirm(msg, title = "确认操作", isDanger = false) {
    this.init();
    return new Promise((resolve) => {
      const isWarn = isDanger || /高危|删除|清空|擦除|重置|恢复出厂|不可逆|不可撤销/i.test(msg + title);
      const iconClass = isWarn ? "fa-solid fa-triangle-exclamation text-rose-400" : "fa-solid fa-circle-question text-cyan-400";
      document.getElementById("neri-modal-title").innerHTML = `<i class="${iconClass}"></i><span>${title}</span>`;
      document.getElementById("neri-modal-body").textContent = msg;
      document.getElementById("neri-modal-input-wrap").classList.add("hidden");

      const confirmBtnClass = isWarn 
        ? "px-5 py-2 text-xs font-bold text-white bg-rose-600 hover:bg-rose-500 rounded-lg shadow-md cursor-pointer transition border border-rose-500/40"
        : "btn-primary px-5 py-2 text-xs font-bold shadow-md cursor-pointer transition";

      const actions = document.getElementById("neri-modal-actions");
      actions.innerHTML = `
        <button id="neri-btn-modal-cancel" class="btn-secondary px-4 py-2 rounded-lg text-xs font-medium cursor-pointer transition">取消</button>
        <button id="neri-btn-modal-confirm" class="${confirmBtnClass}">确定</button>
      `;
      this.container.classList.add("show");

      const finish = (result) => {
        this.container.classList.remove("show");
        document.removeEventListener("keydown", onKeyDown);
        this.container.onclick = null;
        resolve(result);
      };

      const onKeyDown = (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          finish(false);
        } else if (e.key === "Enter") {
          e.preventDefault();
          finish(true);
        }
      };

      const cancelBtn = document.getElementById("neri-btn-modal-cancel");
      const confirmBtn = document.getElementById("neri-btn-modal-confirm");
      if (cancelBtn) cancelBtn.onclick = () => finish(false);
      if (confirmBtn) confirmBtn.onclick = () => finish(true);
      document.addEventListener("keydown", onKeyDown);
      this.container.onclick = (e) => {
        if (e.target === this.container) finish(false);
      };
    });
  },

  prompt(msg, defaultVal = "", title = "输入内容") {
    this.init();
    return new Promise((resolve) => {
      document.getElementById("neri-modal-title").innerHTML = `<i class="fa-solid fa-pen-to-square text-cyan-400"></i><span>${title}</span>`;
      document.getElementById("neri-modal-body").textContent = msg;
      
      const inputWrap = document.getElementById("neri-modal-input-wrap");
      const input = document.getElementById("neri-modal-input");
      inputWrap.classList.remove("hidden");
      input.value = defaultVal || "";

      const actions = document.getElementById("neri-modal-actions");
      actions.innerHTML = `
        <button id="neri-btn-modal-prompt-cancel" class="btn-secondary px-4 py-2 rounded-lg text-xs font-medium cursor-pointer transition">取消</button>
        <button id="neri-btn-modal-prompt-ok" class="btn-primary px-5 py-2 text-xs font-bold shadow-md cursor-pointer transition">确定</button>
      `;
      this.container.classList.add("show");
      setTimeout(() => input.focus(), 50);

      const finishPrompt = (val) => {
        this.container.classList.remove("show");
        document.removeEventListener("keydown", onKeyDown);
        this.container.onclick = null;
        resolve(val);
      };

      const onKeyDown = (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          finishPrompt(input.value.trim() || null);
        } else if (e.key === "Escape") {
          e.preventDefault();
          finishPrompt(null);
        }
      };

      const promptCancelBtn = document.getElementById("neri-btn-modal-prompt-cancel");
      const promptOkBtn = document.getElementById("neri-btn-modal-prompt-ok");
      if (promptCancelBtn) promptCancelBtn.onclick = () => finishPrompt(null);
      if (promptOkBtn) promptOkBtn.onclick = () => finishPrompt(input.value.trim() || null);
      document.addEventListener("keydown", onKeyDown);
      this.container.onclick = (e) => {
        if (e.target === this.container) finishPrompt(null);
      };
    });
  }
};

// 挂载全局别名供全系统使用
window.NeriModal = NeriModal;
window.showConfirmDialog = (msg, title, isDanger) => NeriModal.confirm(msg, title, isDanger);
window.showAlertDialog = (msg, title) => NeriModal.alert(msg, title);
window.showToast = (msg, duration) => NeriModal.toast(msg, duration);
// 默认原生 alert 拦截器
window.alert = (msg, title) => NeriModal.alert(msg, title || "提示");

// ========================================================
// 3. 音理 WebUI 视觉核心引擎 v4.5
// ========================================================
const NeriTheme = {
  config: {
    themeMode: "dark",
    panelBlur: 16,
    panelOpacity: 0.58,
    tabAnimDuration: 0.45,
    playMode: "loop",
    currentWallpaperId: "",
    wallpapers: [],
    currentSongId: "",
    playlist: [],
    mouseFx: {
      enabled: true,
      trailStyle: "sakura",
      clickStyle: "bloom",
      decayRate: 0.012,
      particleSize: 5
    },
    topMarquee: { 
      enabled: true, 
      text: "✨ 欢迎来到音理的控制中心 ✨ Kazamata Neri System Online", 
      delimiter: "---",
      spacing: 16,
      size: 14, 
      opacity: 0.9,
      maskOpacity: 0.6 
    },
    bottomMarquee: { 
      enabled: true, 
      text: "正在运行 Neri 专属核心系统 | OneBot11 链路状态正常", 
      delimiter: "---",
      spacing: 12,
      size: 12, 
      opacity: 0.75,
      maskOpacity: 0.5 
    }
  },

  audioObj: null,
  isPlaying: false,
  fxCanvas: null,
  fxCtx: null,
  particles: [],
  bursts: [],

  // 获取当前生效主题（若为 system 则探测操作系统首选项）
  getEffectiveTheme() {
    if (this.config.themeMode === "system") {
      const isDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      return isDark ? "dark" : "light";
    }
    return this.config.themeMode === "light" ? "light" : "dark";
  },

  async init() {
    await this.loadConfig();
    this.injectMarquees();
    this.injectMusicPlayer();
    this.injectSettingsTab();
    this.initMouseFx();
    this.applyTheme();

    // 监听操作系统亮暗主题切换 (跟随系统模式)
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if (this.config.themeMode === "system") {
          this.applyTheme();
          this.renderWallpaperList();
          this.renderPlaylist();
        }
      });
    }
    // 监听窗口尺寸变化，动态维护顶端高度
    window.addEventListener("resize", () => {
      const headerEl = document.querySelector("header");
      if (headerEl) {
        document.documentElement.style.setProperty("--header-height", `${headerEl.offsetHeight || 54}px`);
      }
    });
    console.log("[NeriTheme] Kazamata Neri UI Engine v4.6 Initialized with Multi-tier Solidification.");
  },

  async loadConfig() {
    // 1. 优先尝试从 LocalStorage 快速读取
    let saved = null;
    try {
      const str = localStorage.getItem("neri_ui_config_persistent");
      if (str) saved = JSON.parse(str);
    } catch (e) {}

    // 2. 若 LocalStorage 为空，从 IndexedDB 读取兜底
    if (!saved) {
      try {
        saved = await NeriDB.getConfig();
      } catch (e) {}
    }

    // 3. 异步尝试从服务端接口获取 (如果服务端存在)
    if (!saved) {
      try {
        const res = await fetch("/api/ui/config");
        if (res.ok) {
          saved = await res.json();
        }
      } catch (e) {}
    }

    if (saved && typeof saved === "object") {
      this.config = {
        ...this.config,
        ...saved,
        mouseFx: { ...this.config.mouseFx, ...(saved.mouseFx || {}) },
        topMarquee: { ...this.config.topMarquee, ...(saved.topMarquee || {}) },
        bottomMarquee: { ...this.config.bottomMarquee, ...(saved.bottomMarquee || {}) },
        wallpapers: Array.isArray(saved.wallpapers) ? saved.wallpapers : this.config.wallpapers,
        playlist: Array.isArray(saved.playlist) ? saved.playlist : this.config.playlist
      };

      // 版本平滑升级：历史版本默认为 light，新版强制初始化暗色并打标
      if (!saved._v46DefaultDark) {
        this.config.themeMode = (saved.themeMode && saved.themeMode !== "light") ? saved.themeMode : "dark";
        this.config._v46DefaultDark = true;
      }
      if (!saved._v47OpacityRefreshed) {
        if (this.config.panelOpacity > 0.65) {
          this.config.panelOpacity = 0.58;
        }
        this.config._v47OpacityRefreshed = true;
      }
    } else {
      this.config._v46DefaultDark = true;
      this.config._v47OpacityRefreshed = true;
    }

    // 4. 从 IndexedDB 还原离线固化的壁纸与音乐 Blob URL
    for (const wp of this.config.wallpapers) {
      if (wp.idbId) {
        const file = await NeriDB.get(wp.idbId);
        if (file) {
          wp.url = URL.createObjectURL(file);
        }
      }
    }

    for (const song of this.config.playlist) {
      if (song.idbId) {
        const file = await NeriDB.get(song.idbId);
        if (file) {
          song.url = URL.createObjectURL(file);
        }
      }
    }
  },

  async saveConfig() {
    const cleanConfig = { ...this.config };

    // 1. 同步保存至 LocalStorage
    try {
      localStorage.setItem("neri_ui_config_persistent", JSON.stringify(cleanConfig));
    } catch (e) {
      console.warn("LocalStorage save warning", e);
    }

    // 2. 永久固化保存至 IndexedDB 本地数据库
    try {
      await NeriDB.setConfig(cleanConfig);
    } catch (e) {}

    // 3. 异步同步到服务端硬盘
    try {
      await fetch("/api/ui/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanConfig)
      });
    } catch (e) {}

    this.applyTheme();
  },

  formatMarqueeContent(cfg) {
    if (!cfg || !cfg.text) return "";
    const rawText = String(cfg.text).trim();
    if (!rawText) return "";

    const delim = cfg.delimiter !== undefined ? String(cfg.delimiter) : "---";
    const spacing = cfg.spacing !== undefined ? parseInt(cfg.spacing) : 16;
    const len = rawText.length;

    // 短句子（例如 "AAA"）复制多次轮流滚动：---AAA---AAA---AAA---
    // 长句子则自动适度减少重复次数避免字体重叠
    let repeats = 1;
    if (len <= 8) {
      repeats = 8;
    } else if (len <= 16) {
      repeats = 5;
    } else if (len <= 35) {
      repeats = 3;
    } else if (len <= 65) {
      repeats = 2;
    } else {
      repeats = 1;
    }

    const safeText = rawText
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const safeDelim = delim
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    let segments = [];
    for (let i = 0; i < repeats; i++) {
      segments.push(`<span class="marquee-segment" style="margin: 0 ${spacing}px;"><span class="marquee-delim opacity-60">${safeDelim}</span><span class="marquee-txt">${safeText}</span></span>`);
    }
    if (safeDelim) {
      segments.push(`<span class="marquee-delim opacity-60" style="margin: 0 ${spacing}px;">${safeDelim}</span>`);
    }
    return segments.join("");
  },

  applyTheme() {
    const root = document.documentElement;
    const body = document.body;

    body.classList.remove("theme-dark", "theme-light", "dark");
    root.classList.remove("dark");

    const effective = this.getEffectiveTheme();
    if (effective === "dark") {
      body.classList.add("dark", "theme-dark");
      root.classList.add("dark");
    } else {
      body.classList.add("theme-light");
    }

    // 模糊度归零完全关停 GPU 滤镜，杜绝壁纸重影与网格畸变
    const blur = parseInt(this.config.panelBlur) || 0;
    root.style.setProperty("--panel-blur", `${blur}px`);
    if (blur <= 0) {
      root.style.setProperty("--panel-blur-css", "none");
    } else {
      root.style.setProperty("--panel-blur-css", `blur(${blur}px)`);
    }

    // 面板透明度 (支持 0% 完全透视)
    const op = this.config.panelOpacity !== undefined ? parseFloat(this.config.panelOpacity) : 0.78;
    root.style.setProperty("--panel-opacity", `${op}`);

    // 动画时长
    root.style.setProperty("--tab-anim-duration", `${this.config.tabAnimDuration || 0.45}s`);

    // 背景壁纸
    const currentWp = this.config.wallpapers.find(w => w.id === this.config.currentWallpaperId);
    if (currentWp && currentWp.url) {
      body.style.backgroundImage = `url('${currentWp.url}')`;
    } else {
      body.style.backgroundImage = 'none';
    }

    const isLight = effective === "light";

    // 顶端状态栏高度感知与下属滚动横幅联动
    const headerEl = document.querySelector("header");
    if (headerEl) {
      const headerH = headerEl.offsetHeight || 54;
      root.style.setProperty("--header-height", `${headerH}px`);
    }

    // 顶部字幕 (位于顶端状态栏下方)
    const topCfg = this.config.topMarquee;
    const mt = document.getElementById("marquee-top");
    if (mt) {
      if (topCfg && topCfg.enabled) {
        const h = Math.round((topCfg.size || 14) * 2.2);
        root.style.setProperty("--marquee-top-height", `${h}px`);
        root.style.setProperty("--marquee-top-size", `${topCfg.size || 14}px`);
        mt.style.display = "flex";

        // 确保 marquee-top 位于 header 下方
        if (headerEl && mt.previousElementSibling !== headerEl && headerEl.parentNode) {
          headerEl.parentNode.insertBefore(mt, headerEl.nextSibling);
        }

        const maskA = topCfg.maskOpacity !== undefined ? parseFloat(topCfg.maskOpacity) : 0.6;
        if (maskA <= 0.01) {
          mt.style.backgroundColor = "transparent";
          mt.style.backdropFilter = "none";
          mt.style.webkitBackdropFilter = "none";
        } else {
          const bg = isLight ? `rgba(255, 255, 255, ${maskA})` : `rgba(20, 16, 24, ${maskA})`;
          mt.style.backgroundColor = bg;
          mt.style.backdropFilter = `blur(${Math.min(blur, 12)}px)`;
          mt.style.webkitBackdropFilter = `blur(${Math.min(blur, 12)}px)`;
        }

        const textColor = isLight ? "#9C6B9E" : "#E2BAEE";
        const topHtml = this.formatMarqueeContent(topCfg);
        mt.innerHTML = `<div class="marquee-text" style="font-size: ${topCfg.size || 14}px; opacity: ${topCfg.opacity || 0.9}; color: ${textColor}">${topHtml}</div>`;
        const topEl = mt.querySelector(".marquee-text");
        if (topEl) {
          const charLen = (topCfg.text || "").length;
          const dur = Math.max(16, Math.min(65, Math.round(charLen * 0.45 + 12)));
          topEl.style.animationDuration = `${dur}s`;
        }
      } else {
        mt.style.display = "none";
        root.style.setProperty("--marquee-top-height", "0px");
      }
    }

    // 底部字幕
    const botCfg = this.config.bottomMarquee;
    const mb = document.getElementById("marquee-bottom");
    if (mb) {
      if (botCfg && botCfg.enabled) {
        const h = Math.round((botCfg.size || 12) * 2.2);
        root.style.setProperty("--marquee-bot-height", `${h}px`);
        root.style.setProperty("--marquee-bot-size", `${botCfg.size || 12}px`);
        mb.style.display = "flex";

        const maskA = botCfg.maskOpacity !== undefined ? parseFloat(botCfg.maskOpacity) : 0.5;
        if (maskA <= 0.01) {
          mb.style.backgroundColor = "transparent";
          mb.style.backdropFilter = "none";
          mb.style.webkitBackdropFilter = "none";
        } else {
          const bg = isLight ? `rgba(255, 255, 255, ${maskA})` : `rgba(20, 16, 24, ${maskA})`;
          mb.style.backgroundColor = bg;
          mb.style.backdropFilter = `blur(${Math.min(blur, 12)}px)`;
          mb.style.webkitBackdropFilter = `blur(${Math.min(blur, 12)}px)`;
        }

        const textColor = isLight ? "#7A5980" : "#D4C9DA";
        const botHtml = this.formatMarqueeContent(botCfg);
        mb.innerHTML = `<div class="marquee-text" style="font-size: ${botCfg.size || 12}px; opacity: ${botCfg.opacity || 0.75}; color: ${textColor}">${botHtml}</div>`;
        const botEl = mb.querySelector(".marquee-text");
        if (botEl) {
          const charLen = (botCfg.text || "").length;
          const dur = Math.max(16, Math.min(65, Math.round(charLen * 0.45 + 12)));
          botEl.style.animationDuration = `${dur}s`;
        }
      } else {
        mb.style.display = "none";
        root.style.setProperty("--marquee-bot-height", "0px");
      }
    }

    this.updatePlayerDisplay();
  },

  getCurrentTrack() {
    if (!this.config.playlist || this.config.playlist.length === 0) return null;
    return this.config.playlist.find(s => s.id === this.config.currentSongId) || this.config.playlist[0] || null;
  },

  getCurrentTrackIndex() {
    if (!this.config.playlist || this.config.playlist.length === 0) return -1;
    return this.config.playlist.findIndex(s => s.id === this.config.currentSongId);
  },

  togglePlayMode() {
    const modes = ["loop", "single", "random", "order"];
    const modeNames = {
      loop: "🔁 列表循环",
      single: "🔂 单曲循环",
      random: "🔀 随机播放",
      order: "⏭️ 顺序播放"
    };
    const curIndex = modes.indexOf(this.config.playMode || "loop");
    const nextMode = modes[(curIndex + 1) % modes.length];
    this.config.playMode = nextMode;
    this.saveConfig();
    this.updatePlayerDisplay();
    NeriModal.toast(`播放模式已切换为: ${modeNames[nextMode]}`);
  },

  prevTrack() {
    if (!this.config.playlist || this.config.playlist.length === 0) {
      NeriModal.toast("当前歌单为空");
      return;
    }
    const len = this.config.playlist.length;
    let idx = this.getCurrentTrackIndex();
    if (idx === -1) idx = 0;
    
    if (this.config.playMode === "random" && len > 1) {
      let rIdx = Math.floor(Math.random() * len);
      if (rIdx === idx) rIdx = (rIdx + 1) % len;
      idx = rIdx;
    } else {
      idx = (idx - 1 + len) % len;
    }

    this.config.currentSongId = this.config.playlist[idx].id;
    this.saveConfig();
    this.renderPlaylist();
    this.updatePlayerDisplay();
    this.playCurrent();
  },

  nextTrack(auto = false) {
    if (!this.config.playlist || this.config.playlist.length === 0) {
      if (!auto) NeriModal.toast("当前歌单为空");
      return;
    }
    const len = this.config.playlist.length;
    let idx = this.getCurrentTrackIndex();
    if (idx === -1) idx = 0;

    if (auto && this.config.playMode === "single") {
      if (this.audioObj) {
        this.audioObj.currentTime = 0;
        this.audioObj.play();
      }
      return;
    }

    if (this.config.playMode === "random" && len > 1) {
      let rIdx = Math.floor(Math.random() * len);
      if (rIdx === idx) rIdx = (rIdx + 1) % len;
      idx = rIdx;
    } else if (this.config.playMode === "order") {
      if (idx >= len - 1 && auto) {
        if (this.audioObj) this.audioObj.pause();
        this.isPlaying = false;
        this.updatePlayerDisplay();
        return;
      }
      idx = (idx + 1) % len;
    } else {
      idx = (idx + 1) % len;
    }

    this.config.currentSongId = this.config.playlist[idx].id;
    this.saveConfig();
    this.renderPlaylist();
    this.updatePlayerDisplay();
    this.playCurrent();
  },

  playCurrent() {
    const track = this.getCurrentTrack();
    if (!track || !track.url) {
      NeriModal.toast("当前无有效音频");
      return;
    }
    if (this.audioObj) {
      this.audioObj.src = track.url;
      this.audioObj.play().then(() => {
        this.isPlaying = true;
        const pBtn = document.getElementById("btn-play-pause");
        const cd = document.getElementById("player-cd");
        if (pBtn) pBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        if (cd) cd.classList.add("playing");
      }).catch(err => {
        console.warn("Play error", err);
      });
    }
  },

  updatePlayerDisplay() {
    const track = this.getCurrentTrack();
    const titleEl = document.getElementById("player-song-title");
    const subEl = document.getElementById("player-song-sub");
    const modeBtn = document.getElementById("btn-player-mode");

    const modeLabels = {
      loop: "列表循环",
      single: "单曲循环",
      random: "随机播放",
      order: "顺序播放"
    };

    const modeIcons = {
      loop: '<i class="fa-solid fa-repeat"></i>',
      single: '<i class="fa-solid fa-rotate-right"></i>',
      random: '<i class="fa-solid fa-shuffle"></i>',
      order: '<i class="fa-solid fa-arrow-down-1-9"></i>'
    };

    const curMode = this.config.playMode || "loop";

    if (modeBtn) {
      modeBtn.innerHTML = modeIcons[curMode];
      modeBtn.title = `播放模式: ${modeLabels[curMode]} (点击切换)`;
    }

    if (titleEl) {
      if (track && track.name) {
        titleEl.textContent = track.name;
        titleEl.title = track.name;
        if (subEl) subEl.textContent = modeLabels[curMode];
      } else {
        titleEl.textContent = "None";
        titleEl.title = "无曲目";
        if (subEl) subEl.textContent = "No Audio";
      }
    }

    if (this.audioObj) {
      const targetUrl = track ? track.url : "";
      if (this.audioObj.src !== targetUrl) {
        this.audioObj.src = targetUrl;
        if (this.isPlaying && targetUrl) this.audioObj.play();
        else if (!targetUrl) {
          this.audioObj.pause();
          this.isPlaying = false;
          const pBtn = document.getElementById("btn-play-pause");
          const cd = document.getElementById("player-cd");
          if (pBtn) pBtn.innerHTML = '<i class="fa-solid fa-play ml-0.5"></i>';
          if (cd) cd.classList.remove("playing");
        }
      }
    }
  },

  injectSettingsTab() {
    const nav = document.querySelector("#app-sidebar nav") || document.querySelector("aside nav");
    const main = document.querySelector("main");
    if (!main) return;

    let uiBtn = document.getElementById("nav-btn-ui-settings");
    if (!uiBtn && nav) {
      uiBtn = document.createElement("button");
      uiBtn.id = "nav-btn-ui-settings";
      uiBtn.className = "nav-btn w-full flex items-center gap-3 px-4 py-2.5 rounded-xl border border-transparent";
      uiBtn.setAttribute("data-tab", "tab-ui-settings");
      uiBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles w-5 text-center text-slate-300"></i><span class="font-semibold text-sm">UI 视觉与偏好</span>`;
      nav.appendChild(uiBtn);
    }

    let tabPane = document.getElementById("tab-ui-settings");
    if (!tabPane) {
      const tabHtml = `
      <section id="tab-ui-settings" class="tab-pane space-y-6">
        
        <div class="glass-card p-7 rounded-2xl relative border">
          <div class="flex items-center justify-between pb-5 mb-6 border-b border-purple-200/30">
            <div>
              <h2 class="text-xl font-bold flex items-center gap-2.5 neri-card-title">
                <i class="fa-solid fa-palette text-2xl text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                <span>NeriUI设置中心</span>
              </h2>
              <p class="text-xs opacity-75 mt-1 neri-card-desc">高定视觉主题、全景透明度与壁纸歌单自定义</p>
            </div>
          </div>

          <div class="space-y-6">
            
            <!-- 第一行：色彩主题 + 磨砂模糊度 + 面板不透明度 (0%~100%) + 切换动画时长 -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
              
              <div class="sub-card p-4 rounded-xl border">
                <label class="block mb-1 font-bold text-xs flex items-center gap-1.5 neri-label">
                  <i class="fa-solid fa-circle-half-stroke text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                  <span>色彩主题模式</span>
                </label>
                <p class="text-[11px] mb-2 neri-subtext">暗色静谧深紫；亮色温润清透；可跟随系统。</p>
                <select id="ui-theme" class="w-full p-2.5 rounded-lg border text-xs font-semibold outline-none cursor-pointer">
                  <option value="dark">🌙 夜阑静谧 / 绝美暗色 (Deep Violet)</option>
                  <option value="light">☀️ 清晨清透 / 珍珠亮色 (Light Porcelain)</option>
                  <option value="system">🌗 随境而动 / 跟随系统 (System Auto)</option>
                </select>
              </div>

              <div class="sub-card p-4 rounded-xl border">
                <div class="flex items-center justify-between mb-1">
                  <label class="font-bold text-xs flex items-center gap-1.5 neri-label">
                    <i class="fa-solid fa-droplet text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                    <span>磨砂模糊度 (Blur)</span>
                  </label>
                  <span id="ui-blur-val" class="font-mono text-xs px-2 py-0.5 rounded neri-badge font-bold">16px</span>
                </div>
                <p class="text-[11px] mb-2 neri-subtext">0px 完全关停滤镜，杜绝壁纸畸变。</p>
                <input type="range" id="ui-blur-range" min="0" max="40" step="1" value="16" class="w-full accent-[#9C6B9E] cursor-pointer">
              </div>

              <div class="sub-card p-4 rounded-xl border">
                <div class="flex items-center justify-between mb-1">
                  <label class="font-bold text-xs flex items-center gap-1.5 neri-label">
                    <i class="fa-solid fa-eye text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                    <span>面板透明度 (0%~100%)</span>
                  </label>
                  <span id="ui-opacity-val" class="font-mono text-xs px-2 py-0.5 rounded neri-badge font-bold">58%</span>
                </div>
                <p class="text-[11px] mb-2 neri-subtext">支持完全透明(0%)全屏壁纸HUD模式。</p>
                <input type="range" id="ui-opacity-range" min="0" max="1.0" step="0.02" value="0.58" class="w-full accent-[#9C6B9E] cursor-pointer">
              </div>

              <div class="sub-card p-4 rounded-xl border">
                <div class="flex items-center justify-between mb-1">
                  <label class="font-bold text-xs flex items-center gap-1.5 neri-label">
                    <i class="fa-solid fa-stopwatch text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                    <span>切换动画时长</span>
                  </label>
                  <span id="ui-anim-val" class="font-mono text-xs px-2 py-0.5 rounded neri-badge font-bold">0.45s</span>
                </div>
                <p class="text-[11px] mb-2 neri-subtext">自定义标签页浮动淡入的切换速率。</p>
                <input type="range" id="ui-anim-range" min="0.1" max="1.2" step="0.05" value="0.45" class="w-full accent-[#9C6B9E] cursor-pointer">
              </div>

            </div>

            <!-- 第二行：背景壁纸库 (可折叠，支持批量多选上传) -->
            <div class="collapsible-card border sub-card">
              <div class="collapsible-header" id="header-toggle-wp">
                <div class="flex items-center gap-2.5 font-bold text-sm neri-label">
                  <i class="fa-solid fa-images text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                  <span>全景壁纸库管理 (支持多选批量上传)</span>
                  <span id="badge-wp-count" class="text-xs px-2 py-0.5 rounded-full neri-badge">0 张壁纸</span>
                </div>
                <div class="flex items-center gap-3">
                  <span class="text-xs opacity-75 neri-subtext">点击展开/折叠</span>
                  <i class="fa-solid fa-chevron-down text-xs transition-transform duration-200" id="icon-toggle-wp"></i>
                </div>
              </div>

              <div class="collapsible-content" id="content-wp">
                <div class="flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-purple-200/20">
                  <div class="flex gap-2 items-center">
                    <label class="btn-primary px-3.5 py-1.5 rounded-lg text-xs font-bold cursor-pointer flex items-center gap-1.5 shadow-md">
                      <i class="fa-solid fa-cloud-arrow-up"></i>
                      <span>上传本地壁纸 (支持按住Ctrl多选)</span>
                      <input type="file" id="ui-wp-file" accept="image/*" multiple class="hidden">
                    </label>
                    <button id="btn-add-wp-url" class="neri-btn-outline px-3.5 py-1.5 rounded-lg text-xs font-bold border transition cursor-pointer">
                      <i class="fa-solid fa-link mr-1"></i>添加壁纸直链
                    </button>
                  </div>
                  <button id="btn-reset-default-wp" class="neri-btn-danger px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer">
                    <i class="fa-solid fa-rotate-left mr-1"></i>恢复默认纯色无背景
                  </button>
                </div>

                <div id="wp-list-container" class="space-y-2 max-h-60 overflow-y-auto pr-1"></div>
              </div>
            </div>

            <!-- 第三行：歌单与背景音乐库 (可折叠，支持批量多选上传) -->
            <div class="collapsible-card border sub-card">
              <div class="collapsible-header" id="header-toggle-music">
                <div class="flex items-center gap-2.5 font-bold text-sm neri-label">
                  <i class="fa-solid fa-compact-disc text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                  <span>悬浮播放器曲库与歌单 (支持多选批量上传)</span>
                  <span id="badge-song-count" class="text-xs px-2 py-0.5 rounded-full neri-badge">0 首歌曲</span>
                </div>
                <div class="flex items-center gap-3">
                  <span class="text-xs opacity-75 neri-subtext">点击展开/折叠</span>
                  <i class="fa-solid fa-chevron-down text-xs transition-transform duration-200" id="icon-toggle-music"></i>
                </div>
              </div>

              <div class="collapsible-content" id="content-music">
                <div class="flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-purple-200/20">
                  <div class="flex gap-2 items-center">
                    <label class="btn-primary px-3.5 py-1.5 rounded-lg text-xs font-bold cursor-pointer flex items-center gap-1.5 shadow-md">
                      <i class="fa-solid fa-upload"></i>
                      <span>上传本地音频文件 (支持按住Ctrl多选)</span>
                      <input type="file" id="ui-song-file" accept="audio/*" multiple class="hidden">
                    </label>
                    <button id="btn-add-song-url" class="neri-btn-outline px-3.5 py-1.5 rounded-lg text-xs font-bold border transition cursor-pointer">
                      <i class="fa-solid fa-plus mr-1"></i>添加音频直链
                    </button>
                  </div>
                  <span class="text-xs opacity-75 neri-subtext">支持上一首/下一首与随机循环；无音频时显示 None</span>
                </div>

                <div id="song-list-container" class="space-y-2 max-h-60 overflow-y-auto pr-1"></div>
              </div>
            </div>

            <!-- 第四行：二次元粒子特效中心 -->
            <div class="sub-card p-5 rounded-xl border space-y-4">
              <div class="flex items-center justify-between">
                <div>
                  <h3 class="font-bold text-sm flex items-center gap-2 neri-label">
                    <i class="fa-solid fa-wand-magic-sparkles text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                    <span>二次元鼠标拖尾与点击华丽光效</span>
                  </h3>
                  <p class="text-xs opacity-75 mt-0.5 neri-subtext">调节样式或开关会即时生效并自动保存。</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" id="ui-fx-enabled" class="sr-only peer">
                  <div class="w-11 h-6 bg-slate-400/40 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#9C6B9E]"></div>
                </label>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-4 gap-4 pt-2">
                <div>
                  <label class="text-xs font-semibold block mb-1 neri-label">移动拖尾样式</label>
                  <select id="ui-fx-trail-style" class="w-full p-2 rounded-lg border text-xs outline-none">
                    <option value="sakura">🌸 浪漫樱花落英 (Sakura)</option>
                    <option value="stardust">✨ 梦幻银河星尘 (Stardust)</option>
                    <option value="orb">🔮 柔光魔法光晕 (Magic Orb)</option>
                  </select>
                </div>

                <div>
                  <label class="text-xs font-semibold block mb-1 neri-label">点击触发动效</label>
                  <select id="ui-fx-click-style" class="w-full p-2 rounded-lg border text-xs outline-none">
                    <option value="bloom">🌸 樱花散华光环 (Sakura Bloom)</option>
                    <option value="starburst">💥 璀璨星芒爆散 (Starburst)</option>
                    <option value="ripple">🌊 水涟波纹荡漾 (Ripple)</option>
                  </select>
                </div>

                <div>
                  <div class="flex justify-between items-center mb-1">
                    <label class="text-xs font-semibold neri-label">拖尾持续时间</label>
                    <span id="ui-fx-decay-val" class="text-[11px] opacity-75 font-mono neri-subtext">慢速悠长</span>
                  </div>
                  <input type="range" id="ui-fx-decay" min="0.005" max="0.04" step="0.002" value="0.012" class="w-full accent-[#9C6B9E] cursor-pointer">
                </div>

                <div>
                  <div class="flex justify-between items-center mb-1">
                    <label class="text-xs font-semibold neri-label">粒子大小与清晰度</label>
                    <span id="ui-fx-size-val" class="text-[11px] opacity-75 font-mono neri-subtext">5px</span>
                  </div>
                  <input type="range" id="ui-fx-size" min="3" max="10" step="1" value="5" class="w-full accent-[#9C6B9E] cursor-pointer">
                </div>
              </div>
            </div>

            <!-- 第五行：上下滚动字幕 -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
              
              <div class="sub-card p-4 rounded-xl border">
                <div class="flex items-center justify-between mb-2">
                  <h3 class="font-bold text-sm flex items-center gap-2 neri-label">
                    <i class="fa-solid fa-chevron-up text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                    <span>顶部走马灯字幕 (自适应防遮挡)</span>
                  </h3>
                  <label class="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
                    <input type="checkbox" id="ui-top-en" class="accent-[#9C6B9E] w-4 h-4"> 启用
                  </label>
                </div>
                <input type="text" id="ui-top-text" class="w-full p-2 rounded-lg border text-sm mb-2.5 outline-none" placeholder="滚动的字幕文字">
                <div class="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">间隔符号 (Delimiter)</span>
                    <input type="text" id="ui-top-delimiter" class="w-full p-1.5 rounded-lg border text-center text-xs" placeholder="---">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">间距大小 (px)</span>
                    <input type="number" id="ui-top-spacing" min="0" max="100" class="w-full p-1.5 rounded-lg border text-center text-xs" placeholder="16">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">字号 (px)</span>
                    <input type="number" id="ui-top-size" min="10" max="32" class="w-full p-1.5 rounded-lg border text-center text-xs">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">文字透明 (0-1)</span>
                    <input type="number" step="0.1" min="0" max="1" id="ui-top-opacity" class="w-full p-1.5 rounded-lg border text-center text-xs">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">遮罩不透明 (0-1)</span>
                    <input type="number" step="0.1" min="0" max="1" id="ui-top-mask" class="w-full p-1.5 rounded-lg border text-center text-xs" title="填 0 为无遮罩完全穿透">
                  </div>
                </div>
                <p class="text-[10px] opacity-70 mt-2 neri-subtext">短句子自动复制多次轮流滚动（例如：---AAA---AAA---AAA---），长句子自动适度减少重复次数避免字体重叠。</p>
              </div>

              <div class="sub-card p-4 rounded-xl border">
                <div class="flex items-center justify-between mb-2">
                  <h3 class="font-bold text-sm flex items-center gap-2 neri-label">
                    <i class="fa-solid fa-chevron-down text-[#9C6B9E] dark:text-[#E2BAEE]"></i>
                    <span>底部状态栏字幕</span>
                  </h3>
                  <label class="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
                    <input type="checkbox" id="ui-bot-en" class="accent-[#9C6B9E] w-4 h-4"> 启用
                  </label>
                </div>
                <input type="text" id="ui-bot-text" class="w-full p-2 rounded-lg border text-sm mb-2.5 outline-none" placeholder="滚动的字幕文字">
                <div class="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">间隔符号 (Delimiter)</span>
                    <input type="text" id="ui-bot-delimiter" class="w-full p-1.5 rounded-lg border text-center text-xs" placeholder="---">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">间距大小 (px)</span>
                    <input type="number" id="ui-bot-spacing" min="0" max="100" class="w-full p-1.5 rounded-lg border text-center text-xs" placeholder="12">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">字号 (px)</span>
                    <input type="number" id="ui-bot-size" min="10" max="32" class="w-full p-1.5 rounded-lg border text-center text-xs">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">文字透明 (0-1)</span>
                    <input type="number" step="0.1" min="0" max="1" id="ui-bot-opacity" class="w-full p-1.5 rounded-lg border text-center text-xs">
                  </div>
                  <div>
                    <span class="text-[11px] opacity-75 block mb-0.5 neri-subtext">遮罩不透明 (0-1)</span>
                    <input type="number" step="0.1" min="0" max="1" id="ui-bot-mask" class="w-full p-1.5 rounded-lg border text-center text-xs" title="填 0 为无遮罩完全穿透">
                  </div>
                </div>
                <p class="text-[10px] opacity-70 mt-2 neri-subtext">短句子自动复制多次轮流滚动，长句子自动精简避免字体重叠，并支持自定义间隔与间距。</p>
              </div>

            </div>

            <!-- 保存按钮 -->
            <div class="flex justify-end pt-2">
              <button id="btn-save-ui-all" class="neri-btn-save px-8 py-2.5 rounded-xl font-bold text-sm shadow-xl flex items-center gap-2 cursor-pointer">
                <i class="fa-solid fa-check"></i>
                <span>保存并立刻应用全部配置</span>
              </button>
            </div>

          </div>
        </div>

      </section>
      `;
      main.insertAdjacentHTML('beforeend', tabHtml);
      tabPane = document.getElementById("tab-ui-settings");
    }

    uiBtn.onclick = () => {
      document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
      uiBtn.classList.add("active");

      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
      tabPane.classList.add("active");

      try {
        sessionStorage.setItem("neri_active_tab", "tab-ui-settings");
      } catch (e) {}

      this.syncInputsFast();
      this.renderWallpaperList();
      this.renderPlaylist();
    };

    document.querySelectorAll(".nav-btn").forEach(b => {
      if (b !== uiBtn) {
        b.addEventListener("click", () => {
          try {
            sessionStorage.setItem("neri_active_tab", b.getAttribute("data-tab") || "");
          } catch (e) {}
          uiBtn.classList.remove("active");
          tabPane.classList.remove("active");
        });
      }
    });

    this.bindEvents();
    this.syncInputsFast();
    this.renderWallpaperList();
    this.renderPlaylist();

    // 记忆标签页自动恢复
    try {
      if (sessionStorage.getItem("neri_active_tab") === "tab-ui-settings") {
        setTimeout(() => {
          if (uiBtn) uiBtn.click();
        }, 80);
      }
    } catch (e) {}
  },

  syncInputsFast() {
    const themeEl = document.getElementById("ui-theme");
    if (themeEl) themeEl.value = this.config.themeMode || "dark";

    const blur = this.config.panelBlur !== undefined ? parseInt(this.config.panelBlur) : 16;
    const blurRange = document.getElementById("ui-blur-range");
    const blurVal = document.getElementById("ui-blur-val");
    if (blurRange) blurRange.value = blur;
    if (blurVal) blurVal.textContent = `${blur}px`;

    const opacity = this.config.panelOpacity !== undefined ? parseFloat(this.config.panelOpacity) : 0.78;
    const opRange = document.getElementById("ui-opacity-range");
    const opVal = document.getElementById("ui-opacity-val");
    if (opRange) opRange.value = opacity;
    if (opVal) opVal.textContent = `${Math.round(opacity * 100)}%`;

    const anim = this.config.tabAnimDuration !== undefined ? parseFloat(this.config.tabAnimDuration) : 0.45;
    const animRange = document.getElementById("ui-anim-range");
    const animVal = document.getElementById("ui-anim-val");
    if (animRange) animRange.value = anim;
    if (animVal) animVal.textContent = `${anim}s`;

    const fx = this.config.mouseFx || {};
    const fxEn = document.getElementById("ui-fx-enabled");
    if (fxEn) fxEn.checked = !!fx.enabled;
    const fxTrail = document.getElementById("ui-fx-trail-style");
    if (fxTrail) fxTrail.value = fx.trailStyle || "sakura";
    const fxClick = document.getElementById("ui-fx-click-style");
    if (fxClick) fxClick.value = fx.clickStyle || "bloom";
    const fxDecay = document.getElementById("ui-fx-decay");
    if (fxDecay) fxDecay.value = fx.decayRate !== undefined ? fx.decayRate : 0.012;
    const fxSize = document.getElementById("ui-fx-size");
    const fxSizeVal = document.getElementById("ui-fx-size-val");
    if (fxSize) fxSize.value = fx.particleSize || 5;
    if (fxSizeVal) fxSizeVal.textContent = `${fx.particleSize || 5}px`;

    const t = this.config.topMarquee || {};
    const tEn = document.getElementById("ui-top-en");
    if (tEn) tEn.checked = !!t.enabled;
    const tText = document.getElementById("ui-top-text");
    if (tText) tText.value = t.text || "";
    const tDelim = document.getElementById("ui-top-delimiter");
    if (tDelim) tDelim.value = t.delimiter !== undefined ? t.delimiter : "---";
    const tSpacing = document.getElementById("ui-top-spacing");
    if (tSpacing) tSpacing.value = t.spacing !== undefined ? t.spacing : 16;
    const tSize = document.getElementById("ui-top-size");
    if (tSize) tSize.value = t.size || 14;
    const tOp = document.getElementById("ui-top-opacity");
    if (tOp) tOp.value = t.opacity !== undefined ? t.opacity : 0.9;
    const tMask = document.getElementById("ui-top-mask");
    if (tMask) tMask.value = t.maskOpacity !== undefined ? t.maskOpacity : 0.6;

    const b = this.config.bottomMarquee || {};
    const bEn = document.getElementById("ui-bot-en");
    if (bEn) bEn.checked = !!b.enabled;
    const bText = document.getElementById("ui-bot-text");
    if (bText) bText.value = b.text || "";
    const bDelim = document.getElementById("ui-bot-delimiter");
    if (bDelim) bDelim.value = b.delimiter !== undefined ? b.delimiter : "---";
    const bSpacing = document.getElementById("ui-bot-spacing");
    if (bSpacing) bSpacing.value = b.spacing !== undefined ? b.spacing : 12;
    const bSize = document.getElementById("ui-bot-size");
    if (bSize) bSize.value = b.size || 12;
    const bOp = document.getElementById("ui-bot-opacity");
    if (bOp) bOp.value = b.opacity !== undefined ? b.opacity : 0.75;
    const bMask = document.getElementById("ui-bot-mask");
    if (bMask) bMask.value = b.maskOpacity !== undefined ? b.maskOpacity : 0.5;
  },

  renderWallpaperList() {
    const listEl = document.getElementById("wp-list-container");
    const countEl = document.getElementById("badge-wp-count");
    if (!listEl) return;

    countEl.textContent = `${this.config.wallpapers.length} 张壁纸`;
    listEl.innerHTML = "";

    if (this.config.wallpapers.length === 0) {
      listEl.innerHTML = `<div class="text-xs py-3 text-center neri-empty-tip">壁纸库为空，点击上方按钮上传壁纸或添加直链</div>`;
      return;
    }

    this.config.wallpapers.forEach((wp) => {
      const isCurrent = this.config.currentWallpaperId === wp.id;
      const item = document.createElement("div");
      item.className = `flex items-center justify-between p-2.5 rounded-lg border transition ${
        isCurrent ? "border-purple-500 bg-purple-500/20 font-semibold" : "border-purple-200/20 bg-white/20 dark:bg-purple-950/20"
      }`;

      item.innerHTML = `
        <div class="flex items-center gap-3 overflow-hidden flex-1">
          <div class="w-10 h-7 rounded border border-purple-300/40 bg-cover bg-center shrink-0" style="background-image: url('${wp.url}')"></div>
          <div class="truncate text-xs">
            <span class="font-medium neri-label">${wp.name}</span>
            ${isCurrent ? '<span class="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-purple-500 text-white font-bold">当前应用中</span>' : ''}
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          ${!isCurrent ? `<button class="btn-use-wp text-xs px-2.5 py-1 rounded transition cursor-pointer" data-id="${wp.id}">应用</button>` : ''}
          <button class="btn-rename-wp text-xs p-1 text-slate-400 hover:text-purple-400 transition cursor-pointer" data-id="${wp.id}" title="重命名"><i class="fa-solid fa-pen-to-square"></i></button>
          <button class="btn-del-wp text-xs p-1 text-rose-400 hover:text-rose-600 transition cursor-pointer" data-id="${wp.id}" title="删除"><i class="fa-solid fa-trash-can"></i></button>
        </div>
      `;
      listEl.appendChild(item);
    });

    listEl.querySelectorAll(".btn-use-wp").forEach(b => {
      b.onclick = () => {
        this.config.currentWallpaperId = b.getAttribute("data-id");
        this.saveConfig();
        this.renderWallpaperList();
        NeriModal.toast("壁纸已即时切换应用！");
      };
    });

    listEl.querySelectorAll(".btn-rename-wp").forEach(b => {
      b.onclick = async () => {
        const id = b.getAttribute("data-id");
        const wp = this.config.wallpapers.find(w => w.id === id);
        if (!wp) return;
        const newName = await NeriModal.prompt("请输入新的壁纸名称：", wp.name, "重命名壁纸");
        if (newName && newName.trim()) {
          wp.name = newName.trim();
          this.saveConfig();
          this.renderWallpaperList();
          NeriModal.toast("壁纸名称已修改");
        }
      };
    });

    listEl.querySelectorAll(".btn-del-wp").forEach(b => {
      b.onclick = async () => {
        const id = b.getAttribute("data-id");
        const wp = this.config.wallpapers.find(w => w.id === id);
        const ok = await NeriModal.confirm("确定要从壁纸库中移除此壁纸吗？", "删除确认");
        if (ok) {
          if (wp && wp.idbId) {
            await NeriDB.delete(wp.idbId);
          }
          this.config.wallpapers = this.config.wallpapers.filter(w => w.id !== id);
          if (this.config.currentWallpaperId === id) {
            this.config.currentWallpaperId = "";
          }
          this.saveConfig();
          this.renderWallpaperList();
          NeriModal.toast("壁纸已成功移除");
        }
      };
    });
  },

  renderPlaylist() {
    const listEl = document.getElementById("song-list-container");
    const countEl = document.getElementById("badge-song-count");
    if (!listEl) return;

    countEl.textContent = `${this.config.playlist.length} 首歌曲`;
    listEl.innerHTML = "";

    if (this.config.playlist.length === 0) {
      listEl.innerHTML = `<div class="text-xs py-3 text-center neri-empty-tip">歌单为空，悬浮黑胶控件将显示 None</div>`;
      return;
    }

    this.config.playlist.forEach((song) => {
      const isCurrent = this.config.currentSongId === song.id;
      const item = document.createElement("div");
      item.className = `flex items-center justify-between p-2.5 rounded-lg border transition ${
        isCurrent ? "border-purple-500 bg-purple-500/20 font-semibold" : "border-purple-200/20 bg-white/20 dark:bg-purple-950/20"
      }`;

      item.innerHTML = `
        <div class="flex items-center gap-2.5 overflow-hidden flex-1">
          <i class="fa-solid fa-music text-xs ${isCurrent ? 'text-purple-400 animate-pulse' : 'opacity-50'}"></i>
          <span class="truncate text-xs font-medium neri-label">${song.name}</span>
          ${isCurrent ? '<span class="text-[10px] px-1.5 py-0.5 rounded bg-purple-500 text-white font-bold shrink-0">当前播放</span>' : ''}
        </div>
        <div class="flex items-center gap-2 shrink-0">
          ${!isCurrent ? `<button class="btn-play-song text-xs px-2.5 py-1 rounded transition cursor-pointer" data-id="${song.id}">播放</button>` : ''}
          <button class="btn-rename-song text-xs p-1 text-slate-400 hover:text-purple-400 transition cursor-pointer" data-id="${song.id}" title="重命名"><i class="fa-solid fa-pen-to-square"></i></button>
          <button class="btn-del-song text-xs p-1 text-rose-400 hover:text-rose-600 transition cursor-pointer" data-id="${song.id}" title="删除"><i class="fa-solid fa-trash-can"></i></button>
        </div>
      `;
      listEl.appendChild(item);
    });

    listEl.querySelectorAll(".btn-play-song").forEach(b => {
      b.onclick = () => {
        this.config.currentSongId = b.getAttribute("data-id");
        this.saveConfig();
        this.renderPlaylist();
        this.updatePlayerDisplay();
        this.playCurrent();
        NeriModal.toast(`正在播放: ${this.getCurrentTrack()?.name}`);
      };
    });

    listEl.querySelectorAll(".btn-rename-song").forEach(b => {
      b.onclick = async () => {
        const id = b.getAttribute("data-id");
        const song = this.config.playlist.find(s => s.id === id);
        if (!song) return;
        const newName = await NeriModal.prompt("请输入新的歌曲名称：", song.name, "重命名歌曲");
        if (newName && newName.trim()) {
          song.name = newName.trim();
          this.saveConfig();
          this.renderPlaylist();
          this.updatePlayerDisplay();
          NeriModal.toast("曲目名称已修改");
        }
      };
    });

    listEl.querySelectorAll(".btn-del-song").forEach(b => {
      b.onclick = async () => {
        const id = b.getAttribute("data-id");
        const song = this.config.playlist.find(s => s.id === id);
        const ok = await NeriModal.confirm("确定要从歌单中删除此歌曲吗？", "删除曲目");
        if (ok) {
          if (song && song.idbId) {
            await NeriDB.delete(song.idbId);
          }
          this.config.playlist = this.config.playlist.filter(s => s.id !== id);
          if (this.config.currentSongId === id) {
            this.config.currentSongId = this.config.playlist[0] ? this.config.playlist[0].id : "";
          }
          this.saveConfig();
          this.renderPlaylist();
          this.updatePlayerDisplay();
          NeriModal.toast("曲目已从歌单删除");
        }
      };
    });
  },

  bindEvents() {
    const hWp = document.getElementById("header-toggle-wp");
    const cWp = document.getElementById("content-wp");
    const iWp = document.getElementById("icon-toggle-wp");
    if (hWp && cWp) {
      hWp.onclick = () => {
        cWp.classList.toggle("collapsed");
        if (iWp) iWp.style.transform = cWp.classList.contains("collapsed") ? "rotate(-90deg)" : "rotate(0deg)";
      };
    }

    const hMusic = document.getElementById("header-toggle-music");
    const cMusic = document.getElementById("content-music");
    const iMusic = document.getElementById("icon-toggle-music");
    if (hMusic && cMusic) {
      hMusic.onclick = () => {
        cMusic.classList.toggle("collapsed");
        if (iMusic) iMusic.style.transform = cMusic.classList.contains("collapsed") ? "rotate(-90deg)" : "rotate(0deg)";
      };
    }

    const btnResetWp = document.getElementById("btn-reset-default-wp");
    if (btnResetWp) {
      btnResetWp.onclick = () => {
        this.config.currentWallpaperId = "";
        this.saveConfig();
        this.renderWallpaperList();
        NeriModal.toast("已恢复默认纯色毛玻璃背景");
      };
    }

    const btnAddWpUrl = document.getElementById("btn-add-wp-url");
    if (btnAddWpUrl) {
      btnAddWpUrl.onclick = async () => {
        const url = await NeriModal.prompt("请输入壁纸图片的网络直链 (URL)：", "", "添加网络壁纸");
        if (url && url.trim()) {
          const name = await NeriModal.prompt("请为这张壁纸起个名字：", "网络壁纸", "壁纸命名") || "自定义壁纸";
          const newWp = { id: `wp_${Date.now()}`, name: name.trim(), url: url.trim(), idbId: null };
          this.config.wallpapers.unshift(newWp);
          this.config.currentWallpaperId = newWp.id;
          this.saveConfig();
          this.renderWallpaperList();
          NeriModal.toast("壁纸已添加并成功应用！");
        }
      };
    }

    // 本地壁纸上传 (支持多选)
    const fileWp = document.getElementById("ui-wp-file");
    if (fileWp) {
      fileWp.onchange = async (e) => {
        const files = Array.from(e.target.files);
        if (files.length === 0) return;
        NeriModal.toast(`正在批量处理并固化 ${files.length} 张壁纸...`, 3000);

        for (const file of files) {
          const customId = `wp_idb_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
          const res = await this.uploadAsset(file, customId);
          const name = file.name.replace(/\.[^/.]+$/, "");
          const newWp = { 
            id: `wp_${Date.now()}_${Math.random().toString(36).slice(2, 5)}`, 
            name: name, 
            url: res.url, 
            idbId: res.idbId 
          };
          this.config.wallpapers.unshift(newWp);
          if (!this.config.currentWallpaperId) {
            this.config.currentWallpaperId = newWp.id;
          }
        }
        
        fileWp.value = ""; // 清空 input 允许再次选同名文件
        this.saveConfig();
        this.renderWallpaperList();
        NeriModal.toast(`✨ 成功导入并永久固化 ${files.length} 张壁纸！`);
      };
    }

    const btnAddSongUrl = document.getElementById("btn-add-song-url");
    if (btnAddSongUrl) {
      btnAddSongUrl.onclick = async () => {
        const url = await NeriModal.prompt("请输入音频的网络直链 (URL)：", "", "添加网络音频");
        if (url && url.trim()) {
          const name = await NeriModal.prompt("请为这首曲目起个名字：", "网络音乐", "曲目命名") || "自定义音乐";
          const newSong = { id: `song_${Date.now()}`, name: name.trim(), url: url.trim(), idbId: null };
          this.config.playlist.unshift(newSong);
          this.config.currentSongId = newSong.id;
          this.saveConfig();
          this.renderPlaylist();
          this.updatePlayerDisplay();
          NeriModal.toast("新曲目已加入歌单！");
        }
      };
    }

    // 本地音乐上传 (支持多选)
    const fileSong = document.getElementById("ui-song-file");
    if (fileSong) {
      fileSong.onchange = async (e) => {
        const files = Array.from(e.target.files);
        if (files.length === 0) return;
        NeriModal.toast(`正在批量处理并固化 ${files.length} 首歌曲...`, 3000);

        for (const file of files) {
          const customId = `song_idb_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
          const res = await this.uploadAsset(file, customId);
          const name = file.name.replace(/\.[^/.]+$/, "");
          const newSong = { 
            id: `song_${Date.now()}_${Math.random().toString(36).slice(2, 5)}`, 
            name: name, 
            url: res.url, 
            idbId: res.idbId 
          };
          this.config.playlist.unshift(newSong);
          if (!this.config.currentSongId) {
            this.config.currentSongId = newSong.id;
          }
        }

        fileSong.value = "";
        this.saveConfig();
        this.renderPlaylist();
        this.updatePlayerDisplay();
        NeriModal.toast(`✨ 成功导入并永久固化 ${files.length} 首曲目！`);
      };
    }

    // 磨砂模糊度滑块 (实时渲染 + 固化)
    const blurRange = document.getElementById("ui-blur-range");
    const blurVal = document.getElementById("ui-blur-val");
    if (blurRange) {
      blurRange.oninput = (e) => {
        const val = parseInt(e.target.value) || 0;
        if (blurVal) blurVal.textContent = `${val}px`;
        this.config.panelBlur = val;
        document.documentElement.style.setProperty("--panel-blur", `${val}px`);
        if (val <= 0) {
          document.documentElement.style.setProperty("--panel-blur-css", "none");
        } else {
          document.documentElement.style.setProperty("--panel-blur-css", `blur(${val}px)`);
        }
      };
      blurRange.onchange = () => {
        this.saveConfig();
        NeriModal.toast(`磨砂模糊度已固化: ${this.config.panelBlur}px`);
      };
    }

    // 面板不透明度滑块 (0%~100%) (实时渲染 + 固化)
    const opRange = document.getElementById("ui-opacity-range");
    const opVal = document.getElementById("ui-opacity-val");
    if (opRange) {
      opRange.oninput = (e) => {
        const val = parseFloat(e.target.value);
        if (opVal) opVal.textContent = `${Math.round(val * 100)}%`;
        document.documentElement.style.setProperty("--panel-opacity", val);
        this.config.panelOpacity = val;
      };
      opRange.onchange = () => {
        this.saveConfig();
        NeriModal.toast(`面板不透明度已固化: ${Math.round(this.config.panelOpacity * 100)}%`);
      };
    }

    // 动画时长滑块 (实时渲染 + 固化)
    const animRange = document.getElementById("ui-anim-range");
    const animVal = document.getElementById("ui-anim-val");
    if (animRange) {
      animRange.oninput = (e) => {
        const val = parseFloat(e.target.value) || 0.45;
        if (animVal) animVal.textContent = `${val}s`;
        document.documentElement.style.setProperty("--tab-anim-duration", `${val}s`);
        this.config.tabAnimDuration = val;
      };
      animRange.onchange = () => {
        this.saveConfig();
        NeriModal.toast(`切换动画时长已固化: ${this.config.tabAnimDuration}s`);
      };
    }

    // 主题切换实时预览 + 立即永久固化 (暗色 / 亮色 / 跟随系统)
    const themeSelect = document.getElementById("ui-theme");
    if (themeSelect) {
      themeSelect.onchange = (e) => {
        this.config.themeMode = e.target.value;
        this.applyTheme();
        this.renderWallpaperList();
        this.renderPlaylist();
        this.saveConfig();
        const text = e.target.options[e.target.selectedIndex].text;
        NeriModal.toast(`主题模式已切换并固化: ${text}`);
      };
    }

    // 鼠标粒子特效即时联动 + 固化
    const fxSwitch = document.getElementById("ui-fx-enabled");
    if (fxSwitch) {
      fxSwitch.onchange = (e) => {
        if (!this.config.mouseFx) this.config.mouseFx = {};
        this.config.mouseFx.enabled = e.target.checked;
        this.saveConfig();
        NeriModal.toast(this.config.mouseFx.enabled ? "🌸 粒子光效已开启并固化" : "粒子光效已停用并固化");
      };
    }

    const fxTrail = document.getElementById("ui-fx-trail-style");
    if (fxTrail) {
      fxTrail.onchange = (e) => {
        if (!this.config.mouseFx) this.config.mouseFx = {};
        this.config.mouseFx.trailStyle = e.target.value;
        this.saveConfig();
        NeriModal.toast(`拖尾已切换并固化: ${e.target.options[e.target.selectedIndex].text}`);
      };
    }

    const fxClick = document.getElementById("ui-fx-click-style");
    if (fxClick) {
      fxClick.onchange = (e) => {
        if (!this.config.mouseFx) this.config.mouseFx = {};
        this.config.mouseFx.clickStyle = e.target.value;
        this.saveConfig();
        NeriModal.toast(`点击动效已切换并固化: ${e.target.options[e.target.selectedIndex].text}`);
      };
    }

    const fxDecay = document.getElementById("ui-fx-decay");
    if (fxDecay) {
      fxDecay.oninput = (e) => {
        if (!this.config.mouseFx) this.config.mouseFx = {};
        this.config.mouseFx.decayRate = parseFloat(e.target.value);
      };
      fxDecay.onchange = () => {
        this.saveConfig();
      };
    }

    const fxSize = document.getElementById("ui-fx-size");
    const fxSizeVal = document.getElementById("ui-fx-size-val");
    if (fxSize) {
      fxSize.oninput = (e) => {
        const val = parseInt(e.target.value);
        if (fxSizeVal) fxSizeVal.textContent = `${val}px`;
        if (!this.config.mouseFx) this.config.mouseFx = {};
        this.config.mouseFx.particleSize = val;
      };
      fxSize.onchange = () => {
        this.saveConfig();
      };
    }

    // 顶部滚动字幕联动 + 固化
    const topEn = document.getElementById("ui-top-en");
    if (topEn) {
      topEn.onchange = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.enabled = e.target.checked;
        this.applyTheme();
        this.saveConfig();
        NeriModal.toast(this.config.topMarquee.enabled ? "顶部字幕已开启并固化" : "顶部字幕已关闭并固化");
      };
    }
    const topText = document.getElementById("ui-top-text");
    if (topText) {
      topText.oninput = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.text = e.target.value;
        this.applyTheme();
      };
      topText.onchange = () => {
        this.saveConfig();
      };
    }
    const topDelim = document.getElementById("ui-top-delimiter");
    if (topDelim) {
      topDelim.oninput = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.delimiter = e.target.value;
        this.applyTheme();
      };
      topDelim.onchange = () => {
        this.saveConfig();
      };
    }
    const topSpacing = document.getElementById("ui-top-spacing");
    if (topSpacing) {
      topSpacing.oninput = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.spacing = parseInt(e.target.value) || 0;
        this.applyTheme();
      };
      topSpacing.onchange = () => {
        this.saveConfig();
      };
    }
    const topSize = document.getElementById("ui-top-size");
    if (topSize) {
      topSize.oninput = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.size = parseInt(e.target.value) || 14;
        this.applyTheme();
      };
      topSize.onchange = () => {
        this.saveConfig();
      };
    }
    const topOpacity = document.getElementById("ui-top-opacity");
    if (topOpacity) {
      topOpacity.oninput = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.opacity = parseFloat(e.target.value) || 0.9;
        this.applyTheme();
      };
      topOpacity.onchange = () => {
        this.saveConfig();
      };
    }
    const topMask = document.getElementById("ui-top-mask");
    if (topMask) {
      topMask.oninput = (e) => {
        if (!this.config.topMarquee) this.config.topMarquee = {};
        this.config.topMarquee.maskOpacity = parseFloat(e.target.value) || 0;
        this.applyTheme();
      };
      topMask.onchange = () => {
        this.saveConfig();
      };
    }

    // 底部滚动字幕联动 + 固化
    const botEn = document.getElementById("ui-bot-en");
    if (botEn) {
      botEn.onchange = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.enabled = e.target.checked;
        this.applyTheme();
        this.saveConfig();
        NeriModal.toast(this.config.bottomMarquee.enabled ? "底部字幕已开启并固化" : "底部字幕已关闭并固化");
      };
    }
    const botText = document.getElementById("ui-bot-text");
    if (botText) {
      botText.oninput = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.text = e.target.value;
        this.applyTheme();
      };
      botText.onchange = () => {
        this.saveConfig();
      };
    }
    const botDelim = document.getElementById("ui-bot-delimiter");
    if (botDelim) {
      botDelim.oninput = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.delimiter = e.target.value;
        this.applyTheme();
      };
      botDelim.onchange = () => {
        this.saveConfig();
      };
    }
    const botSpacing = document.getElementById("ui-bot-spacing");
    if (botSpacing) {
      botSpacing.oninput = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.spacing = parseInt(e.target.value) || 0;
        this.applyTheme();
      };
      botSpacing.onchange = () => {
        this.saveConfig();
      };
    }
    const botSize = document.getElementById("ui-bot-size");
    if (botSize) {
      botSize.oninput = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.size = parseInt(e.target.value) || 12;
        this.applyTheme();
      };
      botSize.onchange = () => {
        this.saveConfig();
      };
    }
    const botOpacity = document.getElementById("ui-bot-opacity");
    if (botOpacity) {
      botOpacity.oninput = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.opacity = parseFloat(e.target.value) || 0.75;
        this.applyTheme();
      };
      botOpacity.onchange = () => {
        this.saveConfig();
      };
    }
    const botMask = document.getElementById("ui-bot-mask");
    if (botMask) {
      botMask.oninput = (e) => {
        if (!this.config.bottomMarquee) this.config.bottomMarquee = {};
        this.config.bottomMarquee.maskOpacity = parseFloat(e.target.value) || 0;
        this.applyTheme();
      };
      botMask.onchange = () => {
        this.saveConfig();
      };
    }

    // 保存按钮（全量读取并覆盖写入）
    const saveBtn = document.getElementById("btn-save-ui-all");
    if (saveBtn) {
      saveBtn.onclick = () => {
        this.config.themeMode = document.getElementById("ui-theme").value;
        this.config.panelBlur = parseInt(document.getElementById("ui-blur-range").value) || 0;
        this.config.panelOpacity = parseFloat(document.getElementById("ui-opacity-range").value);
        this.config.tabAnimDuration = parseFloat(document.getElementById("ui-anim-range").value) || 0.45;

        this.config.mouseFx = {
          enabled: document.getElementById("ui-fx-enabled").checked,
          trailStyle: document.getElementById("ui-fx-trail-style").value,
          clickStyle: document.getElementById("ui-fx-click-style").value,
          decayRate: parseFloat(document.getElementById("ui-fx-decay").value) || 0.012,
          particleSize: parseInt(document.getElementById("ui-fx-size").value) || 5
        };

        const topDelimVal = document.getElementById("ui-top-delimiter")?.value;
        const topSpacingVal = parseInt(document.getElementById("ui-top-spacing")?.value);
        this.config.topMarquee = {
          enabled: document.getElementById("ui-top-en").checked,
          text: document.getElementById("ui-top-text").value,
          delimiter: topDelimVal !== undefined ? topDelimVal : "---",
          spacing: !isNaN(topSpacingVal) ? topSpacingVal : 16,
          size: parseInt(document.getElementById("ui-top-size").value) || 14,
          opacity: parseFloat(document.getElementById("ui-top-opacity").value) || 0.9,
          maskOpacity: parseFloat(document.getElementById("ui-top-mask").value) || 0
        };

        const botDelimVal = document.getElementById("ui-bot-delimiter")?.value;
        const botSpacingVal = parseInt(document.getElementById("ui-bot-spacing")?.value);
        this.config.bottomMarquee = {
          enabled: document.getElementById("ui-bot-en").checked,
          text: document.getElementById("ui-bot-text").value,
          delimiter: botDelimVal !== undefined ? botDelimVal : "---",
          spacing: !isNaN(botSpacingVal) ? botSpacingVal : 12,
          size: parseInt(document.getElementById("ui-bot-size").value) || 12,
          opacity: parseFloat(document.getElementById("ui-bot-opacity").value) || 0.75,
          maskOpacity: parseFloat(document.getElementById("ui-bot-mask").value) || 0
        };

        this.saveConfig();
        this.applyTheme();
        this.renderWallpaperList();
        this.renderPlaylist();
        NeriModal.toast("✨ 全部视觉偏好配置已保存！");
      };
    }
  },

  // 双轨文件上传：优先服务端持久化，降级 IndexedDB 永久本地存储
  async uploadAsset(file, customId) {
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/ui/upload", {
        method: "POST",
        body: fd
      });
      if (res.ok) {
        const data = await res.json();
        return { url: data.url, idbId: null };
      }
    } catch (e) {}

    // 服务端未就绪时，固化存入 IndexedDB 数据库
    const idbId = customId || `idb_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    await NeriDB.set(idbId, file);
    return { url: URL.createObjectURL(file), idbId: idbId };
  },

  injectMarquees() {
    let mt = document.getElementById("marquee-top");
    const header = document.querySelector("header");
    if (!mt) {
      mt = document.createElement("div");
      mt.id = "marquee-top";
      mt.className = "marquee-container marquee-top";
      if (header && header.parentNode) {
        header.parentNode.insertBefore(mt, header.nextSibling);
      } else {
        document.body.appendChild(mt);
      }
    } else if (header && mt.previousElementSibling !== header && header.parentNode) {
      header.parentNode.insertBefore(mt, header.nextSibling);
    }

    let mb = document.getElementById("marquee-bottom");
    if (!mb) {
      mb = document.createElement("div");
      mb.id = "marquee-bottom";
      mb.className = "marquee-container marquee-bottom";
      document.body.appendChild(mb);
    }
  },

  injectMusicPlayer() {
    if (document.getElementById("neri-music-player")) return;

    const currentTrack = this.getCurrentTrack();
    this.audioObj = new Audio(currentTrack ? currentTrack.url : "");
    this.audioObj.loop = false;

    this.audioObj.onended = () => {
      this.nextTrack(true);
    };

    const player = document.createElement("div");
    player.id = "neri-music-player";
    player.innerHTML = `
      <div class="cd-spin" id="player-cd">
        <img src="/static/img/avatar.png" class="w-full h-full object-cover select-none pointer-events-none" />
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <button class="player-ctrl-btn" id="btn-player-prev" title="上一首">
          <i class="fa-solid fa-backward-step"></i>
        </button>
        
        <button class="player-ctrl-btn player-btn-main" id="btn-play-pause" title="播放/暂停">
          <i class="fa-solid fa-play ml-0.5"></i>
        </button>
        
        <button class="player-ctrl-btn" id="btn-player-next" title="下一首">
          <i class="fa-solid fa-forward-step"></i>
        </button>

        <button class="player-ctrl-btn" id="btn-player-mode" title="循环模式">
          <i class="fa-solid fa-repeat"></i>
        </button>
      </div>

      <div class="flex flex-col justify-center select-none overflow-hidden min-w-[70px] max-w-[140px] pl-1">
        <span class="text-[12px] truncate font-bold" id="player-song-title">${currentTrack ? currentTrack.name : 'None'}</span>
        <span class="text-[9px] -mt-0.5 truncate opacity-75 font-semibold" id="player-song-sub">${currentTrack ? '列表循环' : 'No Audio'}</span>
      </div>
    `;
    document.body.appendChild(player);

    const btnPlay = document.getElementById("btn-play-pause");
    const btnPrev = document.getElementById("btn-player-prev");
    const btnNext = document.getElementById("btn-player-next");
    const btnMode = document.getElementById("btn-player-mode");
    const cd = document.getElementById("player-cd");

    btnPlay.onclick = (e) => {
      e.stopPropagation();
      const track = this.getCurrentTrack();
      if (!track || !track.url) {
        NeriModal.toast("当前歌单中暂无音乐，请先在设置中添加曲目");
        return;
      }

      if (this.isPlaying) {
        this.audioObj.pause();
        this.isPlaying = false;
        btnPlay.innerHTML = '<i class="fa-solid fa-play ml-0.5"></i>';
        cd.classList.remove("playing");
      } else {
        this.audioObj.play().then(() => {
          this.isPlaying = true;
          btnPlay.innerHTML = '<i class="fa-solid fa-pause"></i>';
          cd.classList.add("playing");
        }).catch(err => {
          console.warn("Audio play blocked", err);
          NeriModal.toast("无法播放音频，请检查音频文件格式或直链有效性");
        });
      }
    };

    btnPrev.onclick = (e) => {
      e.stopPropagation();
      this.prevTrack();
    };

    btnNext.onclick = (e) => {
      e.stopPropagation();
      this.nextTrack(false);
    };

    btnMode.onclick = (e) => {
      e.stopPropagation();
      this.togglePlayMode();
    };

    let isDragging = false, currentX = 0, currentY = 0, initialX = 0, initialY = 0, xOffset = 0, yOffset = 0;
    player.addEventListener("mousedown", (e) => {
      if (e.target.closest('.player-ctrl-btn')) return;
      initialX = e.clientX - xOffset;
      initialY = e.clientY - yOffset;
      isDragging = true;
    });

    document.addEventListener("mouseup", () => {
      isDragging = false;
    });

    document.addEventListener("mousemove", (e) => {
      if (isDragging) {
        e.preventDefault();
        currentX = e.clientX - initialX;
        currentY = e.clientY - initialY;
        xOffset = currentX;
        yOffset = currentY;
        player.style.transform = `translate(${currentX}px, ${currentY}px)`;
      }
    });

    this.updatePlayerDisplay();
  },

  initMouseFx() {
    if (document.getElementById("neri-fx-canvas")) return;

    this.fxCanvas = document.createElement("canvas");
    this.fxCanvas.id = "neri-fx-canvas";
    document.body.appendChild(this.fxCanvas);
    this.fxCtx = this.fxCanvas.getContext("2d");

    const resize = () => {
      this.fxCanvas.width = window.innerWidth;
      this.fxCanvas.height = window.innerHeight;
    };
    window.addEventListener("resize", resize);
    resize();

    window.addEventListener("mousemove", (e) => {
      const fx = this.config.mouseFx || {};
      if (!fx.enabled) return;

      const style = fx.trailStyle || "sakura";
      const baseSize = fx.particleSize || 5;

      this.particles.push({
        x: e.clientX,
        y: e.clientY,
        vx: (Math.random() - 0.5) * 1.5,
        vy: (Math.random() - 0.5) * 1.5 - 0.6,
        size: Math.random() * baseSize + (baseSize * 0.7),
        rotation: Math.random() * Math.PI * 2,
        vRot: (Math.random() - 0.5) * 0.08,
        alpha: 0.95,
        style: style,
        color: Math.random() > 0.4 ? "rgba(184, 150, 199," : "rgba(227, 95, 106,"
      });
    });

    window.addEventListener("mousedown", (e) => {
      const fx = this.config.mouseFx || {};
      if (!fx.enabled) return;

      const clickStyle = fx.clickStyle || "bloom";
      const count = clickStyle === "ripple" ? 3 : 18;

      for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 / count) * i + (Math.random() * 0.2);
        const speed = Math.random() * 3.5 + 2;
        this.bursts.push({
          x: e.clientX,
          y: e.clientY,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          radius: 2,
          maxRadius: Math.random() * 45 + 30,
          size: Math.random() * 6 + 4,
          rotation: Math.random() * Math.PI * 2,
          vRot: (Math.random() - 0.5) * 0.1,
          alpha: 1.0,
          clickStyle: clickStyle,
          color: i % 2 === 0 ? "rgba(156, 107, 158," : "rgba(216, 112, 147,"
        });
      }
    });

    const render = () => {
      this.fxCtx.clearRect(0, 0, this.fxCanvas.width, this.fxCanvas.height);

      const fx = this.config.mouseFx || {};
      if (fx.enabled) {
        const decay = fx.decayRate || 0.012;

        for (let i = this.particles.length - 1; i >= 0; i--) {
          const p = this.particles[i];
          p.x += p.vx;
          p.y += p.vy;
          p.rotation += p.vRot;
          p.alpha -= decay;
          p.size *= 0.988;

          if (p.alpha <= 0 || p.size <= 0.6) {
            this.particles.splice(i, 1);
            continue;
          }

          this.fxCtx.save();
          this.fxCtx.translate(p.x, p.y);
          this.fxCtx.rotate(p.rotation);

          if (p.style === "sakura") {
            this.fxCtx.fillStyle = `rgba(227, 120, 140, ${p.alpha})`;
            this.fxCtx.beginPath();
            this.fxCtx.moveTo(0, 0);
            this.fxCtx.bezierCurveTo(-p.size, -p.size, -p.size * 1.5, p.size / 2, 0, p.size * 1.8);
            this.fxCtx.bezierCurveTo(p.size * 1.5, p.size / 2, p.size, -p.size, 0, 0);
            this.fxCtx.fill();
          } else if (p.style === "stardust") {
            this.fxCtx.fillStyle = `${p.color}${p.alpha})`;
            this.fxCtx.beginPath();
            for (let s = 0; s < 4; s++) {
              this.fxCtx.lineTo(Math.cos(s * Math.PI / 2) * p.size, Math.sin(s * Math.PI / 2) * p.size);
              this.fxCtx.lineTo(Math.cos(s * Math.PI / 2 + Math.PI / 4) * (p.size * 0.35), Math.sin(s * Math.PI / 2 + Math.PI / 4) * (p.size * 0.35));
            }
            this.fxCtx.closePath();
            this.fxCtx.fill();
          } else {
            const grad = this.fxCtx.createRadialGradient(0, 0, 0, 0, 0, p.size);
            grad.addColorStop(0, `${p.color}${p.alpha})`);
            grad.addColorStop(1, `${p.color}0)`);
            this.fxCtx.fillStyle = grad;
            this.fxCtx.beginPath();
            this.fxCtx.arc(0, 0, p.size, 0, Math.PI * 2);
            this.fxCtx.fill();
          }

          this.fxCtx.restore();
        }

        for (let i = this.bursts.length - 1; i >= 0; i--) {
          const b = this.bursts[i];
          b.alpha -= 0.022;

          if (b.clickStyle === "ripple") {
            b.radius += 2.5;
            if (b.alpha <= 0 || b.radius >= b.maxRadius) {
              this.bursts.splice(i, 1);
              continue;
            }
            this.fxCtx.strokeStyle = `rgba(184, 150, 199, ${b.alpha * 0.8})`;
            this.fxCtx.lineWidth = 2.5;
            this.fxCtx.beginPath();
            this.fxCtx.arc(b.x, b.y, b.radius, 0, Math.PI * 2);
            this.fxCtx.stroke();
          } else {
            b.x += b.vx;
            b.y += b.vy;
            b.vx *= 0.94;
            b.vy *= 0.94;
            b.size *= 0.96;
            b.rotation += b.vRot;

            if (b.alpha <= 0 || b.size <= 0.6) {
              this.bursts.splice(i, 1);
              continue;
            }

            this.fxCtx.save();
            this.fxCtx.translate(b.x, b.y);
            this.fxCtx.rotate(b.rotation);
            this.fxCtx.fillStyle = `${b.color}${b.alpha})`;
            this.fxCtx.beginPath();
            this.fxCtx.arc(0, 0, b.size, 0, Math.PI * 2);
            this.fxCtx.fill();
            this.fxCtx.restore();
          }
        }
      }

      requestAnimationFrame(render);
    };

    requestAnimationFrame(render);
  }
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    setTimeout(() => NeriTheme.init(), 150);
  });
} else {
  setTimeout(() => NeriTheme.init(), 150);
}
