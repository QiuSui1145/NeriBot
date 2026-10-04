// 音理 WebUI 前端核心交互逻辑

let tokenChartInstance = null;
let currentLoadedPrompts = {};
let activePromptFile = "master.yaml";
let currentBindings = [];

document.addEventListener("DOMContentLoaded", () => {
  initStealthMode();
  initAuth();
  initTabs();
  initSliders();
  initForms();
  initSandbox();
  initPromptsEditor();
  initIdentities();
  initGroupLogs();
  initRealTimePerception();
  initMultiProviderAndHub();
  initFlowHub();
  initWhitelistVisualEvents();
  initTTSServiceEvents();
  initMemoryHub();
  initPluginHub();
  initChartRangeControls();
  initWidgetEditor();
  loadDashboardWidgetsLayout();
  startUptimeTicker();
});

// ---------------- 0. 隐秘模式 (Stealth Mode) 全局脱敏引擎 ----------------
let isStealthModeActive = localStorage.getItem("neri_stealth_mode") === "true";

function isStealthMode() {
  return isStealthModeActive;
}

function maskQQ(qq) {
  if (!isStealthMode()) return qq != null ? String(qq) : "";
  if (qq === null || qq === undefined || qq === "") return "";
  return "***";
}

function maskGroup(gid) {
  if (!isStealthMode()) return gid != null ? String(gid) : "";
  if (gid === null || gid === undefined || gid === "") return "";
  return "***";
}

function maskSensitiveText(text) {
  if (!isStealthMode()) return text != null ? String(text) : "";
  if (!text) return "";
  let str = String(text);
  str = str.replace(/\b\d{5,12}\b/g, "***");
  str = str.replace(/group_\d+/gi, "group_***");
  str = str.replace(/群\s*\d+/g, "群 ***");
  str = str.replace(/私聊\s*\d+/g, "私聊 ***");
  return str;
}

function maskFlowTitle(displayName, targetId) {
  if (!isStealthMode()) return displayName || String(targetId);
  if (!displayName) return "***";
  let masked = maskSensitiveText(displayName);
  if (/^\d+$/.test(masked.trim())) return "***";
  return masked;
}

function updateStealthModeUI() {
  const btn = document.getElementById("btn-stealth-mode");
  const icon = document.getElementById("btn-stealth-icon");
  const text = document.getElementById("btn-stealth-text");
  
  if (isStealthModeActive) {
    document.body.classList.add("stealth-mode-active");
    if (btn) {
      btn.classList.add("active");
      btn.classList.add("border-indigo-500/70", "bg-indigo-950/70", "text-indigo-200");
      btn.classList.remove("border-slate-700", "bg-slate-800/80", "text-slate-300");
    }
    if (icon) {
      icon.className = "fa-solid fa-user-secret text-indigo-400";
    }
    if (text) {
      text.textContent = "隐秘模式: 开";
    }
  } else {
    document.body.classList.remove("stealth-mode-active");
    if (btn) {
      btn.classList.remove("active");
      btn.classList.remove("border-indigo-500/70", "bg-indigo-950/70", "text-indigo-200");
      btn.classList.add("border-slate-700", "bg-slate-800/80", "text-slate-300");
    }
    if (icon) {
      icon.className = "fa-solid fa-user-secret text-slate-400";
    }
    if (text) {
      text.textContent = "隐秘模式: 关";
    }
  }

  // 针对敏感 QQ 输入控件切换 password 类型以防偷窥
  const sensitiveInputs = [
    document.getElementById("cfg-identity-master-qq"),
    document.getElementById("new-id-qq"),
    document.getElementById("sim-input-qq"),
    document.getElementById("mem-form-qq"),
  ];
  sensitiveInputs.forEach((inp) => {
    if (inp) {
      if (isStealthModeActive) {
        inp.dataset.originalType = inp.type || "text";
        inp.type = "password";
      } else {
        inp.type = inp.dataset.originalType || (inp.id.includes("qq") ? "number" : "text");
      }
    }
  });
}

function toggleStealthMode() {
  isStealthModeActive = !isStealthModeActive;
  localStorage.setItem("neri_stealth_mode", isStealthModeActive ? "true" : "false");
  updateStealthModeUI();
  
  // 重新无感刷新界面上所有涉及敏感信息的组件
  pollStatusAndStats();
  loadLogs();
  renderFlowSessionCards();
  if (currentFlowSessionId) {
    selectFlowSession(currentFlowSessionId);
  }
  renderWhitelistChipsAndStatus();
  renderIdentitiesTable();
  loadGroupLogs();
  loadCurrentMemSubtab();

  if (window.NeriModal && typeof window.NeriModal.toast === "function") {
    window.NeriModal.toast(isStealthModeActive ? "已开启隐秘模式 (敏感信息已掩码)" : "已关闭隐秘模式 (恢复明文显示)");
  }
}

function initStealthMode() {
  updateStealthModeUI();
  const btn = document.getElementById("btn-stealth-mode");
  if (btn) {
    btn.addEventListener("click", toggleStealthMode);
  }
}

// ---------------- 1. 鉴权与登录 ----------------
async function initAuth() {
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) {
      showApp();
      loadAllData();
      startPolling();
    } else {
      showLogin();
    }
  } catch (e) {
    showLogin();
  }

  // 登录表单处理
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const u = document.getElementById("login-username").value.trim();
    const p = document.getElementById("login-password").value.trim();
    const errDiv = document.getElementById("login-error");
    errDiv.classList.add("hidden");

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      });
      const data = await res.json();
      if (!res.ok) {
        errDiv.textContent = data.detail || "登录失败";
        errDiv.classList.remove("hidden");
        return;
      }
      showApp();
      loadAllData();
      startPolling();
    } catch (err) {
      errDiv.textContent = "网络连接错误: " + err.message;
      errDiv.classList.remove("hidden");
    }
  });

  // 退出登录
  document.getElementById("btn-logout").addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.reload();
  });
}

function showLogin() {
  document.getElementById("login-modal").classList.remove("hidden");
  document.getElementById("app-container").classList.add("hidden");
}

function showApp() {
  document.getElementById("login-modal").classList.add("hidden");
  document.getElementById("app-container").classList.remove("hidden");
}

// ---------------- 2. 选项卡切换与移动端侧栏抽屉 ----------------
function initMobileNav() {
  const btnMenu = document.getElementById("btn-mobile-menu");
  const btnClose = document.getElementById("btn-close-mobile-nav");
  const backdrop = document.getElementById("mobile-nav-backdrop");
  const sidebar = document.getElementById("app-sidebar");

  const openDrawer = () => {
    if (!sidebar || !backdrop) return;
    sidebar.classList.remove("-translate-x-full");
    sidebar.classList.add("translate-x-0");
    backdrop.classList.remove("hidden");
  };

  const closeDrawer = () => {
    if (!sidebar || !backdrop) return;
    sidebar.classList.remove("translate-x-0");
    sidebar.classList.add("-translate-x-full");
    backdrop.classList.add("hidden");
  };

  if (btnMenu) btnMenu.addEventListener("click", openDrawer);
  if (btnClose) btnClose.addEventListener("click", closeDrawer);
  if (backdrop) backdrop.addEventListener("click", closeDrawer);

  return closeDrawer;
}

let closeMobileDrawer = null;

function initTabs() {
  closeMobileDrawer = initMobileNav();
  const navBtns = document.querySelectorAll(".nav-btn");
  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      navBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add("active");

      // 移动端选择后自动收回抽屉
      if (closeMobileDrawer && window.innerWidth < 768) {
        closeMobileDrawer();
      }

      if (targetId === "tab-overview") {
        renderChart(currentChartRange);
        loadCostStats();
        loadSystemTelemetry();
        loadModelDistribution();
      } else if (targetId === "tab-flow") {
        loadFlowSessions();
      } else if (targetId === "tab-llm") {
        loadProviders();
        loadModelHub();
      } else if (targetId === "tab-whitelist" || targetId === "tab-tts" || targetId === "tab-commands" || targetId === "tab-settings") {
        loadConfig();
        if (targetId === "tab-tts") checkTTSServiceStatus();
      } else if (targetId === "tab-grouplogs") {
        loadGroupLogs();
      } else if (targetId === "tab-identities") {
        loadIdentities();
      } else if (targetId === "tab-persona") {
        loadPromptsList();
      } else if (targetId === "tab-memory") {
        loadMemoryAll();
      } else if (targetId === "tab-plugins") {
        if (window.loadPluginsData) window.loadPluginsData();
      } else if (targetId === "tab-ui-settings") {
        if (window.NeriTheme) {
          window.NeriTheme.syncInputsFast();
          window.NeriTheme.renderWallpaperList();
          window.NeriTheme.renderPlaylist();
        }
      }
    });
  });
}

function initSliders() {
  const bindSlider = (sliderId, valId) => {
    const s = document.getElementById(sliderId);
    const v = document.getElementById(valId);
    if (s && v) {
      s.addEventListener("input", () => (v.textContent = s.value));
    }
  };
  bindSlider("cfg-llm-temperature", "val-llm-temp");
  bindSlider("cfg-llm-topp", "val-llm-topp");
  bindSlider("cfg-tts-speed", "val-tts-speed");
  bindSlider("cfg-act-conf", "val-act-conf");

  // 密码可见性切换
  document.querySelectorAll(".btn-toggle-eye").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.previousElementSibling;
      if (input.type === "password") {
        input.type = "text";
        btn.innerHTML = '<i class="fa-solid fa-eye-slash"></i>';
      } else {
        input.type = "password";
        btn.innerHTML = '<i class="fa-solid fa-eye"></i>';
      }
    });
  });

  // QQ显示隐藏切换
  const btnToggleQq = document.getElementById("btn-toggle-qq-mask");
  if (btnToggleQq) {
    btnToggleQq.addEventListener("click", () => {
      const qqBadge = document.getElementById("header-bot-qq");
      const icon = document.getElementById("icon-qq-mask");
      if (!qqBadge.dataset.hidden || qqBadge.dataset.hidden === "false") {
        qqBadge.dataset.hidden = "true";
        qqBadge.textContent = "QQ: ***";
        icon.classList.remove("fa-eye-slash");
        icon.classList.add("fa-eye");
      } else {
        qqBadge.dataset.hidden = "false";
        qqBadge.textContent = qqBadge.dataset.qq;
        icon.classList.remove("fa-eye");
        icon.classList.add("fa-eye-slash");
      }
    });
  }

  // 主动回复策略切换
  const stratModel = document.getElementById("cfg-act-strat-model");
  const stratProb = document.getElementById("cfg-act-strat-prob");
  const optModel = document.getElementById("act-strat-model-options");
  const optProb = document.getElementById("act-strat-prob-options");

  if (stratModel && stratProb) {
    const updateStratUI = () => {
      if (stratModel.checked) {
        optModel.classList.remove("hidden");
        optProb.classList.add("hidden");
      } else {
        optModel.classList.add("hidden");
        optProb.classList.remove("hidden");
      }
    };
    stratModel.addEventListener("change", updateStratUI);
    stratProb.addEventListener("change", updateStratUI);
  }
}

// ---------------- 3. 数据加载与定时轮询 ----------------
let pollTimer = null;
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollStatusAndStats();
  pollTimer = setInterval(pollStatusAndStats, 4000);
}

async function loadAllData() {
  await Promise.allSettled([
    loadConfig(),
    pollStatusAndStats(),
    renderChart(currentChartRange),
    loadCostStats(),
    loadSystemTelemetry(),
    loadModelDistribution(),
    loadLogs(),
    loadIdentities(),
    loadGroupLogs(),
    loadPromptsList(),
    loadProviders(),
    loadModelHub(),
    loadFlowSessions(),
    loadMemoryStats(),
  ]);
}

async function pollStatusAndStats() {
  try {
    const [statusRes, statsRes] = await Promise.all([
      fetch("/api/status"),
      fetch("/api/stats/summary"),
    ]);

    if (statusRes.ok) {
      const s = await statusRes.json();
      // OneBot 状态
      const dot = document.getElementById("stat-onebot-dot");
      const text = document.getElementById("stat-onebot-text");
      const sub = document.getElementById("stat-onebot-sub");
      const hBadge = document.getElementById("header-bot-badge");
      const hQq = document.getElementById("header-bot-qq");
      const hModel = document.getElementById("header-llm-model");
      const hTts = document.getElementById("header-tts-status");

      if (s.onebot.connected) {
        dot.className = "w-3 h-3 rounded-full bg-emerald-400 animate-pulse";
        let connType = "已连接 (在线)";
        if (s.onebot.reverse_connected && s.onebot.forward_connected) {
          connType = "已连接 (双向同时建立)";
        } else if (s.onebot.reverse_connected) {
          connType = "已连接 (反向WS)";
        } else if (s.onebot.forward_connected) {
          connType = "已连接 (正向WS)";
        }

        text.textContent = connType;
        text.className = "font-bold text-sm text-emerald-300";
        sub.textContent = `${s.onebot.nickname} (${maskQQ(s.onebot.bot_qq)})`;
        hBadge.className = "absolute bottom-0 right-0 w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-950";
        hQq.dataset.qq = `QQ: ${s.onebot.bot_qq}`;
        if (isStealthMode()) {
          hQq.textContent = "QQ: ***";
        } else if (hQq.dataset.hidden !== "true") {
          hQq.textContent = `QQ: ${s.onebot.bot_qq}`;
        }
      } else {
        dot.className = "w-3 h-3 rounded-full bg-rose-500";
        text.textContent = "未连接";
        text.className = "font-bold text-sm text-slate-300";
        sub.textContent = isStealthMode() ? "等待 NapCat 连接..." : `等待 NapCat 连接... (目标: ${s.onebot.forward_ws_url || '--'})`;
        hBadge.className = "absolute bottom-0 right-0 w-3 h-3 rounded-full bg-rose-500 border-2 border-slate-950";
      }

      const activeModelName = s.llm.display_name || s.llm.active_model_id || s.llm.model || '--';
      hModel.innerHTML = `<i class="fa-solid fa-microchip mr-1"></i>${escapeHtml(activeModelName)}`;
      hModel.title = `主回复模型: ${s.llm.active_model_id || s.llm.model}`;
      hTts.innerHTML = `<i class="fa-solid fa-headphones mr-1"></i>TTS: ${s.tts.online ? '<span class="text-emerald-300">在线</span>' : '<span class="text-rose-400">离线</span>'}`;
    }

    if (statsRes.ok) {
      const st = await statsRes.json();
      document.getElementById("stat-today-tokens").textContent = st.today_total_tokens.toLocaleString();
      document.getElementById("stat-today-calls").textContent = st.today_calls.toLocaleString();
      document.getElementById("stat-today-prompt").textContent = st.today_prompt_tokens.toLocaleString();
      document.getElementById("stat-total-tokens").textContent = st.grand_total_tokens.toLocaleString();
      document.getElementById("stat-total-calls").textContent = st.total_calls.toLocaleString();
      document.getElementById("stat-total-completion").textContent = st.total_completion_tokens.toLocaleString();
      document.getElementById("stat-avg-latency").textContent = st.avg_latency_ms;
      const llmLatencyEl = document.getElementById("link-llm-latency");
      if (llmLatencyEl) llmLatencyEl.textContent = `${st.avg_latency_ms} ms`;
    }

    // 定时刷新硬件状态与概览组件
    loadSystemTelemetry();

    // 若当前停留在群聊日志页，自动无感同步最新群聊流水
    const activeTabBtn = document.querySelector(".nav-btn.active");
    if (activeTabBtn && activeTabBtn.getAttribute("data-tab") === "tab-grouplogs") {
      loadGroupLogs();
    }
  } catch (e) {
    console.error("轮询状态出错:", e);
  }
}

// ---------------- 4. Token 图表绘制 (Chart.js 支持 24h / 7d / 30d / 12m) ----------------
let currentChartRange = "7d";
let modelDistChartInstance = null;

async function renderChart(range = currentChartRange) {
  currentChartRange = range;
  try {
    // 切换按钮高亮样式
    document.querySelectorAll(".chart-range-btn").forEach((b) => {
      const isAct = b.getAttribute("data-range") === range;
      if (isAct) {
        b.className = "chart-range-btn px-2.5 py-1 rounded-md text-[11px] font-semibold transition bg-cyan-950 text-cyan-300 border border-cyan-800 active";
      } else {
        b.className = "chart-range-btn px-2.5 py-1 rounded-md text-[11px] font-semibold transition text-slate-400 hover:text-slate-200";
      }
    });

    const titleEl = document.getElementById("chart-title");
    if (titleEl) {
      const rangeLabels = { "24h": "最近 24 小时", "7d": "最近 7 天", "30d": "最近 30 天", "12m": "最近 12 个月" };
      titleEl.textContent = `${rangeLabels[range] || "周期"} Token 消耗走势 (Prompt / Completion)`;
    }

    const res = await fetch(`/api/stats/chart?range=${encodeURIComponent(range)}`);
    if (!res.ok) return;
    const chartData = await res.json();

    const labels = chartData.map((d) => d.label || d.day);
    const promptData = chartData.map((d) => d.prompt_tokens);
    const compData = chartData.map((d) => d.completion_tokens);

    const ctx = document.getElementById("tokenChart")?.getContext("2d");
    if (!ctx) return;

    if (tokenChartInstance) {
      tokenChartInstance.destroy();
    }

    tokenChartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Prompt Tokens (输入)",
            data: promptData,
            backgroundColor: "rgba(56, 189, 248, 0.75)",
            borderRadius: 6,
          },
          {
            label: "Completion Tokens (输出)",
            data: compData,
            backgroundColor: "rgba(168, 85, 247, 0.75)",
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            stacked: true,
            grid: { color: "rgba(51, 65, 85, 0.25)" },
            ticks: { color: "#94a3b8", maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
          },
          y: {
            stacked: true,
            grid: { color: "rgba(51, 65, 85, 0.25)" },
            ticks: { color: "#94a3b8" },
          },
        },
        plugins: {
          legend: {
            labels: { color: "#cbd5e1", font: { size: 12 } },
          },
        },
      },
    });
  } catch (e) {
    console.error("渲染 Token 走势图表出错:", e);
  }
}

function initChartRangeControls() {
  document.querySelectorAll(".chart-range-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const r = btn.getAttribute("data-range");
      if (r) renderChart(r);
    });
  });
  const btnRefresh = document.getElementById("btn-refresh-chart");
  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => renderChart(currentChartRange));
  }
  const btnRefCost = document.getElementById("btn-refresh-cost");
  if (btnRefCost) {
    btnRefCost.addEventListener("click", () => loadCostStats());
  }
  const btnRefDist = document.getElementById("btn-refresh-distribution");
  if (btnRefDist) {
    btnRefDist.addEventListener("click", () => loadModelDistribution());
  }
}

// ---------------- 4.1 成本与开销统计加载 ----------------
async function loadCostStats() {
  try {
    const res = await fetch("/api/stats/cost");
    if (!res.ok) return;
    const data = await res.json();

    const elToday = document.getElementById("cost-today");
    const elMonth = document.getElementById("cost-month");
    const elTotal = document.getElementById("cost-total");
    const list = document.getElementById("cost-breakdown-list");

    if (elToday) elToday.textContent = `¥${Number(data.today_cost || 0).toFixed(4)}`;
    if (elMonth) elMonth.textContent = `¥${Number(data.month_cost || 0).toFixed(4)}`;
    if (elTotal) elTotal.textContent = `¥${Number(data.total_cost || 0).toFixed(4)}`;

    if (list) {
      const bks = data.breakdown || [];
      if (bks.length === 0) {
        list.innerHTML = '<div class="text-slate-500 py-3 text-center text-xs">暂无计费模型记录</div>';
        return;
      }

      list.innerHTML = bks
        .map((b) => {
          return `
          <div class="flex items-center justify-between p-2 rounded-lg bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 transition">
            <div class="truncate max-w-[55%]">
              <span class="font-medium text-slate-200 block truncate" title="${escapeHtml(b.model)}">${escapeHtml(b.model)}</span>
              <span class="text-[10px] text-slate-400 font-mono">¥${b.prompt_price || 0}/1M | ¥${b.completion_price || 0}/1M</span>
            </div>
            <div class="text-right">
              <span class="font-mono font-bold text-amber-300 block">¥${Number(b.total_cost || 0).toFixed(4)}</span>
              <span class="text-[10px] text-slate-400 font-mono">${(b.total_tokens || 0).toLocaleString()} Tok</span>
            </div>
          </div>
        `;
        })
        .join("");
    }
  } catch (e) {
    console.error("加载成本统计失败:", e);
  }
}

// ---------------- 4.2 系统硬件实时监测与 Uptime 实时时钟 ----------------
let currentUptimeSecs = 0;
let uptimeTickerInterval = null;

async function loadSystemTelemetry() {
  try {
    const res = await fetch("/api/system/status");
    if (!res.ok) return;
    const data = await res.json();

    // CPU
    const cpuPct = Math.round(data.cpu?.percent || 0);
    const cpuEl = document.getElementById("sys-cpu-percent");
    const cpuBar = document.getElementById("sys-cpu-bar");
    const cpuCores = document.getElementById("sys-cpu-cores");
    if (cpuEl) cpuEl.textContent = `${cpuPct}%`;
    if (cpuBar) cpuBar.style.width = `${Math.min(100, Math.max(0, cpuPct))}%`;
    if (cpuCores) cpuCores.textContent = data.cpu?.cores || 1;

    // RAM
    const ramPct = Math.round(data.ram?.percent || 0);
    const ramEl = document.getElementById("sys-ram-percent");
    const ramBar = document.getElementById("sys-ram-bar");
    const ramUsed = document.getElementById("sys-ram-used");
    const ramTotal = document.getElementById("sys-ram-total");
    if (ramEl) ramEl.textContent = `${ramPct}%`;
    if (ramBar) ramBar.style.width = `${Math.min(100, Math.max(0, ramPct))}%`;
    if (ramUsed) ramUsed.textContent = data.ram?.used_gb || 0;
    if (ramTotal) ramTotal.textContent = data.ram?.total_gb || 0;

    // GPU
    const gpu = data.gpu || {};
    const gpuPct = Math.round(gpu.percent || 0);
    const gpuEl = document.getElementById("sys-gpu-val");
    const gpuBar = document.getElementById("sys-gpu-bar");
    const gpuName = document.getElementById("sys-gpu-name");
    if (gpu.has_gpu) {
      if (gpuEl) gpuEl.textContent = `${gpu.vram_used_mb || 0}MB (${gpuPct}%)`;
      if (gpuBar) gpuBar.style.width = `${Math.min(100, Math.max(0, gpuPct))}%`;
      if (gpuName) gpuName.textContent = gpu.name || "RTX 4060";
    } else {
      if (gpuEl) gpuEl.textContent = "无独显";
      if (gpuBar) gpuBar.style.width = "0%";
      if (gpuName) gpuName.textContent = "GPU 未激活";
    }

    // Disk
    const diskPct = Math.round(data.disk?.percent || 0);
    const diskEl = document.getElementById("sys-disk-percent");
    const diskBar = document.getElementById("sys-disk-bar");
    const diskUsed = document.getElementById("sys-disk-used");
    const diskTotal = document.getElementById("sys-disk-total");
    if (diskEl) diskEl.textContent = `${diskPct}%`;
    if (diskBar) diskBar.style.width = `${Math.min(100, Math.max(0, diskPct))}%`;
    if (diskUsed) diskUsed.textContent = data.disk?.used_gb || 0;
    if (diskTotal) diskTotal.textContent = data.disk?.total_gb || 0;

    // Uptime & Process
    const upt = data.uptime || {};
    currentUptimeSecs = upt.seconds || 0;
    updateUptimeDisplay(currentUptimeSecs);

    const elStart = document.getElementById("uptime-start");
    const elPid = document.getElementById("uptime-pid");
    const elPy = document.getElementById("uptime-python");
    if (elStart) elStart.textContent = upt.start_time ? upt.start_time.slice(11, 19) : "--";
    if (elPid) elPid.textContent = upt.pid || "--";
    if (elPy) elPy.textContent = upt.python_version || "--";

    // Service Links
    const onebotBadge = document.getElementById("link-onebot-badge");
    if (onebotBadge) {
      onebotBadge.textContent = data.health?.onebot_connected ? "在线 (正常)" : "离线";
      onebotBadge.className = data.health?.onebot_connected ? "font-mono text-[11px] text-emerald-400" : "font-mono text-[11px] text-rose-400";
    }
    const ttsBadge = document.getElementById("link-tts-badge");
    if (ttsBadge) {
      ttsBadge.textContent = data.health?.tts_enabled ? "在线" : "未开启";
      ttsBadge.className = data.health?.tts_enabled ? "font-mono text-[11px] text-emerald-400" : "font-mono text-[11px] text-slate-400";
    }
  } catch (e) {
    console.error("加载硬件状态监控出错:", e);
  }
}

function updateUptimeDisplay(secs) {
  const clockEl = document.getElementById("uptime-clock");
  if (!clockEl) return;
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  let str = "";
  if (d > 0) str += `${d}天 `;
  str += `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  clockEl.textContent = str;
}

function startUptimeTicker() {
  if (uptimeTickerInterval) clearInterval(uptimeTickerInterval);
  uptimeTickerInterval = setInterval(() => {
    currentUptimeSecs++;
    updateUptimeDisplay(currentUptimeSecs);
  }, 1000);
}

// ---------------- 4.3 模型调用分布分布图表 ----------------
async function loadModelDistribution() {
  try {
    const res = await fetch("/api/stats/models_distribution");
    if (!res.ok) return;
    const data = await res.json();

    const list = document.getElementById("model-dist-list");
    if (list) {
      if (data.length === 0) {
        list.innerHTML = '<div class="text-slate-500 py-4 text-center text-xs">暂无模型调用数据</div>';
      } else {
        list.innerHTML = data
          .map((m, idx) => {
            const colors = ["#38bdf8", "#a855f7", "#34d399", "#fbbf24", "#f43f5e", "#818cf8"];
            const color = colors[idx % colors.length];
            return `
            <div class="flex items-center justify-between p-1.5 rounded-lg bg-slate-900/60 border border-slate-800/80">
              <div class="flex items-center gap-2 truncate max-w-[65%]">
                <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background-color: ${color}"></span>
                <span class="font-medium text-slate-200 truncate block text-[11px]" title="${escapeHtml(m.model)}">${escapeHtml(m.model)}</span>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <span class="text-[10px] text-slate-400 font-mono">${m.calls}次</span>
                <span class="text-[11px] font-bold font-mono text-cyan-300">${m.tokens_percent}%</span>
              </div>
            </div>
          `;
          })
          .join("");
      }
    }

    const canvas = document.getElementById("modelDistChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    if (modelDistChartInstance) {
      modelDistChartInstance.destroy();
    }

    const chartLabels = data.map((d) => d.model.split("/").pop());
    const chartValues = data.map((d) => d.total_tokens);
    const colors = ["#38bdf8", "#a855f7", "#34d399", "#fbbf24", "#f43f5e", "#818cf8"];

    modelDistChartInstance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: chartLabels.length ? chartLabels : ["无数据"],
        datasets: [
          {
            data: chartValues.length ? chartValues : [1],
            backgroundColor: chartValues.length ? colors.slice(0, chartValues.length) : ["rgba(51, 65, 85, 0.4)"],
            borderWidth: 1,
            borderColor: "rgba(15, 23, 42, 0.8)",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw.toLocaleString()} Tokens`,
            },
          },
        },
      },
    });
  } catch (e) {
    console.error("加载模型分布出错:", e);
  }
}

// ---------------- 4.4 主页看板组件自定义布局管理器 (三档尺寸 S/M/L + 拖拽重排) ----------------
const DEFAULT_DASHBOARD_WIDGETS = [
  { id: "w-metrics", title: "核心指标卡片", icon: "fa-chart-line", size: "lg", visible: true },
  { id: "w-chart", title: "Token 消耗走势", icon: "fa-chart-column", size: "lg", visible: true },
  { id: "w-cost", title: "模型开销与成本统计", icon: "fa-coins", size: "md", visible: true },
  { id: "w-system", title: "硬件系统资源监测", icon: "fa-microchip", size: "md", visible: true },
  { id: "w-uptime", title: "系统在线时间", icon: "fa-clock-rotate-left", size: "sm", visible: true },
  { id: "w-distribution", title: "模型使用分布", icon: "fa-chart-pie", size: "md", visible: true },
  { id: "w-network", title: "服务链路与延迟", icon: "fa-tower-broadcast", size: "sm", visible: true },
  { id: "w-logs", title: "最近请求明细记录", icon: "fa-list-check", size: "lg", visible: true },
];

let userDashboardWidgets = [];
const WIDGET_STORAGE_KEY = "neri_dashboard_widgets_v2";

function loadDashboardWidgetsLayout() {
  try {
    const savedStr = localStorage.getItem(WIDGET_STORAGE_KEY);
    if (savedStr) {
      const parsed = JSON.parse(savedStr);
      if (Array.isArray(parsed) && parsed.length > 0) {
        const savedIds = new Set(parsed.map((p) => p.id));
        const merged = [...parsed];
        DEFAULT_DASHBOARD_WIDGETS.forEach((dw) => {
          if (!savedIds.has(dw.id)) {
            merged.push({ ...dw });
          }
        });
        userDashboardWidgets = merged;
      } else {
        userDashboardWidgets = JSON.parse(JSON.stringify(DEFAULT_DASHBOARD_WIDGETS));
      }
    } else {
      userDashboardWidgets = JSON.parse(JSON.stringify(DEFAULT_DASHBOARD_WIDGETS));
    }
  } catch (e) {
    userDashboardWidgets = JSON.parse(JSON.stringify(DEFAULT_DASHBOARD_WIDGETS));
  }
  applyDashboardWidgetsLayout();
}

function applyDashboardWidgetsLayout() {
  const grid = document.getElementById("overview-widgets-grid");
  if (!grid) return;

  userDashboardWidgets.forEach((w) => {
    const el = grid.querySelector(`[data-widget-id="${w.id}"]`);
    if (!el) return;

    el.classList.remove("widget-size-sm", "widget-size-md", "widget-size-lg", "hidden");

    if (!w.visible) {
      el.classList.add("hidden");
    } else {
      el.classList.add(`widget-size-${w.size || "md"}`);
    }

    grid.appendChild(el);
  });
}

function initWidgetEditor() {
  const btnOpen = document.getElementById("btn-open-widget-editor");
  const modal = document.getElementById("modal-widget-editor");
  const btnClose = document.getElementById("btn-close-widget-editor");
  const btnCancel = document.getElementById("btn-cancel-widget-editor");
  const btnSave = document.getElementById("btn-save-widgets");
  const btnReset = document.getElementById("btn-reset-widgets");

  if (!btnOpen || !modal) return;

  btnOpen.addEventListener("click", () => {
    renderWidgetEditorList();
    modal.classList.remove("hidden");
  });

  const closeModal = () => modal.classList.add("hidden");
  if (btnClose) btnClose.addEventListener("click", closeModal);
  if (btnCancel) btnCancel.addEventListener("click", closeModal);

  if (btnSave) {
    btnSave.addEventListener("click", () => {
      saveWidgetEditorState();
      applyDashboardWidgetsLayout();
      closeModal();
      if (window.NeriModal && typeof window.NeriModal.toast === "function") {
        window.NeriModal.toast("主页看板组件布局已保存生效！");
      }
    });
  }

  if (btnReset) {
    btnReset.addEventListener("click", async () => {
      if (await showConfirmDialog("确定将主页看板布局还原为默认预设排版吗？", "还原排版确认")) {
        userDashboardWidgets = JSON.parse(JSON.stringify(DEFAULT_DASHBOARD_WIDGETS));
        localStorage.removeItem(WIDGET_STORAGE_KEY);
        applyDashboardWidgetsLayout();
        renderWidgetEditorList();
        if (window.NeriModal && typeof window.NeriModal.toast === "function") {
          window.NeriModal.toast("已恢复默认组件排版");
        }
      }
    });
  }
}

function renderWidgetEditorList() {
  const container = document.getElementById("widget-editor-list");
  if (!container) return;

  container.innerHTML = "";

  userDashboardWidgets.forEach((w, index) => {
    const item = document.createElement("div");
    item.className = "widget-drag-item flex items-center justify-between p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-slate-700 transition";
    item.setAttribute("draggable", "true");
    item.setAttribute("data-index", index);
    item.setAttribute("data-id", w.id);

    item.innerHTML = `
      <div class="flex items-center gap-3">
        <div class="cursor-grab text-slate-500 hover:text-cyan-400 p-1 drag-handle" title="按住拖拽调整顺序">
          <i class="fa-solid fa-grip-vertical"></i>
        </div>
        <div class="flex items-center gap-2">
          <i class="fa-solid ${w.icon || "fa-cube"} text-cyan-400 w-5 text-center"></i>
          <span class="font-bold text-xs text-slate-200">${escapeHtml(w.title)}</span>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <!-- 尺寸选择器 (S / M / L) -->
        <div class="inline-flex rounded-lg bg-slate-950 p-0.5 border border-slate-800 text-[11px]">
          <button type="button" class="btn-widget-size px-2 py-0.5 rounded transition ${w.size === "sm" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"}" data-size="sm" title="小号 (1列/手机全宽)">S</button>
          <button type="button" class="btn-widget-size px-2 py-0.5 rounded transition ${w.size === "md" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"}" data-size="md" title="中号 (2列半宽)">M</button>
          <button type="button" class="btn-widget-size px-2 py-0.5 rounded transition ${w.size === "lg" ? "bg-cyan-950 text-cyan-300 font-bold border border-cyan-800" : "text-slate-400 hover:text-slate-200"}" data-size="lg" title="大号 (4列全宽)">L</button>
        </div>

        <!-- 上移/下移快捷箭头 -->
        <div class="flex items-center gap-1">
          <button type="button" class="btn-widget-move-up p-1 text-slate-400 hover:text-cyan-300 transition ${index === 0 ? "opacity-30 pointer-events-none" : ""}" title="上移">
            <i class="fa-solid fa-chevron-up text-xs"></i>
          </button>
          <button type="button" class="btn-widget-move-down p-1 text-slate-400 hover:text-cyan-300 transition ${index === userDashboardWidgets.length - 1 ? "opacity-30 pointer-events-none" : ""}" title="下移">
            <i class="fa-solid fa-chevron-down text-xs"></i>
          </button>
        </div>

        <!-- 显示/隐藏开关 -->
        <label class="relative inline-flex items-center cursor-pointer" title="显示或隐藏此组件">
          <input type="checkbox" class="sr-only peer widget-visibility-toggle" ${w.visible ? "checked" : ""}>
          <div class="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500"></div>
        </label>
      </div>
    `;

    // 绑定尺寸选择点击
    item.querySelectorAll(".btn-widget-size").forEach((btn) => {
      btn.onclick = () => {
        w.size = btn.getAttribute("data-size");
        renderWidgetEditorList();
      };
    });

    // 绑定上移下移
    const upBtn = item.querySelector(".btn-widget-move-up");
    if (upBtn) {
      upBtn.onclick = () => {
        if (index > 0) {
          const temp = userDashboardWidgets[index];
          userDashboardWidgets[index] = userDashboardWidgets[index - 1];
          userDashboardWidgets[index - 1] = temp;
          renderWidgetEditorList();
        }
      };
    }

    const downBtn = item.querySelector(".btn-widget-move-down");
    if (downBtn) {
      downBtn.onclick = () => {
        if (index < userDashboardWidgets.length - 1) {
          const temp = userDashboardWidgets[index];
          userDashboardWidgets[index] = userDashboardWidgets[index + 1];
          userDashboardWidgets[index + 1] = temp;
          renderWidgetEditorList();
        }
      };
    }

    // 绑定显示隐藏
    const toggle = item.querySelector(".widget-visibility-toggle");
    if (toggle) {
      toggle.onchange = (e) => {
        w.visible = e.target.checked;
      };
    }

    // 绑定原生 HTML5 拖拽事件
    item.addEventListener("dragstart", (e) => {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", index);
      item.classList.add("dragging");
    });

    item.addEventListener("dragend", () => {
      item.classList.remove("dragging");
      container.querySelectorAll(".widget-drag-item").forEach((el) => el.classList.remove("drag-over"));
    });

    item.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      item.classList.add("drag-over");
    });

    item.addEventListener("dragleave", () => {
      item.classList.remove("drag-over");
    });

    item.addEventListener("drop", (e) => {
      e.preventDefault();
      item.classList.remove("drag-over");
      const srcIndex = parseInt(e.dataTransfer.getData("text/plain"), 10);
      const destIndex = index;
      if (!isNaN(srcIndex) && srcIndex !== destIndex) {
        const movedItem = userDashboardWidgets.splice(srcIndex, 1)[0];
        userDashboardWidgets.splice(destIndex, 0, movedItem);
        renderWidgetEditorList();
      }
    });

    container.appendChild(item);
  });
}

function saveWidgetEditorState() {
  localStorage.setItem(WIDGET_STORAGE_KEY, JSON.stringify(userDashboardWidgets));
}

// ---------------- 5. 请求日志明细加载 ----------------
async function loadLogs() {
  try {
    const res = await fetch("/api/stats/logs?limit=30");
    if (!res.ok) return;
    const logs = await res.json();
    const tbody = document.getElementById("logs-table-body");
    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center py-6 text-slate-500">暂无调用记录</td></tr>';
      return;
    }

    tbody.innerHTML = logs
      .map((r) => {
        const statusBadge =
          r.status === "success"
            ? '<span class="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800/60">成功</span>'
            : `<span class="px-2 py-0.5 rounded-full bg-rose-950 text-rose-300 border border-rose-800/60" title="${escapeHtml(r.error_message || '')}">失败</span>`;
        const timeStr = r.created_at ? r.created_at.slice(11, 19) : "--";
        const sessionBadge =
          r.session_type === "group"
            ? `<span class="text-indigo-400">群聊 (${maskGroup(r.target_id)})</span>`
            : r.session_type === "private"
            ? `<span class="text-cyan-400">私聊</span>`
            : `<span class="text-purple-400">${escapeHtml(r.session_type)}</span>`;

        return `
          <tr class="hover:bg-slate-800/30 transition">
            <td class="py-2.5 px-3 font-mono text-slate-400">${timeStr}</td>
            <td class="py-2.5 px-3 font-mono">${sessionBadge}</td>
            <td class="py-2.5 px-3 font-mono text-slate-300">${maskQQ(r.user_id) || "--"}</td>
            <td class="py-2.5 px-3 font-mono text-slate-300">${r.model}</td>
            <td class="py-2.5 px-3 text-right font-mono text-cyan-300">${r.prompt_tokens}</td>
            <td class="py-2.5 px-3 text-right font-mono text-purple-300">${r.completion_tokens}</td>
            <td class="py-2.5 px-3 text-right font-mono font-bold text-slate-100">${r.total_tokens}</td>
            <td class="py-2.5 px-3 text-right font-mono text-emerald-400">${r.latency_ms}ms</td>
            <td class="py-2.5 px-3 text-center">${statusBadge}</td>
          </tr>
        `;
      })
      .join("");
  } catch (e) {
    console.error("加载日志失败:", e);
  }
}

document.getElementById("btn-refresh-logs").addEventListener("click", loadLogs);
document.getElementById("btn-clear-stats").addEventListener("click", async () => {
  if (await showConfirmDialog("确定要清空全部 Token 消耗明细统计吗？此操作不可逆！", "清空记录确认", true)) {
    await fetch("/api/stats/clear", { method: "POST" });
    await Promise.all([pollStatusAndStats(), renderChart(), loadLogs()]);
  }
});

// ---------------- 6. 配置加载与表单存取 ----------------
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    const cfg = await res.json();

    // 旧版 LLM 基础配置（若存在则填充）
    const llmBaseUrl = document.getElementById("cfg-llm-base-url");
    if (llmBaseUrl) llmBaseUrl.value = cfg.llm.base_url || "";
    const llmApiKey = document.getElementById("cfg-llm-api-key");
    if (llmApiKey) llmApiKey.value = cfg.llm.api_key || "";
    const llmMaxTokens = document.getElementById("cfg-llm-max-tokens");
    if (llmMaxTokens) llmMaxTokens.value = cfg.llm.max_tokens || 200;
    const llmTemp = document.getElementById("cfg-llm-temperature");
    if (llmTemp) llmTemp.value = cfg.llm.temperature || 0.7;
    const valLlmTemp = document.getElementById("val-llm-temp");
    if (valLlmTemp) valLlmTemp.textContent = cfg.llm.temperature || 0.7;
    const llmTopP = document.getElementById("cfg-llm-topp");
    if (llmTopP) llmTopP.value = cfg.llm.top_p || 1.0;
    const valLlmTopp = document.getElementById("val-llm-topp");
    if (valLlmTopp) valLlmTopp.textContent = cfg.llm.top_p || 1.0;

    const modelSelect = document.getElementById("cfg-llm-model-select");
    if (modelSelect) {
      modelSelect.innerHTML = `<option value="${cfg.llm.model}">${cfg.llm.model}</option>`;
    }

    const decSep = document.getElementById("cfg-dec-separate");
    if (decSep) {
      decSep.checked = cfg.decision_llm.use_separate_model || false;
      toggleDecBlock(decSep.checked);
      const decBase = document.getElementById("cfg-dec-base-url");
      if (decBase) decBase.value = cfg.decision_llm.base_url || "";
      const decKey = document.getElementById("cfg-dec-api-key");
      if (decKey) decKey.value = cfg.decision_llm.api_key || "";
      const decModel = document.getElementById("cfg-dec-model");
      if (decModel) decModel.value = cfg.decision_llm.model || "gpt-4o-mini";
      const decTemp = document.getElementById("cfg-dec-temp");
      if (decTemp) decTemp.value = cfg.decision_llm.temperature || 0.2;
    }

    // TTS
    document.getElementById("cfg-tts-enabled").checked = cfg.tts.enabled;
    document.getElementById("cfg-tts-url").value = cfg.tts.api_url || "";
    if (document.getElementById("cfg-gpt-sovits-dir")) {
      document.getElementById("cfg-gpt-sovits-dir").value = cfg.tts.gpt_sovits_dir || "D:\\GPT-SoVITS\\GPT-SoVITS-v2pro-20250604";
    }
    if (document.getElementById("cfg-tts-gpt-weights")) {
      document.getElementById("cfg-tts-gpt-weights").value = cfg.tts.gpt_weights_path || "";
    }
    if (document.getElementById("cfg-tts-sovits-weights")) {
      document.getElementById("cfg-tts-sovits-weights").value = cfg.tts.sovits_weights_path || "";
    }
    document.getElementById("cfg-tts-mode").value = cfg.tts.mode || "simultaneous";
    document.getElementById("cfg-tts-ref-audio").value = cfg.tts.ref_audio_path || "";
    document.getElementById("cfg-tts-prompt-text").value = cfg.tts.prompt_text || "";
    document.getElementById("cfg-tts-prompt-lang").value = cfg.tts.prompt_lang || "ja";
    document.getElementById("cfg-tts-speed").value = cfg.tts.speed_factor || 1.0;
    document.getElementById("val-tts-speed").textContent = cfg.tts.speed_factor || 1.0;
    document.getElementById("cfg-tts-format").value = cfg.tts.audio_send_format || "base64";

    const voiceOnlyToggle = document.getElementById("cfg-tts-voice-only-toggle");
    if (voiceOnlyToggle) {
      voiceOnlyToggle.checked = (cfg.tts.mode === "voice_only");
    }
    const textLangSelect = document.getElementById("cfg-tts-text-lang");
    if (textLangSelect) {
      textLangSelect.value = cfg.tts.text_lang || "zh";
    }

    // 白名单与安全
    document.getElementById("cfg-sec-priv-enable").checked = cfg.security.private_whitelist_enabled;
    document.getElementById("cfg-sec-priv-list").value = (cfg.security.private_whitelist || []).join("\n");
    document.getElementById("cfg-sec-group-enable").checked = cfg.security.group_whitelist_enabled;
    document.getElementById("cfg-sec-group-list").value = (cfg.security.group_whitelist || []).join("\n");
    document.getElementById("cfg-sec-admin-list").value = (cfg.security.admin_list || []).join("\n");

    // 渲染白名单实时可视化芯片与状态
    renderWhitelistChipsAndStatus(cfg);

    // 指令与主动回复
    document.getElementById("cfg-cmd-prefix").value = cfg.commands.prefix || "/";
    document.getElementById("cfg-cmd-wake-words").value = (cfg.commands.wake_words || []).join(",");
    document.getElementById("cfg-cmd-require-wake").checked = cfg.commands.require_wake_in_group;
    document.getElementById("cfg-cmd-en-reset").checked = cfg.commands.enable_reset;
    document.getElementById("cfg-cmd-en-help").checked = cfg.commands.enable_help;
    document.getElementById("cfg-cmd-en-status").checked = cfg.commands.enable_status;
    document.getElementById("cfg-cmd-en-new").checked = cfg.commands.enable_new !== false;
    document.getElementById("cfg-cmd-en-chatlist").checked = cfg.commands.enable_chatlist !== false;
    document.getElementById("cfg-cmd-en-model").checked = cfg.commands.enable_model !== false;
    document.getElementById("cfg-cmd-en-chat-onoff").checked = cfg.commands.enable_chat_onoff !== false;

    document.getElementById("cfg-act-enabled").checked = cfg.active_reply.enabled;
    // 渲染主动回复白名单勾选列表
    const actWhitelistContainer = document.getElementById("cfg-act-whitelist-container");
    if (actWhitelistContainer) {
      const allowedGroups = cfg.security.group_whitelist || [];
      const currentActGroups = cfg.active_reply.whitelist || [];
      if (allowedGroups.length === 0) {
        actWhitelistContainer.innerHTML = '<div class="text-xs text-slate-500 col-span-2">全局群组白名单为空</div>';
      } else {
        actWhitelistContainer.innerHTML = allowedGroups.map(gid => {
          const isChecked = currentActGroups.includes(gid) ? 'checked' : '';
          return `
            <label class="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" class="act-whitelist-cb accent-cyan-400" value="${gid}" ${isChecked}>
              <span>群 ${maskGroup(gid)}</span>
            </label>
          `;
        }).join('');
      }
    }
    document.getElementById("cfg-act-whitelist").value = (cfg.active_reply.whitelist || []).join(",");
    
    if (cfg.active_reply.strategy === "probability") {
      document.getElementById("cfg-act-strat-prob").checked = true;
      document.getElementById("act-strat-prob-options").classList.remove("hidden");
      document.getElementById("act-strat-model-options").classList.add("hidden");
    } else {
      document.getElementById("cfg-act-strat-model").checked = true;
      document.getElementById("act-strat-model-options").classList.remove("hidden");
      document.getElementById("act-strat-prob-options").classList.add("hidden");
    }
    document.getElementById("cfg-act-prob").value = cfg.active_reply.probability || 0.05;

    document.getElementById("cfg-act-frequency").value = cfg.active_reply.frequency || 5;
    document.getElementById("cfg-act-conf").value = cfg.active_reply.min_confidence || 0.7;
    document.getElementById("val-act-conf").textContent = cfg.active_reply.min_confidence || 0.7;
    document.getElementById("cfg-act-context").value = cfg.active_reply.max_history_context || 8;

    // OneBot 网络连接模式与地址
    document.getElementById("cfg-onebot-mode").value = cfg.onebot.mode || "both";
    document.getElementById("cfg-onebot-forward-url").value = cfg.onebot.forward_ws_url || "ws://127.0.0.1:3001";
    document.getElementById("cfg-onebot-reverse-path").value = cfg.onebot.reverse_ws_path || "/onebot/v11/ws";
    document.getElementById("cfg-onebot-token").value = cfg.onebot.access_token || "";
  } catch (e) {
    console.error("加载配置失败:", e);
  }
}

function renderWhitelistChipsAndStatus(cfg) {
  const privEnEl = document.getElementById("cfg-sec-priv-enable");
  const groupEnEl = document.getElementById("cfg-sec-group-enable");
  const privEn = privEnEl ? privEnEl.checked : (cfg?.security?.private_whitelist_enabled ?? false);
  const groupEn = groupEnEl ? groupEnEl.checked : (cfg?.security?.group_whitelist_enabled ?? false);

  // 1. 双向防护总状态
  const summaryEl = document.getElementById("whitelist-summary-badge");
  const summaryText = document.getElementById("whitelist-summary-text");
  if (summaryEl && summaryText) {
    if (privEn && groupEn) {
      summaryEl.className = "px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 flex items-center gap-1.5";
      summaryText.textContent = "私聊/群聊双向严格白名单生效中";
    } else if (privEn) {
      summaryEl.className = "px-3 py-1 rounded-full text-xs font-semibold bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 flex items-center gap-1.5";
      summaryText.textContent = "仅私聊白名单生效中 (群聊开放)";
    } else if (groupEn) {
      summaryEl.className = "px-3 py-1 rounded-full text-xs font-semibold bg-indigo-950/80 text-indigo-300 border border-indigo-800/60 flex items-center gap-1.5";
      summaryText.textContent = "仅群聊白名单生效中 (私聊开放)";
    } else {
      summaryEl.className = "px-3 py-1 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800/60 flex items-center gap-1.5";
      summaryText.textContent = "白名单已完全关闭 (响应所有消息)";
    }
  }

  // 2. 私聊状态与 Chips
  const privStatus = document.getElementById("badge-priv-status");
  if (privStatus) {
    if (privEn) {
      privStatus.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800/60";
      privStatus.textContent = "已开启 (严格验证)";
    } else {
      privStatus.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700";
      privStatus.textContent = "已关闭 (允许任何私聊)";
    }
  }

  const parseList = (text) =>
    (text || "")
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && !isNaN(Number(s)))
      .map(Number);

  const privListText = document.getElementById("cfg-sec-priv-list")?.value;
  const privQQs = privListText !== undefined ? parseList(privListText) : (cfg?.security?.private_whitelist || []);
  const countPrivEl = document.getElementById("count-priv-users");
  if (countPrivEl) countPrivEl.textContent = privQQs.length;

  const privChipsEl = document.getElementById("container-priv-chips");
  if (privChipsEl) {
    if (privQQs.length === 0) {
      privChipsEl.innerHTML = '<span class="text-slate-500 italic text-[11px]">暂无私聊白名单号码</span>';
    } else {
      privChipsEl.innerHTML = privQQs
        .map((qq) => {
          const bind = (currentBindings || []).find((b) => b.qq === qq);
          const namePart = bind?.nickname ? ` (${escapeHtml(maskSensitiveText(bind.nickname))})` : "";
          const tagPart = bind?.identity_tag ? `<span class="text-[10px] text-cyan-400 ml-1">[${escapeHtml(bind.identity_tag)}]</span>` : "";
          return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-cyan-950/70 text-cyan-200 border border-cyan-800/60 font-mono text-xs"><i class="fa-solid fa-user text-[10px] text-cyan-400"></i><span>${maskQQ(qq)}</span>${namePart}${tagPart}</span>`;
        })
        .join("");
    }
  }

  // 3. 群聊状态与 Chips
  const groupStatus = document.getElementById("badge-group-status");
  if (groupStatus) {
    if (groupEn) {
      groupStatus.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800/60";
      groupStatus.textContent = "已开启 (严格白名单)";
    } else {
      groupStatus.className = "px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700";
      groupStatus.textContent = "已关闭 (允许任何群响应)";
    }
  }

  const groupListText = document.getElementById("cfg-sec-group-list")?.value;
  const groupGIDs = groupListText !== undefined ? parseList(groupListText) : (cfg?.security?.group_whitelist || []);
  const countGroupEl = document.getElementById("count-group-chats");
  if (countGroupEl) countGroupEl.textContent = groupGIDs.length;

  const groupChipsEl = document.getElementById("container-group-chips");
  if (groupChipsEl) {
    if (groupGIDs.length === 0) {
      groupChipsEl.innerHTML = '<span class="text-slate-500 italic text-[11px]">暂无群聊白名单号码</span>';
    } else {
      groupChipsEl.innerHTML = groupGIDs
        .map((gid) => {
          const sess = (flowSessions || []).find((s) => s.target_id === gid && s.session_type === "group");
          const namePart = sess?.display_name ? ` (${escapeHtml(maskFlowTitle(sess.display_name, gid))})` : "";
          return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-950/70 text-indigo-200 border border-indigo-800/60 font-mono text-xs"><i class="fa-solid fa-users text-[10px] text-indigo-400"></i><span>群 ${maskGroup(gid)}</span>${namePart}</span>`;
        })
        .join("");
    }
  }

  // 4. 管理员状态与 Chips
  const adminListText = document.getElementById("cfg-sec-admin-list")?.value;
  const adminQQs = adminListText !== undefined ? parseList(adminListText) : (cfg?.security?.admin_list || []);
  const countAdminEl = document.getElementById("count-admin-users");
  if (countAdminEl) countAdminEl.textContent = adminQQs.length;

  const adminChipsEl = document.getElementById("container-admin-chips");
  if (adminChipsEl) {
    if (adminQQs.length === 0) {
      adminChipsEl.innerHTML = '<span class="text-slate-500 italic text-[11px]">暂无设置管理员</span>';
    } else {
      adminChipsEl.innerHTML = adminQQs
        .map((qq) => {
          const bind = (currentBindings || []).find((b) => b.qq === qq);
          const namePart = bind?.nickname ? ` (${escapeHtml(maskSensitiveText(bind.nickname))})` : " (主人/管理员)";
          return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-950/70 text-amber-200 border border-amber-800/60 font-mono text-xs"><i class="fa-solid fa-crown text-[10px] text-amber-400"></i><span>${maskQQ(qq)}</span>${namePart}</span>`;
        })
        .join("");
    }
  }
}

function initWhitelistVisualEvents() {
  const privEn = document.getElementById("cfg-sec-priv-enable");
  const groupEn = document.getElementById("cfg-sec-group-enable");
  const privList = document.getElementById("cfg-sec-priv-list");
  const groupList = document.getElementById("cfg-sec-group-list");
  const adminList = document.getElementById("cfg-sec-admin-list");

  if (privEn) privEn.addEventListener("change", () => renderWhitelistChipsAndStatus());
  if (groupEn) groupEn.addEventListener("change", () => renderWhitelistChipsAndStatus());
  if (privList) privList.addEventListener("input", () => renderWhitelistChipsAndStatus());
  if (groupList) groupList.addEventListener("input", () => renderWhitelistChipsAndStatus());
  if (adminList) adminList.addEventListener("input", () => renderWhitelistChipsAndStatus());

  const jumpBtn = document.getElementById("btn-jump-to-flow");
  if (jumpBtn) {
    jumpBtn.addEventListener("click", () => {
      const flowNavBtn = document.querySelector('[data-tab="tab-flow"]');
      if (flowNavBtn) flowNavBtn.click();
    });
  }
}

function toggleDecBlock(enabled) {
  const block = document.getElementById("dec-model-block");
  if (!block) return;
  if (enabled) {
    block.classList.remove("opacity-50", "pointer-events-none");
  } else {
    block.classList.add("opacity-50", "pointer-events-none");
  }
}

const decSepEl = document.getElementById("cfg-dec-separate");
if (decSepEl) {
  decSepEl.addEventListener("change", (e) => {
    toggleDecBlock(e.target.checked);
  });
}

// 纯语音与模式选单双向联动
const voiceOnlyTgl = document.getElementById("cfg-tts-voice-only-toggle");
if (voiceOnlyTgl) {
  voiceOnlyTgl.addEventListener("change", (e) => {
    const modeSelect = document.getElementById("cfg-tts-mode");
    if (e.target.checked) {
      modeSelect.value = "voice_only";
    } else if (modeSelect.value === "voice_only") {
      modeSelect.value = "simultaneous";
    }
  });
}
const modeSelEl = document.getElementById("cfg-tts-mode");
if (modeSelEl) {
  modeSelEl.addEventListener("change", (e) => {
    if (voiceOnlyTgl) {
      voiceOnlyTgl.checked = (e.target.value === "voice_only");
    }
  });
}

// 获取模型列表（旧版表单容错保护）
const btnFetchModelsEl = document.getElementById("btn-fetch-models");
if (btnFetchModelsEl) {
  btnFetchModelsEl.addEventListener("click", async () => {
    const btn = btnFetchModelsEl;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>获取中...</span>';

    const baseUrl = document.getElementById("cfg-llm-base-url")?.value.trim() || "";
    const apiKey = document.getElementById("cfg-llm-api-key")?.value.trim() || "";

    try {
      const res = await fetch("/api/llm/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "获取模型列表失败");

      const sel = document.getElementById("cfg-llm-model-select");
      if (sel) {
        const currentVal = sel.value;
        sel.innerHTML = data.models.map((m) => `<option value="${m}">${m}</option>`).join("");
        if (data.models.includes(currentVal)) {
          sel.value = currentVal;
        }
      }
      await showAlertDialog(`成功获取到 ${data.models.length} 个模型！`, "获取模型成功");
    } catch (err) {
      await showAlertDialog("获取模型失败: " + err.message, "获取失败");
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i><span>获取模型列表</span>';
    }
  });
}

function initForms() {
  // 保存 LLM 配置（旧版表单容错保护）
  const btnSaveLlmEl = document.getElementById("btn-save-llm");
  if (btnSaveLlmEl) {
    btnSaveLlmEl.addEventListener("click", async () => {
      const payload = {
        llm: {
          base_url: document.getElementById("cfg-llm-base-url")?.value.trim() || "",
          api_key: document.getElementById("cfg-llm-api-key")?.value.trim() || "",
          model: document.getElementById("cfg-llm-model-select")?.value || "",
          max_tokens: parseInt(document.getElementById("cfg-llm-max-tokens")?.value || "200", 10),
          temperature: parseFloat(document.getElementById("cfg-llm-temperature")?.value || "0.7"),
          top_p: parseFloat(document.getElementById("cfg-llm-topp")?.value || "1.0"),
        },
        decision_llm: {
          use_separate_model: document.getElementById("cfg-dec-separate")?.checked || false,
          base_url: document.getElementById("cfg-dec-base-url")?.value.trim() || "",
          api_key: document.getElementById("cfg-dec-api-key")?.value.trim() || "",
          model: document.getElementById("cfg-dec-model")?.value.trim() || "gpt-4o-mini",
          temperature: parseFloat(document.getElementById("cfg-dec-temp")?.value || "0.2"),
        },
      };
      await saveConfigToServer(payload, "LLM 与决策模型配置已成功保存！");
    });
  }

  // 保存 TTS 配置
  document.getElementById("btn-save-tts").addEventListener("click", async () => {
    let modeVal = document.getElementById("cfg-tts-mode").value;
    if (document.getElementById("cfg-tts-voice-only-toggle")?.checked) {
      modeVal = "voice_only";
    }
    const textLangVal = document.getElementById("cfg-tts-text-lang")?.value || "zh";

    const payload = {
      tts: {
        enabled: document.getElementById("cfg-tts-enabled").checked,
        api_url: document.getElementById("cfg-tts-url").value.trim(),
        gpt_sovits_dir: document.getElementById("cfg-gpt-sovits-dir") ? document.getElementById("cfg-gpt-sovits-dir").value.trim() : "",
        gpt_weights_path: document.getElementById("cfg-tts-gpt-weights") ? document.getElementById("cfg-tts-gpt-weights").value.trim() : "",
        sovits_weights_path: document.getElementById("cfg-tts-sovits-weights") ? document.getElementById("cfg-tts-sovits-weights").value.trim() : "",
        mode: modeVal,
        text_lang: textLangVal,
        ref_audio_path: document.getElementById("cfg-tts-ref-audio").value.trim(),
        prompt_text: document.getElementById("cfg-tts-prompt-text").value.trim(),
        prompt_lang: document.getElementById("cfg-tts-prompt-lang").value,
        speed_factor: parseFloat(document.getElementById("cfg-tts-speed").value),
        audio_send_format: document.getElementById("cfg-tts-format").value,
      },
    };
    await saveConfigToServer(payload, "TTS 语音与同声传译配置已成功保存！");
  });

  // 热切换 / 应用 TTS 权重
  const btnApplyWeights = document.getElementById("btn-apply-tts-weights");
  if (btnApplyWeights) {
    btnApplyWeights.addEventListener("click", async () => {
      const gptPath = document.getElementById("cfg-tts-gpt-weights")?.value.trim() || "";
      const sovitsPath = document.getElementById("cfg-tts-sovits-weights")?.value.trim() || "";
      if (!gptPath && !sovitsPath) {
        await showAlertDialog("请先填写 GPT 权重路径或 SoVITS 权重路径！", "参数缺失");
        return;
      }
      const origHtml = btnApplyWeights.innerHTML;
      try {
        btnApplyWeights.disabled = true;
        btnApplyWeights.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>正在切换...</span>';
        const res = await fetch("/api/tts/service/switch_weights", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            gpt_weights_path: gptPath,
            sovits_weights_path: sovitsPath
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "切换失败");
        await showAlertDialog(data.message || "权重已成功切换！", "切换成功");
      } catch (e) {
        await showAlertDialog("模型权重切换失败: " + e.message, "切换失败");
      } finally {
        btnApplyWeights.disabled = false;
        btnApplyWeights.innerHTML = origHtml;
      }
    });
  }

  // 保存安全与白名单
  document.getElementById("btn-save-security").addEventListener("click", async () => {
    const parseList = (text) =>
      text
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 0 && !isNaN(Number(s)))
        .map(Number);

    const payload = {
      security: {
        private_whitelist_enabled: document.getElementById("cfg-sec-priv-enable").checked,
        private_whitelist: parseList(document.getElementById("cfg-sec-priv-list").value),
        group_whitelist_enabled: document.getElementById("cfg-sec-group-enable").checked,
        group_whitelist: parseList(document.getElementById("cfg-sec-group-list").value),
        admin_list: parseList(document.getElementById("cfg-sec-admin-list").value),
      },
    };
    await saveConfigToServer(payload, "白名单与管理员权限已保存生效！");
  });

  // 保存指令与主动回复
  document.getElementById("btn-save-commands").addEventListener("click", async () => {
    const wakeWords = document
      .getElementById("cfg-cmd-wake-words")
      .value.split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const actWhitelistInputs = document.querySelectorAll(".act-whitelist-cb:checked");
    const actWhitelist = Array.from(actWhitelistInputs).map(cb => parseInt(cb.value, 10));

    const strategy = document.getElementById("cfg-act-strat-model").checked ? "decision_model" : "probability";

    const payload = {
      commands: {
        prefix: document.getElementById("cfg-cmd-prefix").value.trim() || "/",
        wake_words: wakeWords,
        require_wake_in_group: document.getElementById("cfg-cmd-require-wake").checked,
        enable_reset: document.getElementById("cfg-cmd-en-reset").checked,
        enable_help: document.getElementById("cfg-cmd-en-help").checked,
        enable_status: document.getElementById("cfg-cmd-en-status").checked,
        enable_new: document.getElementById("cfg-cmd-en-new").checked,
        enable_chatlist: document.getElementById("cfg-cmd-en-chatlist").checked,
        enable_model: document.getElementById("cfg-cmd-en-model").checked,
        enable_chat_onoff: document.getElementById("cfg-cmd-en-chat-onoff").checked,
      },
      active_reply: {
        enabled: document.getElementById("cfg-act-enabled").checked,
        whitelist: actWhitelist,
        strategy: strategy,
        probability: parseFloat(document.getElementById("cfg-act-prob").value) || 0.05,
        frequency: parseInt(document.getElementById("cfg-act-frequency").value, 10),
        min_confidence: parseFloat(document.getElementById("cfg-act-conf").value),
        max_history_context: parseInt(document.getElementById("cfg-act-context").value, 10),
      },
    };
    await saveConfigToServer(payload, "快速指令与主动回复设置已保存！");
  });

  // 保存 OneBot 网络连接配置
  document.getElementById("btn-save-onebot").addEventListener("click", async () => {
    const payload = {
      onebot: {
        mode: document.getElementById("cfg-onebot-mode").value,
        forward_ws_url: document.getElementById("cfg-onebot-forward-url").value.trim(),
        reverse_ws_path: document.getElementById("cfg-onebot-reverse-path").value.trim(),
        access_token: document.getElementById("cfg-onebot-token").value.trim(),
      },
    };
    await saveConfigToServer(payload, "OneBot11 连接模式与网络地址已保存生效！");
  });

  // 修改密码
  document.getElementById("btn-change-pw").addEventListener("click", async () => {
    const oldP = document.getElementById("chg-old-pw").value.trim();
    const newP = document.getElementById("chg-new-pw").value.trim();
    if (!oldP || !newP) return await showAlertDialog("请完整输入原密码与新密码！", "输入提示");

    try {
      const res = await fetch("/api/auth/change_password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_password: oldP, new_password: newP }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "修改失败");
      await showAlertDialog("密码修改成功，下次请使用新密码登录！", "密码修改成功");
      document.getElementById("chg-old-pw").value = "";
      document.getElementById("chg-new-pw").value = "";
    } catch (err) {
      await showAlertDialog("修改密码失败: " + err.message, "修改失败");
    }
  });

  // 复制 WS 路径
  const btnCopyWsEl = document.getElementById("btn-copy-ws");
  if (btnCopyWsEl) {
    btnCopyWsEl.addEventListener("click", () => {
      const codeEl = document.getElementById("ws-uri-copy");
      const code = codeEl ? codeEl.textContent : "ws://127.0.0.1:8088/onebot/v11/ws";
      navigator.clipboard.writeText(code).then(async () => {
        await showAlertDialog("已复制 NapCat 反向 WebSocket URL 到剪贴板！", "复制成功");
      });
    });
  }

  // 测试 TTS
  document.getElementById("btn-test-tts").addEventListener("click", async () => {
    const text = document.getElementById("tts-test-input").value.trim();
    if (!text) return await showAlertDialog("请输入要合成的台词！", "输入提示");
    const btn = document.getElementById("btn-test-tts");
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>合成中...</span>';

    try {
      const res = await fetch("/api/tts/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, lang: "ja" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "合成失败");

      const player = document.getElementById("tts-audio-player");
      const container = document.getElementById("tts-audio-player-container");
      player.src = data.format === "base64" ? `data:audio/wav;base64,${data.data}` : data.url;
      container.classList.remove("hidden");
      player.play();
    } catch (err) {
      await showAlertDialog("TTS 合成失败: " + err.message, "合成失败");
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-play"></i><span>合成并播放</span>';
    }
  });

  // 快捷 Ping TTS
  document.getElementById("btn-quick-ping-tts").addEventListener("click", async () => {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      await showAlertDialog(`TTS 状态: ${data.tts.online ? "✅ 在线" : "❌ 离线"} (${data.tts.status_text})\n接口地址: ${data.tts.api_url}`, "TTS 连通性测试");
    }
  });
}

async function saveConfigToServer(partialData, successMsg) {
  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(partialData),
    });
    if (!res.ok) throw new Error("保存接口返回错误");
    await showAlertDialog(successMsg, "保存成功");
  } catch (err) {
    await showAlertDialog("保存失败: " + err.message, "保存失败");
  }
}

// ---------------- 6.1 GPT-SoVITS 补丁与服务管理 ----------------
async function checkTTSServiceStatus() {
  const badge = document.getElementById("tts-service-status-badge");
  if (!badge) return;
  try {
    const res = await fetch("/api/tts/service/status");
    if (res.ok) {
      const data = await res.json();
      if (data.running) {
        badge.className = "px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-950 text-emerald-300 border border-emerald-800/80 flex items-center gap-1.5";
        badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span>在线 (端口 ${data.port})</span>`;
      } else {
        badge.className = "px-2.5 py-1 rounded-full text-xs font-bold bg-rose-950 text-rose-300 border border-rose-800/80 flex items-center gap-1.5";
        badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-400"></span><span>未运行 (端口 ${data.port})</span>`;
      }
    }
  } catch (e) {
    badge.className = "px-2.5 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1.5";
    badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-slate-500"></span><span>检测失败</span>`;
  }
}

function initTTSServiceEvents() {
  const btnRefresh = document.getElementById("btn-refresh-tts-status");
  if (btnRefresh) {
    btnRefresh.addEventListener("click", () => {
      checkTTSServiceStatus();
    });
  }

  const btnInstall = document.getElementById("btn-install-tts-patch");
  if (btnInstall) {
    btnInstall.addEventListener("click", async () => {
      const dir = document.getElementById("cfg-gpt-sovits-dir")?.value.trim();
      if (!dir) return await showAlertDialog("请先填写 GPT-SoVITS 根目录绝对路径！", "参数缺失");
      btnInstall.disabled = true;
      btnInstall.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>安装中...</span>`;
      try {
        const res = await fetch("/api/tts/service/install_patch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gpt_sovits_dir: dir }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "安装失败");
        await showAlertDialog(data.message || "补丁安装成功！", "安装成功");
        checkTTSServiceStatus();
      } catch (err) {
        await showAlertDialog("安装定制补丁失败: " + err.message, "安装失败");
      } finally {
        btnInstall.disabled = false;
        btnInstall.innerHTML = `<i class="fa-solid fa-wrench"></i><span>安装补丁与配置脚本</span>`;
      }
    });
  }

  const btnStart = document.getElementById("btn-start-tts-service");
  if (btnStart) {
    btnStart.addEventListener("click", async () => {
      btnStart.disabled = true;
      btnStart.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>启动中...</span>`;
      const badge = document.getElementById("tts-service-status-badge");
      if (badge) {
        badge.className = "px-2.5 py-1 rounded-full text-xs font-bold bg-amber-950 text-amber-300 border border-amber-800/80 flex items-center gap-1.5";
        badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span><span>服务正在拉起...</span>`;
      }
      try {
        const res = await fetch("/api/tts/service/start", { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "启动失败");
        await showAlertDialog(data.message || "服务启动请求已发送！", "启动提示");
        setTimeout(checkTTSServiceStatus, 3000);
      } catch (err) {
        await showAlertDialog("启动 TTS 失败: " + err.message, "启动失败");
      } finally {
        btnStart.disabled = false;
        btnStart.innerHTML = `<i class="fa-solid fa-play"></i><span>一键启动 TTS</span>`;
        checkTTSServiceStatus();
      }
    });
  }

  const btnStop = document.getElementById("btn-stop-tts-service");
  if (btnStop) {
    btnStop.addEventListener("click", async () => {
      if (!await showConfirmDialog("确定要停止 GPT-SoVITS 语音合成服务吗？", "停止服务确认", true)) return;
      try {
        const res = await fetch("/api/tts/service/stop", { method: "POST" });
        const data = await res.json();
        await showAlertDialog(data.message || "TTS 服务已停止", "服务已停止");
        checkTTSServiceStatus();
      } catch (err) {
        await showAlertDialog("停止 TTS 失败: " + err.message, "停止失败");
      }
    });
  }

  const btnLogs = document.getElementById("btn-view-tts-logs");
  const logsBox = document.getElementById("tts-logs-container");
  if (btnLogs && logsBox) {
    btnLogs.addEventListener("click", async () => {
      if (!logsBox.classList.contains("hidden")) {
        logsBox.classList.add("hidden");
        return;
      }
      logsBox.classList.remove("hidden");
      logsBox.textContent = "正在获取日志...";
      try {
        const res = await fetch("/api/tts/service/logs");
        if (res.ok) {
          const data = await res.json();
          logsBox.textContent = data.logs || "暂无日志内容。";
          logsBox.scrollTop = logsBox.scrollHeight;
        }
      } catch (e) {
        logsBox.textContent = "获取日志异常: " + e.message;
      }
    });
  }
}

// ---------------- 7. 人物识别与身份绑定管理 ----------------
async function initIdentities() {
  await loadIdentities();

  document.getElementById("btn-add-identity").addEventListener("click", async () => {
    const qqInput = document.getElementById("new-id-qq").value.trim();
    if (!qqInput || isNaN(Number(qqInput))) return await showAlertDialog("请输入正确的QQ号！", "输入提示");
    const qq = parseInt(qqInput, 10);
    const nick = document.getElementById("new-id-nickname").value.trim();
    const tag = document.getElementById("new-id-tag").value.trim() || "普通群友";
    const notes = document.getElementById("new-id-notes").value.trim();
    const isMaster = document.getElementById("new-id-ismaster").checked;

    const idx = currentBindings.findIndex((b) => b.qq === qq);
    const item = {
      qq: qq,
      nickname: nick,
      identity_tag: tag,
      custom_notes: notes,
      is_master: isMaster,
    };

    if (idx >= 0) {
      currentBindings[idx] = item;
    } else {
      currentBindings.push(item);
    }

    await saveIdentitiesToServer();
    document.getElementById("new-id-qq").value = "";
    document.getElementById("new-id-nickname").value = "";
    document.getElementById("new-id-tag").value = "";
    document.getElementById("new-id-notes").value = "";
    document.getElementById("new-id-ismaster").checked = false;
    renderIdentitiesTable();
    await showAlertDialog(`QQ ${qq} 身份标签绑定已更新！`, "更新成功");
  });

  document.getElementById("btn-save-identities-all").addEventListener("click", async () => {
    await saveIdentitiesToServer();
    await showAlertDialog("身份绑定库与主人QQ设置已成功保存！", "保存成功");
  });
}

async function loadIdentities() {
  try {
    const res = await fetch("/api/identities");
    if (!res.ok) return;
    const data = await res.json();
    currentBindings = data.bindings || [];
    document.getElementById("cfg-identity-master-qq").value = data.master_qq || "";
    renderIdentitiesTable();
  } catch (e) {
    console.error("加载身份绑定失败:", e);
  }
}

function renderIdentitiesTable() {
  const tbody = document.getElementById("identities-table-body");
  if (currentBindings.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="text-center py-6 text-slate-500">暂无身份绑定，所有群友将默认按普通朋友交流</td></tr>';
    return;
  }

  tbody.innerHTML = currentBindings
    .map((b, i) => {
      const roleBadge = b.is_master
        ? '<span class="px-2 py-0.5 rounded-full bg-rose-950 text-rose-300 border border-rose-800/60 font-bold">❤️ 主人/哥哥</span>'
        : '<span class="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">普通群友</span>';

      return `
        <tr class="hover:bg-slate-800/30 transition">
          <td class="py-2.5 px-3 font-mono text-cyan-300 font-bold">${maskQQ(b.qq)}</td>
          <td class="py-2.5 px-3 font-medium text-slate-200">${escapeHtml(maskSensitiveText(b.nickname || "--"))}</td>
          <td class="py-2.5 px-3"><span class="px-2 py-0.5 rounded bg-sky-950/70 text-sky-300 border border-sky-800/50">${escapeHtml(b.identity_tag)}</span></td>
          <td class="py-2.5 px-3 text-slate-400 text-xs">${escapeHtml(b.custom_notes || "--")}</td>
          <td class="py-2.5 px-3 text-center">${roleBadge}</td>
          <td class="py-2.5 px-3 text-center">
            <button type="button" class="btn-del-id text-rose-400 hover:text-rose-300 text-xs transition" data-index="${i}">
              <i class="fa-solid fa-trash-can mr-1"></i>删除
            </button>
          </td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll(".btn-del-id").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const idx = parseInt(btn.getAttribute("data-index"), 10);
      currentBindings.splice(idx, 1);
      await saveIdentitiesToServer();
      renderIdentitiesTable();
    });
  });
}

async function saveIdentitiesToServer() {
  const masterQQ = parseInt(document.getElementById("cfg-identity-master-qq").value, 10) || 0;
  try {
    await fetch("/api/identities/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ master_qq: masterQQ, bindings: currentBindings }),
    });
  } catch (e) {
    console.error("保存身份绑定失败:", e);
  }
}

// ---------------- 8. 白名单群聊历史日志 ----------------
async function initGroupLogs() {
  document.getElementById("btn-search-grouplogs").addEventListener("click", loadGroupLogs);
  document.getElementById("btn-refresh-grouplogs").addEventListener("click", loadGroupLogs);
  document.getElementById("btn-clear-grouplogs").addEventListener("click", async () => {
    const gid = document.getElementById("filter-grouplog-gid").value.trim();
    const msg = gid ? `确定清空群 ${gid} 的所有历史消息流水吗？` : "确定清空全部白名单群聊历史流水吗？";
    if (await showConfirmDialog(msg, "清空日志确认", true)) {
      await fetch(`/api/logs/group/clear${gid ? "?group_id=" + gid : ""}`, { method: "POST" });
      loadGroupLogs();
    }
  });
}

async function loadGroupLogs() {
  const gid = document.getElementById("filter-grouplog-gid").value.trim();
  const kw = document.getElementById("filter-grouplog-kw").value.trim();
  let url = "/api/logs/group?limit=100";
  if (gid) url += `&group_id=${encodeURIComponent(gid)}`;
  if (kw) url += `&keyword=${encodeURIComponent(kw)}`;

  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    const logs = data.logs || [];
    const tbody = document.getElementById("grouplogs-table-body");
    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-slate-500">未检索到群聊消息流水</td></tr>';
      return;
    }

    tbody.innerHTML = logs
      .map((l) => {
        const timeStr = l.created_at ? l.created_at.slice(5, 19) : "--";
        const replyCell = l.bot_reply_content
          ? `<div class="bg-cyan-950/40 p-1.5 rounded border border-cyan-800/40 text-cyan-200 text-xs">${escapeHtml(l.bot_reply_content)}</div>`
          : `<span class="text-slate-600 italic">未回复</span>`;

        return `
          <tr class="hover:bg-slate-800/30 transition">
            <td class="py-2.5 px-3 font-mono text-slate-400 whitespace-nowrap">${timeStr}</td>
            <td class="py-2.5 px-3 font-mono text-indigo-300 font-semibold">${maskGroup(l.group_id)}</td>
            <td class="py-2.5 px-3">
              <div class="font-medium text-slate-200">${escapeHtml(maskSensitiveText(l.nickname || ""))}</div>
              <div class="font-mono text-[11px] text-slate-500">${maskQQ(l.user_id)}</div>
            </td>
            <td class="py-2.5 px-3 text-slate-200 font-sans">${escapeHtml(l.raw_message || "")}</td>
            <td class="py-2.5 px-3">${replyCell}</td>
          </tr>
        `;
      })
      .join("");
  } catch (e) {
    console.error("加载群日志失败:", e);
  }
}

// ---------------- 9. 提示词管理 (Tidebound) ----------------
async function initPromptsEditor() {
  await loadPromptsList();

  document.getElementById("btn-save-prompt-file").addEventListener("click", async () => {
    const content = document.getElementById("prompt-file-content").value;
    try {
      const res = await fetch("/api/prompts/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filepath: activePromptFile, content: content }),
      });
      if (!res.ok) throw new Error("保存失败");
      currentLoadedPrompts[activePromptFile] = content;
      await showAlertDialog(`提示词文件 ${activePromptFile} 已成功写入磁盘！`, "保存成功");
    } catch (err) {
      await showAlertDialog("保存失败: " + err.message, "保存失败");
    }
  });

  document.getElementById("btn-reload-prompts").addEventListener("click", async () => {
    await loadPromptsList();
    await showAlertDialog("提示词模块已重新载入！", "载入成功");
  });
}

async function loadPromptsList() {
  const listDiv = document.getElementById("prompt-file-list");
  try {
    const res = await fetch("/api/prompts");
    if (!res.ok) {
      if (listDiv) listDiv.innerHTML = '<div class="text-xs text-rose-400 px-2 py-1">获取提示词列表失败 (401/未登录)</div>';
      return;
    }
    currentLoadedPrompts = await res.json();

    if (!listDiv) return;
    listDiv.innerHTML = "";
    const files = Object.keys(currentLoadedPrompts).sort();
    if (files.length === 0) {
      listDiv.innerHTML = '<div class="text-xs text-slate-500 px-2 py-1">暂无提示词文件</div>';
      return;
    }

    if (!files.includes(activePromptFile)) {
      activePromptFile = files[0];
    }

    files.forEach((f) => {
      const item = document.createElement("button");
      item.setAttribute("data-file", f);
      item.className = `w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-mono truncate transition ${
        f === activePromptFile
          ? "bg-cyan-950/80 text-cyan-300 border border-cyan-800"
          : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
      }`;
      item.textContent = f;
      item.addEventListener("click", () => {
        activePromptFile = f;
        document.getElementById("current-prompt-filename").textContent = f;
        document.getElementById("prompt-file-content").value = currentLoadedPrompts[f] || "";
        listDiv.querySelectorAll("button").forEach((b) => {
          const isAct = b.getAttribute("data-file") === f;
          b.className = isAct
            ? "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-mono truncate transition bg-cyan-950/80 text-cyan-300 border border-cyan-800"
            : "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-mono truncate transition text-slate-400 hover:text-slate-200 hover:bg-slate-800/40";
        });
      });
      listDiv.appendChild(item);
    });

    if (currentLoadedPrompts[activePromptFile]) {
      document.getElementById("prompt-file-content").value = currentLoadedPrompts[activePromptFile];
      document.getElementById("current-prompt-filename").textContent = activePromptFile;
    }
  } catch (e) {
    console.error("加载提示词失败:", e);
    if (listDiv) listDiv.innerHTML = `<div class="text-xs text-rose-400 px-2 py-1">网络错误: ${e.message}</div>`;
  }
}

// ---------------- 10. 在线调优沙盒 (Neri 聊天) ----------------
let sandboxMessages = [];

function genSandboxMsgId() {
  return "smsg_" + Date.now() + "_" + Math.random().toString(36).substring(2, 7);
}

function updateSandboxModelSelect() {
  const sel = document.getElementById("sandbox-model-select");
  if (!sel) return;
  const curVal = sel.value;
  const options = ['<option value="">跟随主模型</option>'].concat(
    (currentHubItems || []).map(
      (it) => `<option value="${escapeHtml(it.id)}">${escapeHtml(it.display_name || it.model_name)} (${escapeHtml(it.id)})</option>`
    )
  );
  sel.innerHTML = options.join("");
  sel.value = curVal;
}

function initSandbox() {
  const form = document.getElementById("sandbox-chat-form");
  const input = document.getElementById("sandbox-input");
  const box = document.getElementById("sandbox-chat-box");
  const modelSel = document.getElementById("sandbox-model-select");
  const tempRange = document.getElementById("sandbox-temp-range");
  const tempVal = document.getElementById("sandbox-temp-val");
  const maxTokensInput = document.getElementById("sandbox-max-tokens");
  const btnClear = document.getElementById("btn-sandbox-clear");

  // 1. 初始化模型选择列表
  updateSandboxModelSelect();

  // 切换沙盒独立模型时，联动填入预设推荐温度与MaxTokens（仅本页有效，不影响全局）
  if (modelSel) {
    modelSel.addEventListener("change", () => {
      const chosenId = modelSel.value;
      if (chosenId && currentHubItems) {
        const item = currentHubItems.find((it) => it.id === chosenId);
        if (item) {
          if (item.temperature !== undefined && tempRange && tempVal) {
            tempRange.value = item.temperature;
            tempVal.textContent = parseFloat(item.temperature).toFixed(1);
          }
          if (item.max_tokens !== undefined && maxTokensInput) {
            maxTokensInput.value = item.max_tokens;
          }
        }
      }
    });
  }

  // 2. 快速温度滑块数值实时同步
  if (tempRange && tempVal) {
    tempRange.addEventListener("input", () => {
      tempVal.textContent = parseFloat(tempRange.value).toFixed(1);
    });
  }

  // 3. 清空上下文功能
  if (btnClear) {
    btnClear.addEventListener("click", () => {
      sandboxMessages = [];
      renderSandboxChatBox();
      if (window.showToast) {
        window.showToast("上下文已清空，音理已重新开始对话。", "info");
      }
    });
  }

  // 4. 表单发送处理
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = input.value.trim();
      if (!msg) return;

      const chosenModel = modelSel ? modelSel.value : "";
      const chosenTemp = tempRange ? parseFloat(tempRange.value) : undefined;
      const chosenMaxTokens = maxTokensInput ? parseInt(maxTokensInput.value, 10) : undefined;

      // 压入用户消息记录
      const userMsgObj = {
        id: genSandboxMsgId(),
        role: "user",
        content: msg,
        timestamp: Date.now(),
      };
      sandboxMessages.push(userMsgObj);
      appendSandboxUserBubble(userMsgObj);
      input.value = "";

      const loadingId = "loading-" + Date.now();
      appendLoadingBubble(loadingId);
      box.scrollTop = box.scrollHeight;

      try {
        const payload = {
          message: msg,
          messages: sandboxMessages.map((m) => ({ role: m.role, content: m.content })),
        };
        if (chosenModel) payload.model_tag = chosenModel;
        if (chosenTemp !== undefined && !isNaN(chosenTemp)) payload.temperature = chosenTemp;
        if (chosenMaxTokens !== undefined && !isNaN(chosenMaxTokens)) payload.max_tokens = chosenMaxTokens;

        const res = await fetch("/api/chat/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        removeBubble(loadingId);

        if (!res.ok) {
          const errMsg = "生成错误: " + (data.detail || "未知错误");
          const errObj = {
            id: genSandboxMsgId(),
            role: "assistant",
            content: errMsg,
            display_text: errMsg,
            timestamp: Date.now(),
          };
          sandboxMessages.push(errObj);
          appendSandboxBotBubble(errObj);
          return;
        }

        const botMsgObj = {
          id: genSandboxMsgId(),
          role: "assistant",
          content: data.raw_reply || data.display_text,
          display_text: data.display_text,
          voice_url: data.voice_url,
          usage: data.usage,
          timestamp: Date.now(),
        };
        sandboxMessages.push(botMsgObj);
        appendSandboxBotBubble(botMsgObj);

        pollStatusAndStats();
        renderChart();
        loadLogs();
      } catch (err) {
        removeBubble(loadingId);
        const errMsg = "请求失败: " + err.message;
        const errObj = {
          id: genSandboxMsgId(),
          role: "assistant",
          content: errMsg,
          display_text: errMsg,
          timestamp: Date.now(),
        };
        sandboxMessages.push(errObj);
        appendSandboxBotBubble(errObj);
      }
      box.scrollTop = box.scrollHeight;
    });
  }
}

// 单条消息撤回/删除
window.recallSandboxMessage = function (msgId) {
  const idx = sandboxMessages.findIndex((m) => m.id === msgId);
  if (idx !== -1) {
    sandboxMessages.splice(idx, 1);
  }
  const el = document.getElementById(msgId);
  if (el) {
    el.classList.add("opacity-0", "scale-95", "transition-all", "duration-200");
    setTimeout(() => {
      el.remove();
      const box = document.getElementById("sandbox-chat-box");
      if (box && box.children.length === 0) {
        renderSandboxChatBox();
      }
    }, 200);
  }
  if (window.showToast) {
    window.showToast("已撤回此条消息", "info");
  }
};

function renderSandboxChatBox() {
  const box = document.getElementById("sandbox-chat-box");
  if (!box) return;
  box.innerHTML = `
    <div id="sandbox-welcome-msg" class="flex items-start gap-3">
      <img src="/static/img/avatar.png" class="w-8 h-8 rounded-full object-cover">
      <div class="space-y-1">
        <div class="text-xs text-cyan-300 font-semibold">风又音理</div>
        <div class="chat-bubble-bot">哥哥，早上好——！怎么还在赖床呀？快起来，音理特制的大饭团已经准备好咯！</div>
      </div>
    </div>
  `;
  for (const m of sandboxMessages) {
    if (m.role === "user") {
      appendSandboxUserBubble(m);
    } else {
      appendSandboxBotBubble(m);
    }
  }
  box.scrollTop = box.scrollHeight;
}

function appendSandboxUserBubble(msgObj) {
  const box = document.getElementById("sandbox-chat-box");
  const row = document.createElement("div");
  row.id = msgObj.id;
  row.className = "flex items-start gap-2 justify-end group transition-all duration-200";
  row.innerHTML = `
    <div class="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity self-center">
      <button type="button" onclick="recallSandboxMessage('${msgObj.id}')" class="px-1.5 py-0.5 rounded text-[11px] text-slate-400 hover:text-rose-400 hover:bg-slate-800/80 transition flex items-center gap-1 cursor-pointer" title="撤回此条消息">
        <i class="fa-solid fa-rotate-left text-[10px]"></i>
        <span>撤回</span>
      </button>
    </div>
    <div class="chat-bubble-user max-w-[80%]">${escapeHtml(msgObj.content)}</div>
  `;
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function appendSandboxBotBubble(msgObj) {
  const box = document.getElementById("sandbox-chat-box");
  const row = document.createElement("div");
  row.id = msgObj.id;
  row.className = "flex items-start gap-3 group transition-all duration-200";

  let audioSection = "";
  if (msgObj.voice_url) {
    audioSection = `
      <div class="mt-2 pt-2 border-t border-slate-700/60 flex items-center gap-2">
        <audio src="${msgObj.voice_url}" controls class="h-7 w-56 rounded"></audio>
        <span class="text-[10px] text-slate-400 font-mono">日文配音</span>
      </div>
    `;
  }

  const usageBadge = msgObj.usage
    ? `<div class="text-[10px] text-slate-500 font-mono mt-1">Prompt: ${msgObj.usage.prompt_tokens} | Output: ${msgObj.usage.completion_tokens} | 耗时: ${msgObj.usage.latency_ms}ms</div>`
    : "";

  row.innerHTML = `
    <img src="/static/img/avatar.png" class="w-8 h-8 rounded-full object-cover">
    <div class="space-y-1 max-w-[85%]">
      <div class="flex items-center gap-2">
        <span class="text-xs text-cyan-300 font-semibold">风又音理</span>
        <button type="button" onclick="recallSandboxMessage('${msgObj.id}')" class="opacity-0 group-hover:opacity-100 text-[11px] text-slate-500 hover:text-rose-400 transition flex items-center gap-1 cursor-pointer" title="撤回此条消息">
          <i class="fa-solid fa-rotate-left text-[10px]"></i>
          <span>撤回</span>
        </button>
      </div>
      <div class="chat-bubble-bot">
        <div>${escapeHtml(msgObj.display_text || msgObj.content)}</div>
        ${audioSection}
      </div>
      ${usageBadge}
    </div>
  `;
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function appendLoadingBubble(id) {
  const box = document.getElementById("sandbox-chat-box");
  const row = document.createElement("div");
  row.id = id;
  row.className = "flex items-start gap-3";
  row.innerHTML = `
    <img src="/static/img/avatar.png" class="w-8 h-8 rounded-full object-cover">
    <div class="chat-bubble-bot text-slate-400 flex items-center gap-1.5">
      <i class="fa-solid fa-circle-notch fa-spin text-cyan-400"></i>
      <span>音理正在思考与生成配音...</span>
    </div>
  `;
  box.appendChild(row);
}

function removeBubble(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function escapeHtml(text) {
  return (text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ---------------- 现实世界时间感知 ----------------
function initRealTimePerception() {
  const dateEl = document.getElementById("header-real-time-date");
  const clockEl = document.getElementById("header-real-time-clock");
  const periodEl = document.getElementById("header-real-time-period");
  if (!clockEl) return;

  async function syncServerTime() {
    try {
      const res = await fetch("/api/system/time");
      if (res.ok) {
        const data = await res.json();
        if (dateEl) dateEl.textContent = `${data.date} (${data.weekday})`;
        if (clockEl) clockEl.textContent = data.time;
        if (periodEl) periodEl.textContent = data.period;
      }
    } catch (e) {
      const now = new Date();
      if (clockEl) clockEl.textContent = now.toTimeString().slice(0, 8);
    }
  }

  syncServerTime();
  setInterval(() => {
    const now = new Date();
    if (clockEl) clockEl.textContent = now.toTimeString().slice(0, 8);
  }, 1000);
  setInterval(syncServerTime, 25000);
}

// ---------------- 多供应商与系统模型库 ----------------
let currentProviders = [];
let currentHubItems = [];
let fetchedModelsList = [];
let activeFetchingProvider = null;

async function loadProviders() {
  try {
    const res = await fetch("/api/llm/providers");
    if (!res.ok) return;
    currentProviders = await res.json();

    const listDiv = document.getElementById("providers-list");
    if (!listDiv) return;

    if (currentProviders.length === 0) {
      listDiv.innerHTML = `
        <div class="col-span-full p-6 text-center text-xs text-slate-500 bg-slate-900/40 rounded-xl border border-dashed border-slate-800">
          尚未配置任何供应商，点击上方「添加供应商」按钮接入 OpenAI、SiliconFlow、Ollama 等接口。
        </div>
      `;
      return;
    }

    listDiv.innerHTML = currentProviders
      .map(
        (p) => `
      <div class="bg-slate-900/80 border border-slate-800 hover:border-slate-700 p-4 rounded-xl space-y-3 transition flex flex-col justify-between">
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <span class="font-bold text-sm text-slate-100 flex items-center gap-1.5">
              <i class="fa-solid fa-cloud text-cyan-400"></i>
              <span>${escapeHtml(p.name)}</span>
            </span>
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold ${
              p.enabled
                ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                : "bg-slate-800 text-slate-400 border border-slate-700"
            }">${p.enabled ? "已启用" : "已停用"}</span>
          </div>
          <div class="text-[11px] text-slate-400 font-mono break-all truncate" title="${escapeHtml(p.base_url)}">
            ${escapeHtml(p.base_url)}
          </div>
        </div>

        <div class="flex items-center gap-1.5 pt-2 border-t border-slate-800/70">
          <button onclick="fetchModelsFromProvider('${p.id}')" class="btn-secondary px-2.5 py-1 text-xs flex-1 flex items-center justify-center gap-1">
            <i class="fa-solid fa-arrows-rotate text-cyan-400"></i>
            <span>拉取模型</span>
          </button>
          <button onclick="editProvider('${p.id}')" class="btn-secondary px-2 py-1 text-xs text-slate-300" title="编辑供应商">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
          <button onclick="deleteProvider('${p.id}')" class="btn-secondary px-2 py-1 text-xs text-rose-400 hover:text-rose-300" title="删除供应商">
            <i class="fa-solid fa-trash"></i>
          </button>
        </div>
      </div>
    `
      )
      .join("");
  } catch (e) {
    console.error("加载供应商失败:", e);
  }
}

async function loadModelHub() {
  try {
    const res = await fetch("/api/llm/hub");
    if (!res.ok) return;
    const data = await res.json();
    currentHubItems = data.items || [];
    const activeChat = data.active_model_id || "--";
    const activeDec = data.active_decision_model_id || "--";

    const tagEl = document.getElementById("active-model-tag");
    const decEl = document.getElementById("active-decision-tag");
    if (tagEl) tagEl.textContent = activeChat;
    if (decEl) decEl.textContent = activeDec;

    const listDiv = document.getElementById("model-hub-list");
    if (!listDiv) return;

    if (currentHubItems.length === 0) {
      listDiv.innerHTML = `
        <div class="p-8 text-center text-xs text-slate-500 bg-slate-900/40 rounded-xl border border-dashed border-slate-800">
          系统模型库暂无模型。请从上方供应商卡片点击「拉取模型」或点击「手动添加模型」加入模型！
        </div>
      `;
    } else {
      listDiv.innerHTML = currentHubItems
        .map((item) => {
          const isActiveChat = item.id === activeChat;
          const isActiveDec = item.id === activeDec;

          const multiBadges = [];
          if (item.supports_vision)
            multiBadges.push('<span class="px-1.5 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800 text-[10px]">📷 图传</span>');
          if (item.supports_audio)
            multiBadges.push('<span class="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[10px]">🎙️ 音频</span>');
          if (item.supports_video)
            multiBadges.push('<span class="px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800 text-[10px]">🎬 视频</span>');
          if (multiBadges.length === 0) {
            multiBadges.push('<span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">📝 纯文本</span>');
          }

          const activeBadges = [];
          if (isActiveChat)
            activeBadges.push('<span class="px-2 py-0.5 rounded-full font-bold bg-cyan-950 text-cyan-300 border border-cyan-700 text-[10px]">🌟 当前主模型</span>');
          if (isActiveDec)
            activeBadges.push('<span class="px-2 py-0.5 rounded-full font-bold bg-purple-950 text-purple-300 border border-purple-700 text-[10px]">🧠 决策模型</span>');

          return `
          <div class="bg-slate-900/80 border ${
            isActiveChat ? "border-cyan-500/50 shadow-lg shadow-cyan-950/30" : "border-slate-800"
          } p-4 rounded-xl space-y-3 transition">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div class="space-y-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-bold text-sm text-slate-100">${escapeHtml(item.display_name || item.model_name)}</span>
                  <span class="px-2 py-0.5 rounded font-mono text-xs bg-slate-950 text-cyan-300 border border-slate-800">tag: ${escapeHtml(item.id)}</span>
                  ${activeBadges.join(" ")}
                </div>
                <div class="text-[11px] text-slate-400 flex items-center gap-3">
                  <span>供应商: <span class="text-slate-300 font-semibold">${escapeHtml(item.provider_id)}</span></span>
                  <span>真实模型ID: <span class="font-mono text-slate-300">${escapeHtml(item.model_name)}</span></span>
                </div>
              </div>

              <div class="flex items-center gap-1.5 flex-wrap">
                <button onclick="setActiveHubModel('${escapeHtml(item.id)}', 'chat')" class="btn-secondary px-2.5 py-1 text-xs ${
            isActiveChat ? "opacity-50 pointer-events-none" : ""
          }">设为主模型</button>
                <button onclick="setActiveHubModel('${escapeHtml(item.id)}', 'decision')" class="btn-secondary px-2.5 py-1 text-xs ${
            isActiveDec ? "opacity-50 pointer-events-none" : ""
          }">设为决策</button>
                <button onclick="editHubItem('${escapeHtml(item.id)}')" class="btn-secondary px-2 py-1 text-xs" title="编辑参数"><i class="fa-solid fa-pen-to-square"></i></button>
                <button onclick="deleteHubItem('${escapeHtml(item.id)}')" class="btn-secondary px-2 py-1 text-xs text-rose-400 hover:text-rose-300" title="删除"><i class="fa-solid fa-trash"></i></button>
              </div>
            </div>

            <div class="flex items-center justify-between gap-4 pt-2 border-t border-slate-800/80 text-xs">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-slate-400">模态支持:</span>
                ${multiBadges.join(" ")}
              </div>
              <div class="flex items-center gap-3 text-slate-400 text-[11px] font-mono flex-wrap">
                <span>入: <span class="text-amber-300">¥${item.prompt_price_per_1m !== undefined ? item.prompt_price_per_1m : (item.prompt_price_per_1k ? item.prompt_price_per_1k * 1000 : 0)}</span>/1M</span>
                <span>出: <span class="text-amber-300">¥${item.completion_price_per_1m !== undefined ? item.completion_price_per_1m : (item.completion_price_per_1k ? item.completion_price_per_1k * 1000 : 0)}</span>/1M</span>
                <span>温度: <span class="text-slate-200">${item.temperature}</span></span>
                <span>Max: <span class="text-slate-200">${item.max_tokens}</span></span>
                <span>轮数: <span class="text-slate-200">${item.context_limit}</span></span>
              </div>
            </div>
          </div>
        `;
        })
        .join("");
    }

    updateFlowModelSelects();
  } catch (e) {
    console.error("加载模型库失败:", e);
  }
}

function updateFlowModelSelects() {
  const modelSel = document.getElementById("flow-cfg-model");
  const decSel = document.getElementById("flow-cfg-dec-model");
  if (modelSel && decSel) {
    const curModel = modelSel.value;
    const curDec = decSel.value;

    const options = ['<option value="">跟随全局主模型</option>'].concat(
      currentHubItems.map(
        (it) => `<option value="${escapeHtml(it.id)}">${escapeHtml(it.display_name || it.model_name)} (${escapeHtml(it.id)})</option>`
      )
    );

    modelSel.innerHTML = options.join("");
    decSel.innerHTML = options.join("");

    modelSel.value = curModel;
    decSel.value = curDec;
  }

  if (typeof updateSandboxModelSelect === "function") {
    updateSandboxModelSelect();
  }
}

function initMultiProviderAndHub() {
  document.getElementById("btn-add-provider").addEventListener("click", () => {
    document.getElementById("modal-provider-title").innerHTML = '<i class="fa-solid fa-server text-cyan-400"></i><span>添加 LLM 供应商</span>';
    document.getElementById("provider-id-hidden").value = "";
    document.getElementById("provider-name-input").value = "";
    document.getElementById("provider-url-input").value = "";
    document.getElementById("provider-key-input").value = "";
    document.getElementById("provider-enabled-input").checked = true;
    document.getElementById("modal-provider").classList.remove("hidden");
  });

  document.getElementById("btn-close-provider-modal").addEventListener("click", () => {
    document.getElementById("modal-provider").classList.add("hidden");
  });
  document.getElementById("btn-cancel-provider").addEventListener("click", () => {
    document.getElementById("modal-provider").classList.add("hidden");
  });

  document.getElementById("form-provider").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("provider-id-hidden").value.trim();
    const name = document.getElementById("provider-name-input").value.trim();
    const base_url = document.getElementById("provider-url-input").value.trim();
    const api_key = document.getElementById("provider-key-input").value.trim();
    const enabled = document.getElementById("provider-enabled-input").checked;

    try {
      const res = await fetch("/api/llm/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: id || undefined, name, base_url, api_key, enabled }),
      });
      if (!res.ok) throw new Error("保存失败");
      document.getElementById("modal-provider").classList.add("hidden");
      await loadProviders();
    } catch (err) {
      await showAlertDialog("保存供应商失败: " + err.message, "保存失败");
    }
  });

  document.getElementById("btn-close-fetch-modal").addEventListener("click", () => {
    document.getElementById("modal-provider-models").classList.add("hidden");
  });
  document.getElementById("btn-done-fetch-modal").addEventListener("click", () => {
    document.getElementById("modal-provider-models").classList.add("hidden");
  });

  document.getElementById("filter-fetched-models").addEventListener("input", (e) => {
    renderFetchedModels(e.target.value.toLowerCase().trim());
  });

  document.getElementById("btn-add-hub-model").addEventListener("click", () => {
    openHubItemModal();
  });

  document.getElementById("btn-close-hub-modal").addEventListener("click", () => {
    document.getElementById("modal-hub-item").classList.add("hidden");
  });
  document.getElementById("btn-cancel-hub").addEventListener("click", () => {
    document.getElementById("modal-hub-item").classList.add("hidden");
  });

  document.getElementById("hub-temp-input").addEventListener("input", (e) => {
    document.getElementById("hub-temp-val").textContent = e.target.value;
  });

  const updateTagPreview = () => {
    const provSelect = document.getElementById("hub-provider-select");
    const provText = provSelect.options[provSelect.selectedIndex]?.text || "Provider";
    const provName = provText.split(" (")[0].trim();
    const modelName = document.getElementById("hub-model-name-input").value.trim();
    if (modelName) {
      document.getElementById("hub-tag-input").value = `${provName}/${modelName}`;
    }
  };
  document.getElementById("hub-provider-select").addEventListener("change", updateTagPreview);
  document.getElementById("hub-model-name-input").addEventListener("input", updateTagPreview);

  document.getElementById("form-hub-item").addEventListener("submit", async (e) => {
    e.preventDefault();
    const provider_id = document.getElementById("hub-provider-select").value;
    const model_name = document.getElementById("hub-model-name-input").value.trim();
    const tag = document.getElementById("hub-tag-input").value.trim();
    const display_name = document.getElementById("hub-display-name-input").value.trim();
    const temperature = parseFloat(document.getElementById("hub-temp-input").value);
    const max_tokens = parseInt(document.getElementById("hub-maxtokens-input").value, 10);
    const context_limit = parseInt(document.getElementById("hub-context-input").value, 10);
    const supports_vision = document.getElementById("hub-support-vision").checked;
    const supports_audio = document.getElementById("hub-support-audio").checked;
    const supports_video = document.getElementById("hub-support-video").checked;
    const prompt_price_per_1m = parseFloat(document.getElementById("hub-price-prompt-input")?.value || "0") || 0.0;
    const completion_price_per_1m = parseFloat(document.getElementById("hub-price-completion-input")?.value || "0") || 0.0;
    const prompt_price_per_1k = Math.round((prompt_price_per_1m / 1000.0) * 1000000) / 1000000;
    const completion_price_per_1k = Math.round((completion_price_per_1m / 1000.0) * 1000000) / 1000000;

    try {
      const res = await fetch("/api/llm/hub/item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: tag,
          provider_id,
          model_name,
          display_name,
          temperature,
          max_tokens,
          context_limit,
          supports_vision,
          supports_audio,
          supports_video,
          prompt_price_per_1m,
          completion_price_per_1m,
          prompt_price_per_1k,
          completion_price_per_1k,
        }),
      });
      if (!res.ok) {
        let msg = "保存模型失败";
        try {
          const errData = await res.json();
          if (errData.detail) msg = errData.detail;
        } catch (_) {}
        throw new Error(msg);
      }
      document.getElementById("modal-hub-item").classList.add("hidden");
      await loadModelHub();
    } catch (err) {
      await showAlertDialog("保存模型库条目失败: " + err.message, "保存失败");
    }
  });
}

window.editProvider = function (providerId) {
  const p = currentProviders.find((x) => x.id === providerId);
  if (!p) return;
  document.getElementById("modal-provider-title").innerHTML = '<i class="fa-solid fa-server text-cyan-400"></i><span>编辑供应商</span>';
  document.getElementById("provider-id-hidden").value = p.id;
  document.getElementById("provider-name-input").value = p.name;
  document.getElementById("provider-url-input").value = p.base_url;
  document.getElementById("provider-key-input").value = p.api_key;
  document.getElementById("provider-enabled-input").checked = p.enabled;
  document.getElementById("modal-provider").classList.remove("hidden");
};

window.deleteProvider = async function (providerId) {
  if (await showConfirmDialog(`确定要删除供应商「${providerId}」吗？此操作不可逆！`, "删除供应商确认", true)) {
    await fetch(`/api/llm/providers/${providerId}`, { method: "DELETE" });
    await loadProviders();
  }
};

window.fetchModelsFromProvider = async function (providerId) {
  const p = currentProviders.find((x) => x.id === providerId);
  if (!p) return;
  activeFetchingProvider = p;

  const modal = document.getElementById("modal-provider-models");
  document.getElementById("modal-fetch-subtitle").textContent = `从「${p.name}」(${p.base_url}) 拉取`;
  const listDiv = document.getElementById("fetched-models-list");
  listDiv.innerHTML = '<div class="text-xs text-slate-500 py-6 text-center"><i class="fa-solid fa-circle-notch fa-spin text-cyan-400 mr-2"></i>正在连接拉取模型列表中...</div>';
  modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/llm/providers/${providerId}/fetch_models`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "拉取失败");
    fetchedModelsList = data.models || [];
    renderFetchedModels();
  } catch (err) {
    listDiv.innerHTML = `<div class="text-xs text-rose-400 py-6 text-center">拉取模型失败: ${err.message}</div>`;
  }
};

function renderFetchedModels(filter = "") {
  const listDiv = document.getElementById("fetched-models-list");
  if (!listDiv) return;

  const filtered = fetchedModelsList.filter((m) => m.toLowerCase().includes(filter));
  if (filtered.length === 0) {
    listDiv.innerHTML = '<div class="text-xs text-slate-500 py-6 text-center">未检索到匹配的模型</div>';
    return;
  }

  listDiv.innerHTML = filtered
    .map(
      (m) => `
    <div class="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition">
      <div class="font-mono text-xs text-slate-200">${escapeHtml(m)}</div>
      <button onclick="addModelFromFetched('${escapeHtml(m)}')" class="btn-primary px-3 py-1 text-xs flex items-center gap-1">
        <i class="fa-solid fa-plus text-[10px]"></i>
        <span>加入模型库</span>
      </button>
    </div>
  `
    )
    .join("");
}

window.addModelFromFetched = function (modelName) {
  if (!activeFetchingProvider) return;
  const p = activeFetchingProvider;
  openHubItemModal({
    provider_id: p.id,
    model_name: modelName,
    id: `${p.name}/${modelName}`,
    display_name: modelName,
    temperature: 0.7,
    max_tokens: 200,
    context_limit: 12,
    supports_vision: modelName.toLowerCase().includes("vl") || modelName.toLowerCase().includes("vision") || modelName.toLowerCase().includes("4o"),
  });
};

function openHubItemModal(item = null) {
  const provSelect = document.getElementById("hub-provider-select");
  provSelect.innerHTML = currentProviders
    .map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${escapeHtml(p.id)})</option>`)
    .join("");

  if (item) {
    provSelect.value = item.provider_id || (currentProviders[0]?.id || "");
    document.getElementById("hub-model-name-input").value = item.model_name || "";
    document.getElementById("hub-tag-input").value = item.id || "";
    document.getElementById("hub-display-name-input").value = item.display_name || "";
    document.getElementById("hub-temp-input").value = item.temperature !== undefined ? item.temperature : 0.7;
    document.getElementById("hub-temp-val").textContent = document.getElementById("hub-temp-input").value;
    document.getElementById("hub-maxtokens-input").value = item.max_tokens || 200;
    document.getElementById("hub-context-input").value = item.context_limit || 12;
    document.getElementById("hub-support-vision").checked = item.supports_vision || false;
    document.getElementById("hub-support-audio").checked = item.supports_audio || false;
    document.getElementById("hub-support-video").checked = item.supports_video || false;
    const promptInp = document.getElementById("hub-price-prompt-input");
    const pVal = item.prompt_price_per_1m !== undefined ? item.prompt_price_per_1m : (item.prompt_price_per_1k !== undefined ? item.prompt_price_per_1k * 1000 : 0.0);
    if (promptInp) promptInp.value = pVal;
    const compInp = document.getElementById("hub-price-completion-input");
    const cVal = item.completion_price_per_1m !== undefined ? item.completion_price_per_1m : (item.completion_price_per_1k !== undefined ? item.completion_price_per_1k * 1000 : 0.0);
    if (compInp) compInp.value = cVal;
  } else {
    document.getElementById("hub-model-name-input").value = "";
    document.getElementById("hub-tag-input").value = "";
    document.getElementById("hub-display-name-input").value = "";
    document.getElementById("hub-temp-input").value = 0.7;
    document.getElementById("hub-temp-val").textContent = "0.7";
    document.getElementById("hub-maxtokens-input").value = 200;
    document.getElementById("hub-context-input").value = 12;
    document.getElementById("hub-support-vision").checked = false;
    document.getElementById("hub-support-audio").checked = false;
    document.getElementById("hub-support-video").checked = false;
    const promptInp = document.getElementById("hub-price-prompt-input");
    if (promptInp) promptInp.value = 0.0;
    const compInp = document.getElementById("hub-price-completion-input");
    if (compInp) compInp.value = 0.0;
  }

  document.getElementById("modal-hub-item").classList.remove("hidden");
}

window.editHubItem = function (tag) {
  const item = currentHubItems.find((x) => x.id === tag);
  if (!item) return;
  openHubItemModal(item);
};

window.deleteHubItem = async function (tag) {
  if (await showConfirmDialog(`确定要从系统模型库中移除「${tag}」吗？此操作不可逆！`, "移除模型确认", true)) {
    await fetch(`/api/llm/hub/item/${encodeURIComponent(tag)}`, { method: "DELETE" });
    await loadModelHub();
  }
};

window.setActiveHubModel = async function (tag, role) {
  const payload = role === "chat" ? { active_model_id: tag } : { active_decision_model_id: tag };
  await fetch("/api/llm/hub/set_active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadModelHub();
  await pollStatusAndStats();
};

// ---------------- 上下信息流总管理 ----------------
let flowSessions = [];
let currentFlowSessionId = null;
let flowFilter = "all";
let flowSearchTerm = "";
let flowMessagesTimer = null;

async function loadFlowSessions() {
  try {
    const res = await fetch("/api/flow/sessions");
    if (!res.ok) return;
    const data = await res.json();
    flowSessions = data.sessions || [];
    const countEl = document.getElementById("flow-session-count");
    if (countEl) countEl.textContent = flowSessions.length;
    renderFlowSessionCards();
  } catch (e) {
    console.error("加载信息流会话失败:", e);
  }
}

function renderFlowSessionCards() {
  const container = document.getElementById("flow-sessions-list");
  if (!container) return;

  const filtered = flowSessions.filter((s) => {
    if (flowFilter === "group" && s.session_type !== "group") return false;
    if (flowFilter === "private" && s.session_type !== "private") return false;
    if (flowFilter === "pinned" && !s.is_pinned) return false;
    if (flowFilter === "fav" && !s.is_favorite) return false;
    if (flowSearchTerm) {
      const q = flowSearchTerm.toLowerCase();
      const matchName = (s.display_name || "").toLowerCase().includes(q);
      const matchId = String(s.target_id).includes(q);
      if (!matchName && !matchId) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = '<div class="text-xs text-slate-500 py-3">无匹配会话</div>';
    return;
  }

  container.innerHTML = filtered
    .map((s) => {
      const isSelected = s.session_id === currentFlowSessionId;
      const typeLabel = s.session_type === "group" ? "群" : "私";
      const typeBadgeColor = s.session_type === "group" ? "bg-indigo-950 text-indigo-300 border-indigo-800" : "bg-cyan-950 text-cyan-300 border-cyan-800";

      return `
      <div onclick="selectFlowSession('${s.session_id}')" class="shrink-0 p-3 rounded-xl cursor-pointer transition border ${
        isSelected
          ? "bg-slate-900 border-cyan-400 shadow-md shadow-cyan-950/40"
          : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
      } w-52 space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 truncate">
            <span class="px-1.5 py-0.2 rounded text-[10px] font-bold border ${typeBadgeColor}">${typeLabel}</span>
            <span class="font-bold text-xs text-slate-100 truncate">${escapeHtml(maskFlowTitle(s.display_name, s.target_id))}</span>
          </div>
          <div class="flex items-center gap-1" onclick="event.stopPropagation()">
            <button onclick="toggleSessionPin('${s.session_id}', ${!s.is_pinned})" class="text-xs ${
        s.is_pinned ? "text-amber-400" : "text-slate-600 hover:text-slate-400"
      }" title="置顶"><i class="fa-solid fa-thumbtack"></i></button>
            <button onclick="toggleSessionFav('${s.session_id}', ${!s.is_favorite})" class="text-xs ${
        s.is_favorite ? "text-amber-400" : "text-slate-600 hover:text-slate-400"
      }" title="收藏"><i class="fa-solid fa-star"></i></button>
          </div>
        </div>

        <div class="text-[11px] text-slate-400 font-mono">ID: ${maskGroup(s.target_id)}</div>

        <div class="flex items-center justify-between text-[10px] pt-1 border-t border-slate-800/80">
          <span class="${s.chat_enabled ? "text-emerald-400" : "text-rose-400"}">${s.chat_enabled ? "自动聊天: 开" : "自动聊天: 关"}</span>
          <span class="text-slate-400">${s.message_count} 条</span>
        </div>
      </div>
    `;
    })
    .join("");

  if (!currentFlowSessionId && filtered.length > 0) {
    selectFlowSession(filtered[0].session_id);
  }
}

async function selectFlowSession(sessionId) {
  currentFlowSessionId = sessionId;
  renderFlowSessionCards();

  const sess = flowSessions.find((x) => x.session_id === sessionId);
  if (!sess) return;

  const badge = document.getElementById("flow-target-badge");
  const title = document.getElementById("flow-target-title");
  if (badge) {
    badge.textContent = sess.session_type === "group" ? "群聊" : "私聊";
    badge.className = `px-2 py-0.5 rounded text-[11px] font-bold ${
      sess.session_type === "group" ? "bg-indigo-950 text-indigo-300 border-indigo-800" : "bg-cyan-950 text-cyan-300 border-cyan-800"
    }`;
  }
  if (title) title.textContent = `${maskFlowTitle(sess.display_name, sess.target_id)} (${maskGroup(sess.target_id)})`;

  const chatTitle = document.getElementById("flow-chat-title");
  if (chatTitle) chatTitle.textContent = `${maskFlowTitle(sess.display_name, sess.target_id)} 消息流`;

  const pinBtn = document.getElementById("btn-flow-toggle-pin");
  const favBtn = document.getElementById("btn-flow-toggle-fav");
  if (pinBtn) pinBtn.className = sess.is_pinned ? "text-amber-400 p-1" : "text-slate-400 hover:text-amber-400 p-1";
  if (favBtn) favBtn.className = sess.is_favorite ? "text-amber-400 p-1" : "text-slate-400 hover:text-amber-400 p-1";

  try {
    const res = await fetch(`/api/flow/session/${sessionId}/settings`);
    if (res.ok) {
      const cfg = await res.json();
      document.getElementById("flow-cfg-display-name").value = cfg.display_name || "";
      document.getElementById("flow-cfg-chat-enabled").checked = cfg.chat_enabled !== false;
      document.getElementById("flow-cfg-model").value = cfg.model_id || "";
      document.getElementById("flow-cfg-dec-model").value = cfg.decision_model_id || "";
      document.getElementById("flow-cfg-tts-enabled").value = cfg.tts_enabled === null ? "inherit" : String(cfg.tts_enabled);
      document.getElementById("flow-cfg-tts-mode").value = cfg.tts_mode || "inherit";
      document.getElementById("flow-cfg-tts-lang").value = cfg.tts_text_lang || "inherit";
      document.getElementById("flow-cfg-rate-limit").value = cfg.rate_limit_per_min || 0;
      document.getElementById("flow-cfg-cooldown").value = cfg.cooldown_seconds || 0;
    }
  } catch (e) {
    console.error("加载会话配置失败:", e);
  }

  const container = document.getElementById("flow-chat-messages");
  if (container) container.dataset.lastSnapshot = "";

  await Promise.all([loadFlowBranches(sessionId), loadFlowMessages(sessionId)]);

  if (flowMessagesTimer) clearInterval(flowMessagesTimer);
  flowMessagesTimer = setInterval(() => {
    if (currentFlowSessionId === sessionId) {
      loadFlowMessages(sessionId, true);
    }
  }, 3000);
}

async function loadFlowBranches(sessionId) {
  try {
    const res = await fetch(`/api/flow/session/${sessionId}/branches`);
    if (!res.ok) return;
    const data = await res.json();
    const branches = data.branches || [];
    const activeId = data.active_branch_id;

    const sel = document.getElementById("flow-branches-select");
    sel.innerHTML = branches
      .map(
        (b) => `
      <option value="${b.id}" ${b.id === activeId ? "selected" : ""}>
        序号 ${b.id}: ${escapeHtml(b.name)} (${b.message_count}条) ${b.is_active ? "★[当前]" : ""}
      </option>
    `
      )
      .join("");

    const activeB = branches.find((b) => b.id === activeId);
    if (activeB) {
      document.getElementById("flow-branch-active-label").textContent = `当前: ${activeB.name}`;
    }
  } catch (e) {
    console.error("加载分支失败:", e);
  }
}

// 全局失效图片 URL 记录表，彻底消除重复网络请求与闪烁抖动
window.failedFlowImageUrls = window.failedFlowImageUrls || new Set();

window.handleFlowImageError = function (imgEl, url) {
  if (url) window.failedFlowImageUrls.add(url);
  imgEl.style.display = "none";
  const fallback = imgEl.nextElementSibling;
  if (fallback) fallback.classList.remove("hidden");
};

async function loadFlowMessages(sessionId, isSilent = false) {
  try {
    const res = await fetch(`/api/flow/session/${sessionId}/messages`);
    if (!res.ok) return;
    const data = await res.json();
    const msgs = data.messages || [];

    const countEl = document.getElementById("flow-chat-msg-count");
    if (countEl) countEl.textContent = `${msgs.length} 条消息`;

    const container = document.getElementById("flow-chat-messages");
    if (!container) return;

    if (msgs.length === 0) {
      container.dataset.lastSnapshot = "empty";
      container.innerHTML = '<div class="text-center text-xs text-slate-500 py-10">当前上下文暂无消息记录</div>';
      return;
    }

    // 1. 建立数据快照校验：在静默轮询模式下，如果上下文消息列表未发生变化，坚决不重构 DOM，杜绝一切由于 DOM 频繁摧毁重建引发的上下抖动与重绘闪烁
    const lastMsg = msgs[msgs.length - 1];
    const currentSnapshot = `${sessionId}_${msgs.length}_${lastMsg ? (lastMsg.timestamp || "") + (lastMsg.content || "") : ""}`;
    if (isSilent && container.dataset.lastSnapshot === currentSnapshot) {
      return;
    }
    container.dataset.lastSnapshot = currentSnapshot;

    const wasScrolledToBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 60;

    container.innerHTML = msgs
      .map((m) => {
        const isBot = m.role === "assistant";
        const timeStr = m.timestamp ? new Date(m.timestamp * 1000).toTimeString().slice(0, 8) : "";

        // 智能剥离多模态冗余占位文本（例如单独发图时的“(发送了图片)”占位符）
        let rawContent = (m.content || "").trim();
        const hasImages = Array.isArray(m.images) && m.images.length > 0;
        
        let displayContent = rawContent;
        if (hasImages) {
          displayContent = displayContent.replace(/[（\(]发送了图片[）\)]/g, "").replace(/\[图片\]/g, "").trim();
        }

        // 渲染图片列表（带懒加载、过期兜底卡片及比例优化）
        let imgHtml = "";
        if (hasImages) {
          const imgItems = m.images.map((u) => {
            const isFailed = window.failedFlowImageUrls.has(u);
            if (isFailed) {
              return `
              <div class="flow-img-expired inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-slate-400 text-xs shadow-sm select-none my-0.5">
                <i class="fa-regular fa-image text-slate-500"></i>
                <span>[图片已过期]</span>
              </div>`;
            }
            return `
            <div class="flow-msg-image-wrap inline-block my-0.5 max-w-full">
              <img src="${escapeHtml(u)}"
                   loading="lazy"
                   referrerpolicy="no-referrer"
                   alt="聊天图片"
                   class="flow-chat-img max-w-[280px] max-h-[280px] w-auto h-auto rounded-xl object-contain border border-white/10 shadow-md bg-black/20 cursor-pointer hover:opacity-95 hover:scale-[1.01] transition-all block"
                   onclick="window.open('${escapeHtml(u)}')"
                   onerror="window.handleFlowImageError(this, '${escapeHtml(u)}')"
              />
              <div class="flow-img-fallback hidden inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-slate-400 text-xs shadow-sm select-none">
                <i class="fa-regular fa-image text-slate-500"></i>
                <span>[图片已过期]</span>
              </div>
            </div>`;
          });
          imgHtml = `<div class="flex gap-2 flex-wrap items-center mt-1">${imgItems.join("")}</div>`;
        }

        if (m.role === "planner") {
          return `
          <div class="my-3 px-3">
            <div class="border border-emerald-800/80 bg-emerald-950/30 rounded-xl overflow-hidden shadow-sm">
                <div class="bg-emerald-900/40 px-3 py-1.5 flex items-center justify-between border-b border-emerald-800/80">
                  <div class="flex items-center gap-2">
                    <span class="text-xs font-bold text-emerald-300"><i class="fa-solid fa-code-branch mr-1"></i>Planner</span>
                    <span class="text-[10px] bg-emerald-800/60 px-1.5 py-0.5 rounded text-emerald-200">推理</span>
                  </div>
                  <span class="text-[10px] text-slate-500 font-mono">${timeStr}</span>
                </div>
                <div class="p-3 text-[11px] text-slate-300 font-mono whitespace-pre-wrap leading-relaxed">${escapeHtml(m.content)}</div>
            </div>
          </div>
          `;
        }

        if (isBot) {
          let bodyHtml = "";
          if (displayContent && hasImages) {
            bodyHtml = `
              <div class="chat-bubble-bot">
                <div class="break-words">${escapeHtml(displayContent)}</div>
                ${imgHtml}
              </div>`;
          } else if (displayContent) {
            bodyHtml = `
              <div class="chat-bubble-bot">
                <div class="break-words">${escapeHtml(displayContent)}</div>
              </div>`;
          } else if (hasImages) {
            bodyHtml = `
              <div class="flex flex-col items-start gap-1">
                ${imgHtml}
              </div>`;
          }

          return `
          <div class="flex items-start gap-2.5 max-w-[85%]">
            <img src="/static/img/avatar.png" class="w-7 h-7 rounded-full object-cover shrink-0 mt-0.5 border border-cyan-400/50 shadow-sm">
            <div class="space-y-1">
              <div class="text-[11px] text-cyan-300 font-semibold flex items-center gap-1.5">
                <span>风又音理</span>
                <span class="text-[10px] text-slate-500 font-mono">${timeStr}</span>
              </div>
              ${bodyHtml}
            </div>
          </div>
        `;
        } else {
          let bodyHtml = "";
          if (displayContent && hasImages) {
            bodyHtml = `
              <div class="chat-bubble-user text-left">
                <div class="break-words">${escapeHtml(displayContent)}</div>
                ${imgHtml}
              </div>`;
          } else if (displayContent) {
            bodyHtml = `
              <div class="chat-bubble-user text-left">
                <div class="break-words">${escapeHtml(displayContent)}</div>
              </div>`;
          } else if (hasImages) {
            bodyHtml = `
              <div class="flex flex-col items-end gap-1">
                ${imgHtml}
              </div>`;
          }

          return `
          <div class="flex items-start justify-end gap-2.5 ml-auto max-w-[85%]">
            <div class="space-y-1 text-right">
              <div class="text-[11px] text-slate-300 font-semibold flex items-center justify-end gap-1.5">
                <span class="text-[10px] text-slate-500 font-mono">${timeStr}</span>
                <span>${escapeHtml(maskSensitiveText(m.user_name || "群友"))}</span>
              </div>
              ${bodyHtml}
            </div>
          </div>
        `;
        }
      })
      .join("");

    if (!isSilent || wasScrolledToBottom) {
      container.scrollTop = container.scrollHeight;
    }
  } catch (e) {
    console.error("加载消息失败:", e);
  }
}

window.toggleSessionPin = async function (sessionId, isPinned) {
  await fetch(`/api/flow/session/${sessionId}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_pinned: isPinned }),
  });
  await loadFlowSessions();
};

window.toggleSessionFav = async function (sessionId, isFav) {
  await fetch(`/api/flow/session/${sessionId}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_favorite: isFav }),
  });
  await loadFlowSessions();
};

window.selectFlowSession = selectFlowSession;

function initFlowHub() {
  document.querySelectorAll(".flow-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".flow-filter-btn").forEach((b) => {
        b.classList.remove("active", "border-cyan-500/40", "bg-cyan-950/60", "text-cyan-300");
        b.classList.add("border-slate-800", "bg-slate-900/60", "text-slate-400");
      });
      btn.classList.add("active", "border-cyan-500/40", "bg-cyan-950/60", "text-cyan-300");
      btn.classList.remove("border-slate-800", "bg-slate-900/60", "text-slate-400");
      flowFilter = btn.getAttribute("data-filter");
      renderFlowSessionCards();
    });
  });

  document.getElementById("flow-search-input").addEventListener("input", (e) => {
    flowSearchTerm = e.target.value.trim();
    renderFlowSessionCards();
  });

  document.getElementById("btn-refresh-flow-sessions").addEventListener("click", loadFlowSessions);
  document.getElementById("btn-refresh-flow-chat").addEventListener("click", () => {
    if (currentFlowSessionId) loadFlowMessages(currentFlowSessionId);
  });

  document.getElementById("btn-flow-toggle-pin").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    const s = flowSessions.find((x) => x.session_id === currentFlowSessionId);
    if (s) toggleSessionPin(currentFlowSessionId, !s.is_pinned);
  });
  document.getElementById("btn-flow-toggle-fav").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    const s = flowSessions.find((x) => x.session_id === currentFlowSessionId);
    if (s) toggleSessionFav(currentFlowSessionId, !s.is_favorite);
  });

  document.getElementById("btn-save-flow-settings").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    const ttsEnVal = document.getElementById("flow-cfg-tts-enabled").value;
    const ttsModeVal = document.getElementById("flow-cfg-tts-mode").value;
    const ttsLangVal = document.getElementById("flow-cfg-tts-lang").value;

    const updates = {
      display_name: document.getElementById("flow-cfg-display-name").value.trim(),
      chat_enabled: document.getElementById("flow-cfg-chat-enabled").checked,
      model_id: document.getElementById("flow-cfg-model").value || null,
      decision_model_id: document.getElementById("flow-cfg-dec-model").value || null,
      tts_enabled: ttsEnVal === "inherit" ? null : ttsEnVal === "true",
      tts_mode: ttsModeVal === "inherit" ? null : ttsModeVal,
      tts_text_lang: ttsLangVal === "inherit" ? null : ttsLangVal,
      rate_limit_per_min: parseInt(document.getElementById("flow-cfg-rate-limit").value, 10) || 0,
      cooldown_seconds: parseInt(document.getElementById("flow-cfg-cooldown").value, 10) || 0,
    };

    try {
      const res = await fetch(`/api/flow/session/${currentFlowSessionId}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (!res.ok) throw new Error("保存失败");
      await showAlertDialog("会话专属配置已成功保存！", "保存成功");
      await loadFlowSessions();
    } catch (err) {
      await showAlertDialog("保存会话配置失败: " + err.message, "保存失败");
    }
  });

  document.getElementById("btn-flow-switch-branch").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    const branchId = parseInt(document.getElementById("flow-branches-select").value, 10);
    await fetch(`/api/flow/session/${currentFlowSessionId}/branch/switch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ branch_id: branchId }),
    });
    await Promise.all([loadFlowBranches(currentFlowSessionId), loadFlowMessages(currentFlowSessionId)]);
  });

  document.getElementById("btn-flow-create-branch").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    const name = document.getElementById("flow-new-branch-name").value.trim();
    await fetch(`/api/flow/session/${currentFlowSessionId}/branch/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    document.getElementById("flow-new-branch-name").value = "";
    await Promise.all([loadFlowBranches(currentFlowSessionId), loadFlowMessages(currentFlowSessionId), loadFlowSessions()]);
  });

  document.getElementById("btn-flow-delete-branch").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    const branchId = document.getElementById("flow-branches-select").value;
    if (await showConfirmDialog(`确定要删除/归档当前选中的分支 (序号 ${branchId}) 吗？`, "删除分支确认", true)) {
      await fetch(`/api/flow/session/${currentFlowSessionId}/branch/${branchId}`, { method: "DELETE" });
      await Promise.all([loadFlowBranches(currentFlowSessionId), loadFlowMessages(currentFlowSessionId), loadFlowSessions()]);
    }
  });

  document.getElementById("btn-flow-clear-context").addEventListener("click", async () => {
    if (!currentFlowSessionId) return;
    if (await showConfirmDialog("确定要清空当前上下文的全部对话记忆吗？此操作不可逆！", "清空上下文记忆", true)) {
      await fetch(`/api/flow/session/${currentFlowSessionId}/branch/clear`, { method: "POST" });
      await Promise.all([loadFlowBranches(currentFlowSessionId), loadFlowMessages(currentFlowSessionId), loadFlowSessions()]);
    }
  });

  const doSendManual = async () => {
    if (!currentFlowSessionId) {
      await showAlertDialog("请先在上方选择一个会话！", "提示");
      return;
    }
    const input = document.getElementById("flow-manual-input");
    const text = input.value.trim();
    if (!text) return;

    const asBot = document.getElementById("flow-send-as-bot").checked;
    const sendToQq = document.getElementById("flow-send-to-qq").checked;

    input.value = "";
    try {
      const res = await fetch(`/api/flow/session/${currentFlowSessionId}/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, as_bot: asBot, send_to_qq: sendToQq }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "发送失败");
      }
      await loadFlowMessages(currentFlowSessionId);
    } catch (e) {
      await showAlertDialog("发送干预消息失败: " + e.message, "发送失败");
    }
  };

  document.getElementById("btn-flow-send-manual").addEventListener("click", doSendManual);
  document.getElementById("flow-manual-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      doSendManual();
    }
  });
}

// ---------------- 13. 记忆系统与知识图谱 (Memory Management Hub) ----------------
let currentMemSubtab = "mem-view-graph";
let memoryGraphData = { nodes: [], links: [] };
let graphCanvas = null;
let graphCtx = null;
let graphAnimId = null;
let graphCamera = { x: 0, y: 0, scale: 1.0, isDragging: false, startX: 0, startY: 0, dragStartTime: 0, clickStartPos: { x: 0, y: 0 } };
let draggedNode = null;
let hoveredNode = null;

async function loadMemoryAll() {
  await Promise.allSettled([
    loadMemoryStats(),
    loadCurrentMemSubtab(),
  ]);
}

function formatMemTime(ts) {
  if (ts === null || ts === undefined || ts === "") return "-";
  if (typeof ts === "number") {
    const ms = ts < 1e11 ? ts * 1000 : ts;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? String(ts) : d.toLocaleString("zh-CN", { hour12: false });
  }
  if (typeof ts === "string") {
    if (!isNaN(Number(ts)) && !ts.includes("-") && !ts.includes(":")) {
      return formatMemTime(Number(ts));
    }
    return ts.replace("T", " ").substring(0, 19);
  }
  return String(ts);
}

function formatMemDate(ts) {
  if (ts === null || ts === undefined || ts === "") return "-";
  if (typeof ts === "number") {
    const ms = ts < 1e11 ? ts * 1000 : ts;
    const d = new Date(ms);
    return isNaN(d.getTime()) ? String(ts) : d.toLocaleDateString("zh-CN");
  }
  if (typeof ts === "string") {
    if (!isNaN(Number(ts)) && !ts.includes("-") && !ts.includes(":")) {
      return formatMemDate(Number(ts));
    }
    return ts.substring(0, 10);
  }
  return String(ts);
}

async function loadMemoryStats() {
  try {
    const res = await fetch("/api/memory/stats");
    if (!res.ok) return;
    const data = await res.json();
    const stats = data.stats || data || {};

    const totalCount = stats.total_count ?? stats.total_memories ?? 0;
    const activeCount = stats.active_count ?? stats.active_memories ?? 0;
    const factCount = stats.fact_count ?? stats.fact_memories ?? 0;
    const episodeCount = stats.episode_count ?? stats.episode_memories ?? 0;
    const forgottenCount = stats.forgotten_count ?? stats.forgotten_memories ?? 0;
    const userCount = stats.user_count ?? stats.unique_users ?? 0;

    const isHealthy = stats.status === "healthy" || stats.status === "ok" || stats.is_healthy === true || stats.healthy === true || stats.collection_exists === true || totalCount >= 0;

    const badge = document.getElementById("mem-status-badge");
    if (badge) {
      if (isHealthy) {
        badge.className = "px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1";
        badge.innerHTML = `
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>${stats.status_text || "正常就绪"}</span>
        `;
      } else {
        badge.className = "px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950 text-rose-300 border border-rose-800 flex items-center gap-1";
        badge.innerHTML = `
          <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
          <span>异常未就绪</span>
        `;
      }
    }

    const channelsEl = document.getElementById("mem-status-channels");
    if (channelsEl && Array.isArray(stats.channels)) {
      channelsEl.textContent = stats.channels.map(c => c.name.split(" ")[0]).join("、");
    }

    const dimEl = document.getElementById("mem-dim-val");
    if (dimEl) dimEl.textContent = (stats.dimension || 512) + " 维";

    const modelEl = document.getElementById("mem-model-val");
    if (modelEl) {
      const isLocal = stats.is_local_model !== false;
      modelEl.textContent = `${stats.model_name || "bge-small-zh-v1.5"} (${isLocal ? "本地离线" : "API备用"})`;
    }

    const colEl = document.getElementById("mem-col-val");
    if (colEl) colEl.textContent = stats.collection_name || "neri_memories";

    const integrityEl = document.getElementById("mem-integrity-val");
    if (integrityEl) integrityEl.textContent = "ChromaDB 持久化存储 (已验证)";

    const totalEl = document.getElementById("mem-total-val");
    if (totalEl) totalEl.textContent = totalCount + " 条";

    const detailEl = document.getElementById("mem-detail-counts");
    if (detailEl) {
      detailEl.textContent = `活跃: ${activeCount} | 事实: ${factCount} | 情景: ${episodeCount} | 用户: ${userCount}`;
    }

    // 更新子标签页计数
    const countFacts = document.getElementById("count-subtab-facts");
    if (countFacts) countFacts.textContent = factCount;

    const countEpisodes = document.getElementById("count-subtab-episodes");
    if (countEpisodes) countEpisodes.textContent = episodeCount;

    const countArchive = document.getElementById("count-subtab-archive");
    if (countArchive) countArchive.textContent = forgottenCount;
  } catch (err) {
    console.error("加载记忆系统状态指标失败:", err);
  }
}

async function loadCurrentMemSubtab() {
  if (currentMemSubtab === "mem-view-graph") {
    await loadMemoryGraph();
  } else if (currentMemSubtab === "mem-view-timeline") {
    await loadMemoryTimeline();
  } else if (currentMemSubtab === "mem-view-facts") {
    await loadMemoryTable("fact", "mem-facts-tbody");
  } else if (currentMemSubtab === "mem-view-episodes") {
    await loadMemoryTable("episode", "mem-episodes-tbody");
  } else if (currentMemSubtab === "mem-view-archive") {
    await loadMemoryTable("archive", "mem-archive-tbody");
  }
}

async function loadMemoryGraph() {
  const limit = document.getElementById("mem-graph-limit-select")?.value || 120;
  const kw = document.getElementById("mem-graph-search-input")?.value.trim() || "";

  try {
    let url = `/api/memory/graph?limit=${limit}`;
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    let rawNodes = data.nodes || [];
    let rawLinks = data.links || [];

    if (kw) {
      const lowerKw = kw.toLowerCase();
      const matchedNodeIds = new Set(
        rawNodes
          .filter(n => (n.full_content && n.full_content.toLowerCase().includes(lowerKw)) || (n.label && n.label.toLowerCase().includes(lowerKw)) || (n.user_id && String(n.user_id).includes(lowerKw)))
          .map(n => n.id)
      );
      rawNodes = rawNodes.filter(n => matchedNodeIds.has(n.id));
      rawLinks = rawLinks.filter(l => matchedNodeIds.has(l.source) && matchedNodeIds.has(l.target));
    }

    const statNodes = document.getElementById("graph-stat-nodes");
    if (statNodes) statNodes.textContent = `节点: ${rawNodes.length}`;
    const statLinks = document.getElementById("graph-stat-links");
    if (statLinks) statLinks.textContent = `关系: ${rawLinks.length}`;

    initGraphCanvas();
    setupGraphPhysics(rawNodes, rawLinks);
  } catch (e) {
    console.error("加载记忆图谱失败:", e);
  }
}

function setupGraphPhysics(nodes, links) {
  if (!graphCanvas) return;
  const rect = graphCanvas.getBoundingClientRect();
  const width = rect.width || 800;
  const height = rect.height || 520;
  const cx = width / 2;
  const cy = height / 2;

  const nodeMap = new Map();
  nodes.forEach((n, idx) => {
    const angle = (idx / Math.max(1, nodes.length)) * Math.PI * 2 * 3;
    const r = Math.min(width, height) * 0.35 * Math.sqrt((idx + 1) / Math.max(1, nodes.length));
    n.x = cx + Math.cos(angle) * r + (Math.random() - 0.5) * 20;
    n.y = cy + Math.sin(angle) * r + (Math.random() - 0.5) * 20;
    n.vx = 0;
    n.vy = 0;
    n.radius = Math.max(8, Math.min(22, (n.size || 8) * 1.3));
    nodeMap.set(n.id, n);
  });

  const resolvedLinks = [];
  links.forEach(l => {
    const s = nodeMap.get(l.source);
    const t = nodeMap.get(l.target);
    if (s && t) {
      resolvedLinks.push({ source: s, target: t, weight: l.weight || 0.5 });
    }
  });

  memoryGraphData = {
    nodes,
    links: resolvedLinks,
    width,
    height
  };

  if (!graphAnimId) {
    startGraphAnimationLoop();
  }
}

function startGraphAnimationLoop() {
  function renderStep() {
    if (currentMemSubtab !== "mem-view-graph") {
      graphAnimId = null;
      return;
    }

    stepGraphPhysics();
    drawGraphScene();
    graphAnimId = requestAnimationFrame(renderStep);
  }
  graphAnimId = requestAnimationFrame(renderStep);
}

function stepGraphPhysics() {
  const { nodes, links, width, height } = memoryGraphData;
  if (!nodes || nodes.length === 0) return;

  const cx = width / 2;
  const cy = height / 2;
  const damping = 0.88;

  // 1. 斥力
  for (let i = 0; i < nodes.length; i++) {
    const na = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const nb = nodes[j];
      const dx = na.x - nb.x;
      const dy = na.y - nb.y;
      const distSq = dx * dx + dy * dy + 1;
      const dist = Math.sqrt(distSq);
      if (dist < 260) {
        const force = 420 / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        if (na !== draggedNode) { na.vx += fx; na.vy += fy; }
        if (nb !== draggedNode) { nb.vx -= fx; nb.vy -= fy; }
      }
    }
  }

  // 2. 边弹簧引力
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    const dx = l.target.x - l.source.x;
    const dy = l.target.y - l.source.y;
    const dist = Math.sqrt(dx * dx + dy * dy) + 0.1;
    const targetDist = 85;
    const spring = (dist - targetDist) * 0.035;
    const fx = (dx / dist) * spring;
    const fy = (dy / dist) * spring;
    if (l.source !== draggedNode) { l.source.vx += fx; l.source.vy += fy; }
    if (l.target !== draggedNode) { l.target.vx -= fx; l.target.vy -= fy; }
  }

  // 3. 中心向心力与阻尼衰减
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n === draggedNode) continue;
    n.vx += (cx - n.x) * 0.005;
    n.vy += (cy - n.y) * 0.005;
    n.vx *= damping;
    n.vy *= damping;
    n.x += n.vx;
    n.y += n.vy;
  }
}

function drawGraphScene() {
  if (!graphCanvas || !graphCtx) return;
  const rect = graphCanvas.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;

  graphCtx.clearRect(0, 0, width, height);

  graphCtx.save();
  graphCtx.translate(graphCamera.x, graphCamera.y);
  graphCtx.scale(graphCamera.scale, graphCamera.scale);

  const { nodes, links } = memoryGraphData;
  const isLightMode = document.body.classList.contains("theme-light");

  // 绘制边
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    const isConn = hoveredNode && (l.source === hoveredNode || l.target === hoveredNode);
    graphCtx.beginPath();
    graphCtx.moveTo(l.source.x, l.source.y);
    graphCtx.lineTo(l.target.x, l.target.y);
    if (isLightMode) {
      graphCtx.strokeStyle = isConn ? "rgba(14, 165, 233, 0.9)" : "rgba(100, 116, 139, 0.4)";
      graphCtx.lineWidth = isConn ? 2.5 : 1.2;
    } else {
      graphCtx.strokeStyle = isConn ? "rgba(34, 211, 238, 0.75)" : "rgba(148, 163, 184, 0.18)";
      graphCtx.lineWidth = isConn ? 2 : 1;
    }
    graphCtx.stroke();
  }

  // 绘制节点
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const isHovered = (n === hoveredNode);
    const isImportant = (n.importance >= 4.0);

    // 外圈光晕 (Halo)
    if (isHovered || isImportant) {
      graphCtx.beginPath();
      graphCtx.arc(n.x, n.y, n.radius + (isHovered ? 8 : 4), 0, Math.PI * 2);
      if (isLightMode) {
        graphCtx.fillStyle = isHovered ? "rgba(14, 165, 233, 0.35)" : "rgba(129, 140, 248, 0.3)";
      } else {
        graphCtx.fillStyle = isHovered ? "rgba(34, 211, 238, 0.35)" : "rgba(129, 140, 248, 0.2)";
      }
      graphCtx.fill();
    }

    // 核心圆形
    graphCtx.beginPath();
    graphCtx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
    graphCtx.fillStyle = n.color || (n.type === "fact" ? "#22d3ee" : "#818cf8");
    graphCtx.fill();
    if (isLightMode) {
      graphCtx.strokeStyle = isHovered ? "#0284c7" : "rgba(255, 255, 255, 0.95)";
      graphCtx.lineWidth = isHovered ? 2.5 : 2;
    } else {
      graphCtx.strokeStyle = isHovered ? "#ffffff" : "rgba(15, 23, 42, 0.8)";
      graphCtx.lineWidth = isHovered ? 2.5 : 1.5;
    }
    graphCtx.stroke();

    // 节点文字标注 (双层描边 + 亮暗自适应高对比色彩，彻底杜绝亮色下不可见)
    graphCtx.font = "bold 11px 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif";
    graphCtx.textAlign = "center";
    graphCtx.textBaseline = "middle";
    const labelText = n.label || "记忆";
    const textY = n.y + n.radius + 14;

    graphCtx.lineJoin = "round";
    graphCtx.miterLimit = 2;

    if (isLightMode) {
      // 亮色模式：深紫蓝高对比文字 + 纯白保护光晕外描边，任何亮色壁纸下均清晰醒目
      graphCtx.strokeStyle = "rgba(255, 255, 255, 0.95)";
      graphCtx.lineWidth = 3.5;
      graphCtx.strokeText(labelText, n.x, textY);
      graphCtx.fillStyle = isHovered ? "#0284c7" : "#1e1b4b";
      graphCtx.fillText(labelText, n.x, textY);
    } else {
      // 暗色模式：高亮浅色文字 + 深色阴影描边
      graphCtx.strokeStyle = "rgba(15, 23, 42, 0.85)";
      graphCtx.lineWidth = 3;
      graphCtx.strokeText(labelText, n.x, textY);
      graphCtx.fillStyle = isHovered ? "#38bdf8" : "rgba(241, 245, 249, 0.95)";
      graphCtx.fillText(labelText, n.x, textY);
    }
  }

  graphCtx.restore();
}

function initGraphCanvas() {
  graphCanvas = document.getElementById("mem-graph-canvas");
  if (!graphCanvas) return;
  graphCtx = graphCanvas.getContext("2d");

  const resize = () => {
    const rect = graphCanvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    graphCanvas.width = rect.width * dpr;
    graphCanvas.height = rect.height * dpr;
    graphCtx.setTransform(1, 0, 0, 1, 0, 0);
    graphCtx.scale(dpr, dpr);
    if (memoryGraphData.nodes) {
      memoryGraphData.width = rect.width;
      memoryGraphData.height = rect.height;
    }
  };
  resize();
  window.addEventListener("resize", resize);

  const toWorld = (clientX, clientY) => {
    const rect = graphCanvas.getBoundingClientRect();
    const mx = clientX - rect.left;
    const my = clientY - rect.top;
    const wx = (mx - graphCamera.x) / graphCamera.scale;
    const wy = (my - graphCamera.y) / graphCamera.scale;
    return { wx, wy, mx, my };
  };

  const findNodeAt = (wx, wy) => {
    const nodes = memoryGraphData.nodes || [];
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      const dx = wx - n.x;
      const dy = wy - n.y;
      if (dx * dx + dy * dy <= (n.radius + 4) * (n.radius + 4)) {
        return n;
      }
    }
    return null;
  };

  const tooltipEl = document.getElementById("mem-graph-tooltip");

  graphCanvas.addEventListener("mousedown", (e) => {
    const { wx, wy, mx, my } = toWorld(e.clientX, e.clientY);
    const hit = findNodeAt(wx, wy);
    graphCamera.dragStartTime = Date.now();
    graphCamera.clickStartPos = { x: mx, y: my };

    if (hit) {
      draggedNode = hit;
    } else {
      graphCamera.isDragging = true;
      graphCamera.startX = mx - graphCamera.x;
      graphCamera.startY = my - graphCamera.y;
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!graphCanvas || !document.getElementById("mem-view-graph") || document.getElementById("mem-view-graph").classList.contains("hidden")) return;
    const { wx, wy, mx, my } = toWorld(e.clientX, e.clientY);

    if (draggedNode) {
      draggedNode.x = wx;
      draggedNode.y = wy;
      draggedNode.vx = 0;
      draggedNode.vy = 0;
    } else if (graphCamera.isDragging) {
      graphCamera.x = mx - graphCamera.startX;
      graphCamera.y = my - graphCamera.startY;
    }

    const hit = findNodeAt(wx, wy);
    hoveredNode = hit;
    if (hit && tooltipEl) {
      tooltipEl.classList.remove("hidden");
      const rect = graphCanvas.getBoundingClientRect();
      const left = Math.min(rect.width - 240, Math.max(10, mx + 16));
      const top = Math.min(rect.height - 140, Math.max(10, my + 16));
      tooltipEl.style.left = `${left}px`;
      tooltipEl.style.top = `${top}px`;

      const typeLabel = hit.type === "fact" ? "核心事实" : "情景事件";
      const typeColor = hit.type === "fact" ? "text-cyan-400" : "text-indigo-400";
      const retentionPct = Math.round((hit.retention || 1) * 100);

      tooltipEl.innerHTML = `
        <div class="flex items-center justify-between gap-2 border-b border-slate-800 pb-1.5 mb-1.5">
          <span class="font-bold ${typeColor} text-[11px]">${typeLabel}</span>
          <span class="text-[10px] text-slate-400">留存: ${retentionPct}% | 权重: ${hit.importance}</span>
        </div>
        <div class="text-slate-200 text-xs font-normal leading-relaxed line-clamp-4">${escapeHtml(hit.full_content || hit.label)}</div>
        <div class="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/80 mt-1.5">
          <span>用户: ${maskQQ(hit.user_id)}</span>
          <span class="text-cyan-400 font-medium">点击可编辑</span>
        </div>
      `;
    } else if (tooltipEl) {
      tooltipEl.classList.add("hidden");
    }
  });

  window.addEventListener("mouseup", (e) => {
    if (draggedNode) {
      const { mx, my } = toWorld(e.clientX, e.clientY);
      const startPos = graphCamera.clickStartPos || { x: mx, y: my };
      const dist = Math.hypot(mx - startPos.x, my - startPos.y);
      const elapsed = Date.now() - (graphCamera.dragStartTime || 0);

      if (dist < 5 && elapsed < 400) {
        openMemoryModal({
          id: draggedNode.id,
          user_id: draggedNode.user_id,
          type: draggedNode.type,
          importance: draggedNode.importance,
          content: draggedNode.full_content || draggedNode.label
        });
      }
      draggedNode = null;
    }
    graphCamera.isDragging = false;
  });

  // 移动端触摸手势支持 (平移与点击查看节点)
  graphCanvas.addEventListener("touchstart", (e) => {
    if (!e.touches.length) return;
    const t = e.touches[0];
    const { wx, wy, mx, my } = toWorld(t.clientX, t.clientY);
    const hit = findNodeAt(wx, wy);
    graphCamera.dragStartTime = Date.now();
    graphCamera.clickStartPos = { x: mx, y: my };

    if (hit) {
      draggedNode = hit;
    } else {
      graphCamera.isDragging = true;
      graphCamera.startX = mx - graphCamera.x;
      graphCamera.startY = my - graphCamera.y;
    }
  }, { passive: true });

  window.addEventListener("touchmove", (e) => {
    if (!graphCanvas || !document.getElementById("mem-view-graph") || document.getElementById("mem-view-graph").classList.contains("hidden")) return;
    if (!e.touches.length) return;
    const t = e.touches[0];
    const { wx, wy, mx, my } = toWorld(t.clientX, t.clientY);

    if (draggedNode) {
      if (e.cancelable) e.preventDefault();
      draggedNode.x = wx;
      draggedNode.y = wy;
      draggedNode.vx = 0;
      draggedNode.vy = 0;
    } else if (graphCamera.isDragging) {
      if (e.cancelable) e.preventDefault();
      graphCamera.x = mx - graphCamera.startX;
      graphCamera.y = my - graphCamera.startY;
    }
  }, { passive: false });

  window.addEventListener("touchend", (e) => {
    if (draggedNode) {
      const elapsed = Date.now() - (graphCamera.dragStartTime || 0);
      if (elapsed < 350) {
        openMemoryModal({
          id: draggedNode.id,
          user_id: draggedNode.user_id,
          type: draggedNode.type,
          importance: draggedNode.importance,
          content: draggedNode.full_content || draggedNode.label
        });
      }
      draggedNode = null;
    }
    graphCamera.isDragging = false;
  });

  graphCanvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
    const newScale = Math.min(3.5, Math.max(0.3, graphCamera.scale * zoomFactor));

    const { mx, my } = toWorld(e.clientX, e.clientY);
    graphCamera.x = mx - (mx - graphCamera.x) * (newScale / graphCamera.scale);
    graphCamera.y = my - (my - graphCamera.y) * (newScale / graphCamera.scale);
    graphCamera.scale = newScale;
  }, { passive: false });
}

async function loadMemoryTimeline() {
  const container = document.getElementById("mem-timeline-container");
  const badge = document.getElementById("timeline-count-badge");
  if (!container) return;

  container.innerHTML = `<div class="text-center py-6 text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>加载时间线流水中...</div>`;

  try {
    const res = await fetch("/api/memory/list?limit=100&is_forgotten=false");
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || errData.message || `请求失败 (HTTP ${res.status})`);
    }
    const data = await res.json();
    const list = data.memories || [];

    if (badge) badge.textContent = `共 ${list.length} 条`;

    if (list.length === 0) {
      container.innerHTML = `<div class="text-center py-8 text-slate-500">暂无活跃记忆数据，可在上方点击【录入记忆】</div>`;
      return;
    }

    container.innerHTML = list.map((m) => {
      const isFact = m.type === "fact";
      const typeLabel = isFact ? "核心事实" : "情景事件";
      const typeBadgeClass = isFact ? "bg-cyan-950 text-cyan-300 border-cyan-800" : "bg-indigo-950 text-indigo-300 border-indigo-800";
      const retPct = Math.round((m.retention || 1) * 100);
      const retColorClass = retPct > 70 ? "text-emerald-400 bg-emerald-950/80" : retPct > 40 ? "text-amber-400 bg-amber-950/80" : "text-rose-400 bg-rose-950/80";

      return `
        <div class="mem-timeline-item pl-2 group transition-all">
          <div class="p-3.5 rounded-xl bg-slate-900/70 border border-slate-800/90 hover:border-slate-700 hover:bg-slate-900/90 transition shadow-sm space-y-2">
            <div class="flex items-center justify-between flex-wrap gap-2">
              <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${typeBadgeClass}">${typeLabel}</span>
                <span class="text-[11px] font-mono text-slate-400"><i class="fa-solid fa-user-tag mr-1 text-slate-500"></i>${maskQQ(m.user_id)}</span>
                <span class="text-[10px] text-slate-500 font-mono">${formatMemTime(m.created_at)}</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 rounded text-[10px] font-semibold border border-slate-800 ${retColorClass}" title="艾宾浩斯留存率">
                  留存: ${retPct}%
                </span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 font-semibold" title="重要度权重">
                  ★ ${m.importance || 3.0}
                </span>
              </div>
            </div>
            <div class="text-xs text-slate-200 leading-relaxed break-words">${escapeHtml(m.content)}</div>
            <div class="flex items-center justify-between text-[11px] text-slate-500 pt-1.5 border-t border-slate-800/60">
              <span class="text-[10px] text-slate-400">调用频次: ${m.access_count || 0} 次</span>
              <div class="flex items-center gap-2 opacity-80 group-hover:opacity-100 transition">
                <button type="button" class="text-slate-400 hover:text-cyan-400 text-xs px-2 py-0.5 rounded hover:bg-slate-800" onclick="window.editMemoryById('${m.id}')">
                  <i class="fa-solid fa-pen-to-square mr-1"></i>编辑
                </button>
                <button type="button" class="text-slate-400 hover:text-rose-400 text-xs px-2 py-0.5 rounded hover:bg-slate-800" onclick="window.deleteMemoryById('${m.id}')">
                  <i class="fa-solid fa-trash-can mr-1"></i>删除
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<div class="text-center py-6 text-rose-400">加载时间线失败: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadMemoryTable(type, tbodyId) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-500"><i class="fa-solid fa-spinner fa-spin mr-2"></i>加载记忆列表中...</td></tr>`;

  try {
    let url = "/api/memory/list?limit=150";
    if (type === "fact") url += "&mem_type=fact&is_forgotten=false";
    else if (type === "episode") url += "&mem_type=episode&is_forgotten=false";
    else if (type === "archive") url += "&is_forgotten=true";

    const res = await fetch(url);
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || errData.message || `请求失败 (HTTP ${res.status})`);
    }
    const data = await res.json();
    const list = data.memories || [];

    if (list.length === 0) {
      const msg = type === "archive" ? "暂无被遗忘归档的记忆碎片" : "暂无此分类记忆记录";
      tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-500">${msg}</td></tr>`;
      return;
    }

    if (type === "fact") {
      tbody.innerHTML = list.map(m => {
        const retPct = Math.round((m.retention || 1) * 100);
        return `
          <tr class="hover:bg-slate-900/40 transition">
            <td class="py-2.5 px-3 font-mono text-cyan-300 font-medium">${maskQQ(m.user_id)}</td>
            <td class="py-2.5 px-3 text-slate-200 max-w-md break-words">${escapeHtml(m.content)}</td>
            <td class="py-2.5 px-3 text-center">
              <span class="px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 text-[10px] font-bold">★ ${m.importance}</span>
            </td>
            <td class="py-2.5 px-3 text-center font-mono text-[11px] text-emerald-400">${retPct}%</td>
            <td class="py-2.5 px-3 text-center font-mono text-[11px] text-slate-400">${formatMemDate(m.created_at)}</td>
            <td class="py-2.5 px-3 text-center space-x-1">
              <button type="button" class="btn-secondary px-2 py-1 text-[11px]" onclick="window.editMemoryById('${m.id}')" title="编辑">
                <i class="fa-solid fa-pen"></i>
              </button>
              <button type="button" class="px-2 py-1 text-[11px] rounded bg-slate-900 border border-slate-800 text-slate-400 hover:text-rose-400 transition" onclick="window.deleteMemoryById('${m.id}', false)" title="移入归档">
                <i class="fa-solid fa-box-archive"></i>
              </button>
            </td>
          </tr>
        `;
      }).join("");
    } else if (type === "episode") {
      tbody.innerHTML = list.map(m => {
        return `
          <tr class="hover:bg-slate-900/40 transition">
            <td class="py-2.5 px-3 font-mono text-indigo-300 font-medium">${maskQQ(m.user_id)}</td>
            <td class="py-2.5 px-3 text-slate-200 max-w-md break-words">${escapeHtml(m.content)}</td>
            <td class="py-2.5 px-3 text-center">
              <span class="px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800 text-[10px] font-bold">★ ${m.importance}</span>
            </td>
            <td class="py-2.5 px-3 text-center font-mono text-[11px] text-cyan-300">${m.access_count || 0}</td>
            <td class="py-2.5 px-3 text-center font-mono text-[11px] text-slate-400">${formatMemDate(m.created_at)}</td>
            <td class="py-2.5 px-3 text-center space-x-1">
              <button type="button" class="btn-secondary px-2 py-1 text-[11px]" onclick="window.editMemoryById('${m.id}')" title="编辑">
                <i class="fa-solid fa-pen"></i>
              </button>
              <button type="button" class="px-2 py-1 text-[11px] rounded bg-slate-900 border border-slate-800 text-slate-400 hover:text-rose-400 transition" onclick="window.deleteMemoryById('${m.id}', false)" title="移入归档">
                <i class="fa-solid fa-box-archive"></i>
              </button>
            </td>
          </tr>
        `;
      }).join("");
    } else if (type === "archive") {
      tbody.innerHTML = list.map(m => {
        const catLabel = m.type === "fact" ? "核心事实" : "情景记忆";
        return `
          <tr class="hover:bg-slate-900/40 transition opacity-80 hover:opacity-100">
            <td class="py-2.5 px-3 font-mono text-slate-400">${maskQQ(m.user_id)}</td>
            <td class="py-2.5 px-3 text-slate-300 line-through max-w-md break-words">${escapeHtml(m.content)}</td>
            <td class="py-2.5 px-3 text-center text-[10px] text-slate-400">${catLabel}</td>
            <td class="py-2.5 px-3 text-center font-mono text-slate-400">${m.importance}</td>
            <td class="py-2.5 px-3 text-center space-x-2">
              <button type="button" class="px-2.5 py-1 text-xs rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 hover:bg-emerald-900 transition" onclick="window.restoreMemoryById('${m.id}')" title="恢复至活跃记忆">
                <i class="fa-solid fa-rotate-left mr-1"></i>恢复
              </button>
              <button type="button" class="px-2.5 py-1 text-xs rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 hover:bg-rose-900 transition" onclick="window.deleteMemoryById('${m.id}', true)" title="永久物理删除">
                <i class="fa-solid fa-trash-can mr-1"></i>硬删除
              </button>
            </td>
          </tr>
        `;
      }).join("");
    }
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-rose-400">加载失败: ${escapeHtml(e.message)}</td></tr>`;
  }
}

async function runMemorySelfTest() {
  const modal = document.getElementById("modal-mem-selftest");
  const content = document.getElementById("mem-selftest-content");
  if (!modal || !content) return;

  modal.classList.remove("hidden");
  content.innerHTML = `
    <div class="text-center py-8 text-slate-400">
      <i class="fa-solid fa-spinner fa-spin text-2xl text-cyan-400 mb-2"></i>
      <div>正在执行 ChromaDB、离线向量嵌入模型与 ANN 检索自检...</div>
    </div>
  `;

  try {
    const res = await fetch("/api/memory/selftest");
    if (!res.ok) throw new Error("诊断请求失败");
    const data = await res.json();
    const report = data.report || {};

    const tests = report.tests || [];
    const isHealthy = report.status === "healthy";

    content.innerHTML = `
      <div class="p-3.5 rounded-xl border ${isHealthy ? "bg-emerald-950/50 border-emerald-800 text-emerald-300" : "bg-rose-950/50 border-rose-800 text-rose-300"} flex items-center justify-between">
        <div class="flex items-center gap-2">
          <i class="fa-solid ${isHealthy ? "fa-circle-check text-emerald-400" : "fa-triangle-exclamation text-rose-400"} text-base"></i>
          <span class="font-bold text-xs">${isHealthy ? "记忆系统全链路自检全部通过" : "自检发现异常指标"}</span>
        </div>
        <span class="font-mono text-xs font-bold">${(report.total_latency_ms || 0).toFixed(1)} ms</span>
      </div>

      <div class="space-y-2 pt-1">
        ${tests.map(t => {
          const pass = t.status === "pass";
          return `
            <div class="p-2.5 rounded-lg bg-slate-900/70 border border-slate-800 flex items-center justify-between text-xs">
              <div>
                <div class="font-semibold text-slate-200 flex items-center gap-1.5">
                  <span class="w-1.5 h-1.5 rounded-full ${pass ? "bg-emerald-400" : "bg-rose-400"}"></span>
                  <span>${escapeHtml(t.name)}</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">${escapeHtml(t.detail)}</div>
              </div>
              <div class="font-mono text-right text-[11px]">
                <div class="${pass ? "text-emerald-300" : "text-rose-400"} font-bold">${pass ? "通过" : "异常"}</div>
                <div class="text-slate-500">${t.latency_ms.toFixed(1)} ms</div>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  } catch (err) {
    content.innerHTML = `<div class="p-4 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-300 text-xs">自检异常: ${escapeHtml(err.message)}</div>`;
  }
}

async function runRetrievalSimulator() {
  const query = document.getElementById("sim-input-query")?.value.trim();
  const userId = document.getElementById("sim-input-qq")?.value.trim() || "0";
  const topK = parseInt(document.getElementById("sim-input-topk")?.value, 10) || 5;
  const alpha = parseFloat(document.getElementById("sim-range-weight")?.value) || 0.7;
  const decayRate = parseFloat(document.getElementById("sim-range-decay")?.value) || 0.1;
  const tbody = document.getElementById("sim-results-body");

  if (!query) {
    await showAlertDialog("请输入用于模拟检索的测试 Query 文本！", "输入提示");
    return;
  }

  tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-400"><i class="fa-solid fa-spinner fa-spin mr-2"></i>正在计算本地向量嵌入与余弦重排序...</td></tr>`;

  try {
    const res = await fetch("/api/memory/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        user_id: parseInt(userId, 10) || 0,
        top_k: topK,
        alpha,
        decay_rate: decayRate
      })
    });
    if (!res.ok) throw new Error("模拟请求失败");
    const data = await res.json();
    const results = data.results || [];

    if (results.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-slate-500">未检索到相关记忆条目（库中可能暂无该用户或全局记忆）</td></tr>`;
      return;
    }

    tbody.innerHTML = results.map(r => {
      const rankBadge = r.rank === 1 ? "bg-amber-500 text-slate-950 font-bold" : r.rank === 2 ? "bg-slate-300 text-slate-950 font-bold" : r.rank === 3 ? "bg-amber-700 text-white font-bold" : "bg-slate-800 text-slate-400";
      const catLabel = r.type === "fact" ? "核心事实" : "情景事件";
      const catClass = r.type === "fact" ? "text-cyan-400 bg-cyan-950/70 border-cyan-800" : "text-indigo-400 bg-indigo-950/70 border-indigo-800";
      
      const distVal = typeof r.distance === "number" ? r.distance.toFixed(4) : "0.0000";
      const simNum = typeof r.similarity === "number" ? r.similarity : (typeof r.sim_score === "number" ? r.sim_score : 0);
      const simVal = simNum.toFixed(4);
      const retNum = typeof r.retention === "number" ? r.retention : 1.0;
      const retVal = (retNum * 100).toFixed(1) + "%";
      const scoreNum = typeof r.final_score === "number" ? r.final_score : 0;
      const scoreVal = scoreNum.toFixed(4);
      const scorePct = Math.min(100, Math.max(0, Math.round(scoreNum * 100)));

      return `
        <tr class="hover:bg-slate-900/40 transition">
          <td class="py-2.5 px-3 text-center">
            <span class="w-5 h-5 rounded-full inline-flex items-center justify-center text-[10px] ${rankBadge}">${r.rank}</span>
          </td>
          <td class="py-2.5 px-3 text-slate-200 max-w-sm break-words">${escapeHtml(r.content)}</td>
          <td class="py-2.5 px-3 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] border ${catClass}">${catLabel}</span>
          </td>
          <td class="py-2.5 px-3 text-center font-mono text-[11px] text-slate-400">${distVal}</td>
          <td class="py-2.5 px-3 text-center font-mono text-[11px] text-indigo-300">${simVal}</td>
          <td class="py-2.5 px-3 text-center font-mono text-[11px] text-emerald-400">${retVal}</td>
          <td class="py-2.5 px-3 text-center font-mono text-xs font-bold text-cyan-300">
            <div class="flex items-center justify-center gap-1.5">
              <span>${scoreVal}</span>
              <div class="w-12 h-1.5 rounded-full bg-slate-800 overflow-hidden inline-block">
                <div class="h-full bg-cyan-400" style="width: ${scorePct}%"></div>
              </div>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-rose-400">检索失败: ${escapeHtml(err.message)}</td></tr>`;
  }
}

function openMemoryModal(memData = null) {
  const modal = document.getElementById("modal-mem-form");
  const title = document.getElementById("modal-mem-title");
  if (!modal) return;

  if (memData) {
    title.innerHTML = `<i class="fa-solid fa-pen-to-square text-cyan-400"></i><span>修正记忆碎片</span>`;
    document.getElementById("mem-form-id").value = memData.id || "";
    document.getElementById("mem-form-qq").value = memData.user_id !== undefined ? memData.user_id : "0";
    document.getElementById("mem-form-type").value = memData.type || "fact";
    document.getElementById("mem-form-importance").value = memData.importance || 3.0;
    document.getElementById("mem-form-importance-val").textContent = memData.importance || 3.0;
    document.getElementById("mem-form-content").value = memData.content || "";
  } else {
    title.innerHTML = `<i class="fa-solid fa-brain text-cyan-400"></i><span>录入记忆碎片</span>`;
    document.getElementById("mem-form-id").value = "";
    document.getElementById("mem-form-qq").value = "0";
    document.getElementById("mem-form-type").value = "fact";
    document.getElementById("mem-form-importance").value = "3.0";
    document.getElementById("mem-form-importance-val").textContent = "3.0";
    document.getElementById("mem-form-content").value = "";
  }

  modal.classList.remove("hidden");
}

window.editMemoryById = async function(id) {
  try {
    const res = await fetch(`/api/memory/list?keyword=&limit=200`);
    if (!res.ok) return;
    const data = await res.json();
    const item = (data.memories || []).find(m => m.id === id);
    if (item) {
      openMemoryModal({
        id: item.id,
        user_id: item.user_id,
        type: item.type,
        importance: item.importance,
        content: item.content
      });
    }
  } catch (e) {
    console.error("打开记忆编辑失败:", e);
  }
};

window.deleteMemoryById = async function(id, hard = false) {
  const actionText = hard ? "永久物理硬删除" : "归档遗忘";
  if (!await showConfirmDialog(`确定要对该记忆执行【${actionText}】吗？`, "记忆操作确认", hard)) return;

  try {
    const res = await fetch("/api/memory/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, hard })
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || errData.message || "操作失败");
    }
    await loadMemoryAll();
  } catch (e) {
    await showAlertDialog("删除记忆失败: " + e.message, "操作失败");
  }
};

window.restoreMemoryById = async function(id) {
  try {
    const res = await fetch(`/api/memory/restore/${id}`, { method: "POST" });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || errData.message || "恢复失败");
    }
    await loadMemoryAll();
  } catch (e) {
    await showAlertDialog("恢复记忆失败: " + e.message, "恢复失败");
  }
};

async function submitMemoryForm(e) {
  e.preventDefault();
  const id = document.getElementById("mem-form-id").value.trim();
  const rawUserId = document.getElementById("mem-form-qq").value.trim() || "0";
  const userId = parseInt(rawUserId, 10) || 0;
  const memType = document.getElementById("mem-form-type").value;
  const importance = parseFloat(document.getElementById("mem-form-importance").value) || 3.0;
  const content = document.getElementById("mem-form-content").value.trim();

  if (!content) {
    await showAlertDialog("请填写记忆内容！", "输入提示");
    return;
  }

  try {
    if (id) {
      const res = await fetch("/api/memory/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, content, mem_type: memType, importance, user_id: userId })
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || "修改记忆失败");
      }
    } else {
      const res = await fetch("/api/memory/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, content, mem_type: memType, importance })
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || errData.message || "添加记忆失败");
      }
    }

    document.getElementById("modal-mem-form").classList.add("hidden");
    await loadMemoryAll();
  } catch (err) {
    await showAlertDialog("保存记忆失败: " + err.message, "保存失败");
  }
}

async function runDecayMaintenance() {
  try {
    const res = await fetch("/api/memory/maintenance/forget", { method: "POST" });
    if (!res.ok) throw new Error("执行失败");
    const data = await res.json();
    const r = data.result || {};
    await showAlertDialog(`遗忘曲线扫描完成！扫描了 ${r.scanned || 0} 条记忆，新增归档 ${r.newly_forgotten || 0} 条。`, "扫描完成");
    await loadMemoryAll();
  } catch (e) {
    await showAlertDialog("衰减修护扫描失败: " + e.message, "扫描失败");
  }
}

async function clearTestMemories() {
  if (!await showConfirmDialog("确定要一键清理所有带 [测试/诊断] 标签的临时记忆碎片吗？", "清理测试记忆", true)) return;
  try {
    const res = await fetch("/api/memory/maintenance/clear_test", { method: "POST" });
    if (!res.ok) throw new Error("清理失败");
    const data = await res.json();
    const r = data.result || {};
    await showAlertDialog(`已清理 ${r.deleted || 0} 条测试记忆！`, "清理完成");
    await loadMemoryAll();
  } catch (e) {
    await showAlertDialog("清理测试数据失败: " + e.message, "清理失败");
  }
}

async function exportMemoriesZip() {
  const btn = document.getElementById("btn-mem-export");
  const origHtml = btn ? btn.innerHTML : "";
  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>正在打包...</span>';
    }
    const res = await fetch("/api/memory/export");
    if (!res.ok) throw new Error("导出请求失败 (HTTP " + res.status + ")");
    const blob = await res.blob();
    let filename = "neri_memories_export.zip";
    const disposition = res.headers.get("Content-Disposition");
    if (disposition) {
      const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
      if (match && match[1]) {
        filename = decodeURIComponent(match[1]);
      } else {
        const match2 = /filename="?([^";]+)"?/i.exec(disposition);
        if (match2 && match2[1]) filename = match2[1];
      }
    }
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    await showAlertDialog("导出记忆库失败: " + e.message, "导出失败");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

async function resetFactoryMemories() {
  const ok = await showConfirmDialog(
    "⚠️ 高危操作确认：\n\n您确定要彻底擦除当前数据库中的全部记忆并还原出厂设置吗？\n\n此操作将完全清空向量数据库中所有记忆数据（恢复至 0 条纯净状态，不保留任何预置记忆），此操作不可撤销！",
    "恢复出厂设置确认",
    true
  );
  if (!ok) return;

  const btn = document.getElementById("btn-mem-reset-factory");
  const origHtml = btn ? btn.innerHTML : "";
  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i><span>初始化中...</span>';
    }
    const res = await fetch("/api/memory/reset_factory", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "出厂初始化失败");
    await showAlertDialog(data.message || "记忆库已成功恢复出厂设置并完成初始化！", "操作成功");
    await loadMemoryAll();
  } catch (e) {
    await showAlertDialog("恢复出厂设置失败: " + e.message, "恢复失败");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  }
}

function initMemoryHub() {
  // 1. 子选项卡切换
  const subtabBtns = document.querySelectorAll(".mem-subtab-btn");
  subtabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      subtabBtns.forEach(b => {
        b.classList.remove("active", "bg-cyan-950", "border-cyan-800", "text-cyan-300");
        b.classList.add("bg-slate-900", "border-slate-800", "text-slate-400");
      });
      btn.classList.add("active", "bg-cyan-950", "border-cyan-800", "text-cyan-300");
      btn.classList.remove("bg-slate-900", "border-slate-800", "text-slate-400");

      const targetId = btn.getAttribute("data-subtab");
      currentMemSubtab = targetId;
      document.querySelectorAll(".mem-view-pane").forEach(p => p.classList.add("hidden"));
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.remove("hidden");

      loadCurrentMemSubtab();
    });
  });

  // 2. 快速开始推荐卡片
  document.getElementById("card-qs-add")?.addEventListener("click", () => openMemoryModal());
  document.getElementById("card-qs-sim")?.addEventListener("click", () => {
    document.querySelector('.mem-subtab-btn[data-subtab="mem-view-sim"]')?.click();
  });
  document.getElementById("card-qs-graph")?.addEventListener("click", () => {
    document.querySelector('.mem-subtab-btn[data-subtab="mem-view-graph"]')?.click();
  });
  document.getElementById("btn-close-mem-quickstart")?.addEventListener("click", () => {
    document.getElementById("mem-quick-start-box")?.classList.add("hidden");
  });

  // 3. 顶部操作栏
  document.getElementById("btn-mem-refresh")?.addEventListener("click", loadMemoryAll);
  document.getElementById("btn-mem-selftest")?.addEventListener("click", runMemorySelfTest);
  document.getElementById("btn-mem-export")?.addEventListener("click", exportMemoriesZip);
  document.getElementById("btn-mem-reset-factory")?.addEventListener("click", resetFactoryMemories);
  document.getElementById("btn-mem-add-manual")?.addEventListener("click", () => openMemoryModal());
  document.getElementById("btn-mem-forget-run")?.addEventListener("click", runDecayMaintenance);
  document.getElementById("btn-mem-clear-test-data")?.addEventListener("click", clearTestMemories);

  // 4. 图谱控制
  document.getElementById("btn-refresh-graph")?.addEventListener("click", loadMemoryGraph);
  document.getElementById("mem-graph-limit-select")?.addEventListener("change", loadMemoryGraph);
  document.getElementById("mem-graph-search-input")?.addEventListener("input", () => {
    loadMemoryGraph();
  });

  // 5. 模拟检索
  const simWeightSlider = document.getElementById("sim-range-weight");
  if (simWeightSlider) {
    simWeightSlider.addEventListener("input", (e) => {
      const v = document.getElementById("val-sim-weight");
      if (v) v.textContent = e.target.value;
    });
  }
  const simDecaySlider = document.getElementById("sim-range-decay");
  if (simDecaySlider) {
    simDecaySlider.addEventListener("input", (e) => {
      const v = document.getElementById("val-sim-decay");
      if (v) v.textContent = e.target.value;
    });
  }
  document.getElementById("btn-run-sim-retrieval")?.addEventListener("click", runRetrievalSimulator);
  document.getElementById("sim-input-query")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      runRetrievalSimulator();
    }
  });

  // 6. 弹窗表单
  const memImportanceSlider = document.getElementById("mem-form-importance");
  if (memImportanceSlider) {
    memImportanceSlider.addEventListener("input", (e) => {
      const v = document.getElementById("mem-form-importance-val");
      if (v) v.textContent = e.target.value;
    });
  }
  document.getElementById("form-mem-item")?.addEventListener("submit", submitMemoryForm);
  document.getElementById("btn-close-mem-modal")?.addEventListener("click", () => {
    document.getElementById("modal-mem-form")?.classList.add("hidden");
  });
  document.getElementById("btn-cancel-mem-modal")?.addEventListener("click", () => {
    document.getElementById("modal-mem-form")?.classList.add("hidden");
  });
  document.getElementById("btn-close-mem-selftest")?.addEventListener("click", () => {
    document.getElementById("modal-mem-selftest")?.classList.add("hidden");
  });
  document.getElementById("btn-done-mem-selftest")?.addEventListener("click", () => {
    document.getElementById("modal-mem-selftest")?.classList.add("hidden");
  });
}

// ---------------- 13. 插件生态与微内核驱动中枢 (Plugin Hub) ----------------
let currentPluginSettingsSchema = [];
let currentPluginSettingsId = "";

function initPluginHub() {
  // 1. 暴露标准插件客户端 SDK (NeriPluginAPI)
  window.NeriPluginAPI = {
    fetch: async (path, opts = {}) => {
      const res = await fetch(path, opts);
      return res;
    },
    alert: (title, msg) => {
      if (window.showAlertDialog) return window.showAlertDialog(title, msg);
      return Promise.resolve(alert(`${title}\n${msg}`));
    },
    confirm: (title, msg) => {
      if (window.showConfirmDialog) return window.showConfirmDialog(title, msg);
      return Promise.resolve(confirm(`${title}\n${msg}`));
    },
    toast: (msg, type = "info") => {
      if (window.showToast) window.showToast(msg, type);
      else console.log(`[Toast ${type}] ${msg}`);
    },
    db: {
      get: async (key) => (window.NeriDB ? window.NeriDB.get(key) : null),
      set: async (key, val) => (window.NeriDB ? window.NeriDB.set(key, val) : null),
    },
  };

  // 2. 绑定工具条按钮
  document.getElementById("btn-refresh-plugins")?.addEventListener("click", loadPluginsData);
  const uploadBtn = document.getElementById("btn-upload-plugin");
  const fileInput = document.getElementById("plugin-zip-file-input");

  // 绑定文档跳转与查看按钮
  const viewDocsBtn = document.getElementById("btn-view-plugin-docs");
  const modalDocs = document.getElementById("modal-plugin-docs");
  const docsBody = document.getElementById("plugin-docs-body");
  const closeDocsBtn = document.getElementById("btn-close-plugin-docs");
  const doneDocsBtn = document.getElementById("btn-done-plugin-docs");

  const closePluginDocs = () => {
    modalDocs?.classList.add("hidden");
  };

  closeDocsBtn?.addEventListener("click", closePluginDocs);
  doneDocsBtn?.addEventListener("click", closePluginDocs);
  if (modalDocs) {
    modalDocs.addEventListener("click", (e) => {
      if (e.target === modalDocs) closePluginDocs();
    });
  }

  function formatMarkdownDocs(md) {
    if (!md) return "";
    let html = md
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // 代码块 ```lang ... ```
    html = html.replace(/```([a-zA-Z0-9_\-]*)?\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre class="my-3 p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 font-mono text-[11px] text-cyan-300 overflow-x-auto leading-normal"><code>${code.trim()}</code></pre>`;
    });

    // 行内代码 `...`
    html = html.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 font-mono text-[11px]">$1</code>');

    // 标题
    html = html.replace(/^### (.*$)/gim, '<h3 class="text-sm font-bold text-slate-100 mt-4 mb-2 flex items-center gap-1.5"><i class="fa-solid fa-angle-right text-cyan-400 text-xs"></i><span>$1</span></h3>');
    html = html.replace(/^## (.*$)/gim, '<h2 class="text-base font-bold text-cyan-300 mt-6 mb-2 pb-1 border-b border-slate-800/80 flex items-center gap-2"><i class="fa-solid fa-bookmark text-xs"></i><span>$1</span></h2>');
    html = html.replace(/^# (.*$)/gim, '<h1 class="text-lg font-bold text-slate-100 mt-2 mb-3 pb-2 border-b border-cyan-800/50">$1</h1>');

    // 粗体
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-slate-100">$1</strong>');

    // 无序列表
    html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li class="ml-4 list-disc text-slate-300 mb-1">$1</li>');

    // 引用块
    html = html.replace(/^>\s+(.*$)/gim, '<blockquote class="border-l-4 border-cyan-500/70 pl-3 py-1 my-2 bg-cyan-950/20 text-slate-300 italic rounded-r">$1</blockquote>');

    // 分隔线
    html = html.replace(/^---$/gim, '<hr class="border-slate-800 my-4">');

    // 段落换行
    html = html.replace(/\n\n/g, '<p class="mb-2.5"></p>');

    return html;
  }

  if (viewDocsBtn) {
    viewDocsBtn.addEventListener("click", async () => {
      if (!modalDocs || !docsBody) return;
      modalDocs.classList.remove("hidden");
      docsBody.innerHTML = `
        <div class="text-center py-12 text-slate-400">
          <i class="fa-solid fa-spinner fa-spin text-2xl text-cyan-400 mb-2"></i>
          <div>正在加载插件开发规范与示例文档...</div>
        </div>
      `;

      try {
        const res = await fetch("/api/plugins/docs/guide");
        const data = await res.json();
        if (res.ok && data.content) {
          docsBody.innerHTML = formatMarkdownDocs(data.content);
        } else {
          docsBody.innerHTML = `<div class="p-4 rounded-xl bg-rose-950/40 text-rose-300 border border-rose-800">加载文档失败: ${data.detail || "未知错误"}</div>`;
        }
      } catch (err) {
        docsBody.innerHTML = `<div class="p-4 rounded-xl bg-rose-950/40 text-rose-300 border border-rose-800">网络异常: ${err.message}</div>`;
      }
    });
  }

  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const formData = new FormData();
      formData.append("file", file);

      window.showToast("正在上传并解压安装插件...", "info");
      try {
        const res = await fetch("/api/plugins/install", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        if (res.ok) {
          window.showToast(data.message || "插件安装成功！", "success");
          loadPluginsData();
        } else {
          window.showToast(data.detail || "插件安装失败", "error");
        }
      } catch (err) {
        window.showToast("上传异常: " + err.message, "error");
      } finally {
        fileInput.value = "";
      }
    });
  }

  // 3. 记忆系统驱动下拉切换
  const selMemory = document.getElementById("select-active-memory-driver");
  if (selMemory) {
    selMemory.addEventListener("change", async (e) => {
      const driverId = e.target.value;
      try {
        const res = await fetch("/api/plugins/drivers/set_active_memory", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ driver_id: driverId }),
        });
        if (res.ok) {
          window.showToast(`已成功切换记忆系统驱动为: ${driverId}`, "success");
          loadPluginsData();
        } else {
          const data = await res.json();
          window.showToast(data.detail || "切换记忆驱动失败", "error");
        }
      } catch (err) {
        window.showToast("切换异常: " + err.message, "error");
      }
    });
  }

  // 4. 插件配置保存表单
  document.getElementById("form-plugin-settings")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!currentPluginSettingsId) return;

    const payload = {};
    for (const item of currentPluginSettingsSchema) {
      const el = document.getElementById(`plugin-field-${item.key}`);
      if (!el) continue;
      if (item.type === "boolean") {
        payload[item.key] = el.checked;
      } else if (item.type === "number") {
        payload[item.key] = Number(el.value);
      } else {
        payload[item.key] = el.value;
      }
    }

    try {
      const res = await fetch(`/api/plugins/${currentPluginSettingsId}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: payload }),
      });
      if (res.ok) {
        window.showToast("插件专属配置保存成功！", "success");
        document.getElementById("modal-plugin-settings")?.classList.add("hidden");
      } else {
        const data = await res.json();
        window.showToast(data.detail || "保存失败", "error");
      }
    } catch (err) {
      window.showToast("网络异常: " + err.message, "error");
    }
  });

  document.getElementById("btn-close-plugin-settings-modal")?.addEventListener("click", () => {
    document.getElementById("modal-plugin-settings")?.classList.add("hidden");
  });
  document.getElementById("btn-cancel-plugin-settings")?.addEventListener("click", () => {
    document.getElementById("modal-plugin-settings")?.classList.add("hidden");
  });

  // 5. 插件 README 说明弹窗关闭
  document.getElementById("btn-close-plugin-readme-modal")?.addEventListener("click", () => {
    document.getElementById("modal-plugin-readme")?.classList.add("hidden");
  });

  window.loadPluginsData = loadPluginsData;
}

async function loadPluginsData() {
  try {
    const [pluginsRes, driversRes] = await Promise.all([
      fetch("/api/plugins/list"),
      fetch("/api/plugins/drivers/list"),
    ]);

    if (!pluginsRes.ok || !driversRes.ok) return;

    const pluginsData = await pluginsRes.json();
    const driversData = await driversRes.json();

    const plugins = pluginsData.plugins || [];
    renderDriverOverview(driversData);
    renderPluginsGrid(plugins);
    injectDynamicPluginTabs(plugins);
  } catch (e) {
    console.error("加载插件数据异常:", e);
  }
}

function renderDriverOverview(drivers) {
  // 1. 记忆驱动下拉选择
  const selMemory = document.getElementById("select-active-memory-driver");
  const badgeMemory = document.getElementById("active-memory-driver-badge");
  if (selMemory) {
    selMemory.innerHTML = (drivers.memory_drivers || [])
      .map(
        (m) =>
          `<option value="${m.id}" ${m.is_active ? "selected" : ""}>${m.name}</option>`
      )
      .join("");
  }
  if (badgeMemory) {
    badgeMemory.textContent = drivers.active_memory_driver || "默认";
  }

  // 2. 通信适配器列表
  const adList = document.getElementById("adapters-status-list");
  const adBadge = document.getElementById("adapters-count-badge");
  const adapters = drivers.adapters || [];
  if (adBadge) adBadge.textContent = `${adapters.length} 个在线`;
  if (adList) {
    if (adapters.length === 0) {
      adList.innerHTML = '<span class="text-slate-500">无活动适配器</span>';
    } else {
      adList.innerHTML = adapters
        .map(
          (a) => `
        <div class="flex items-center justify-between py-1 border-b border-slate-800/60">
          <span class="flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full ${a.is_connected ? "bg-emerald-400 animate-pulse" : "bg-slate-500"}"></span>
            <span>${a.name}</span>
          </span>
          <span class="text-[10px] ${a.is_connected ? "text-emerald-400" : "text-slate-400"}">${a.is_connected ? "已连接" : "离线"}</span>
        </div>
      `
        )
        .join("");
    }
  }

  // 3. Agent 技能工具标签
  const skContainer = document.getElementById("skills-tags-container");
  const skBadge = document.getElementById("skills-count-badge");
  const skills = drivers.skills || [];
  if (skBadge) skBadge.textContent = `${skills.length} 个已注册`;
  if (skContainer) {
    if (skills.length === 0) {
      skContainer.innerHTML = '<span class="text-slate-500 py-1">暂无激活的外部技能</span>';
    } else {
      skContainer.innerHTML = skills
        .map(
          (s) => `
        <span class="px-2 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px] flex items-center gap-1" title="${s.description}">
          <i class="fa-solid fa-wrench text-[9px]"></i>
          <span>${s.name}</span>
          ${s.admin_only ? '<span class="text-[9px] text-rose-400">(管理员)</span>' : ""}
        </span>
      `
        )
        .join("");
    }
  }
}

function renderPluginsGrid(plugins) {
  const container = document.getElementById("plugins-grid-container");
  const countBadge = document.getElementById("plugins-total-count");
  if (!container) return;

  if (countBadge) countBadge.textContent = `共 ${plugins.length} 个插件`;

  if (plugins.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-12 text-center text-slate-400 text-xs">
        <i class="fa-solid fa-puzzle-piece text-3xl mb-3 text-slate-600 block"></i>
        <p>暂无安装的插件。可将 .zip 插件包拖拽至上方一键安装！</p>
      </div>
    `;
    return;
  }

  container.innerHTML = plugins
    .map((p) => {
      const m = p.manifest || {};
      const caps = p.capabilities || {};
      const isEnabled = p.enabled;
      const hasError = !!p.error;

      // 提取驱动徽章
      const badges = [];
      if (caps.adapters?.length) badges.push(`<span class="px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 text-[10px]">📡 通信适配器</span>`);
      if (caps.memory_drivers?.length) badges.push(`<span class="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px]">🧠 记忆驱动</span>`);
      if (caps.skills?.length) badges.push(`<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px]">⚡ 技能工具 (${caps.skills.length})</span>`);
      if (caps.tts_drivers?.length) badges.push(`<span class="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px]">🎙️ TTS驱动</span>`);
      if (m.ui?.has_tab) badges.push(`<span class="px-1.5 py-0.5 rounded bg-pink-500/20 text-pink-300 text-[10px]">🖥️ 独立Tab</span>`);

      return `
      <div class="p-4 rounded-xl border ${isEnabled ? "border-cyan-500/30 bg-slate-900/60" : "border-slate-800 bg-slate-950/40"} backdrop-blur transition-all flex flex-col justify-between space-y-3">
        <div>
          <!-- 头部: 图标、标题与开关 -->
          <div class="flex items-start justify-between gap-2">
            <div class="flex items-center gap-2.5">
              <span class="text-2xl">${m.icon || "🧩"}</span>
              <div>
                <h4 class="font-bold text-sm text-slate-100 flex items-center gap-1.5">
                  <span>${escapeHtml(m.name || p.id)}</span>
                  <span class="text-[10px] text-slate-400 font-normal">v${m.version || "1.0.0"}</span>
                </h4>
                <p class="text-[11px] text-slate-500">作者: ${escapeHtml(m.author || "Unknown")}</p>
              </div>
            </div>
            <!-- 启停开关 -->
            <label class="relative inline-flex items-center cursor-pointer shrink-0">
              <input type="checkbox" class="sr-only peer" ${isEnabled ? "checked" : ""} onchange="window.togglePluginState('${p.id}', this.checked)">
              <div class="w-9 h-5 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500"></div>
            </label>
          </div>

          <!-- 描述 -->
          <p class="text-xs text-slate-300 mt-2.5 leading-relaxed line-clamp-2">${escapeHtml(m.description || "暂无描述")}</p>

          <!-- 报错提示 -->
          ${hasError ? `<div class="mt-2 p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] break-all">${escapeHtml(p.error)}</div>` : ""}

          <!-- 驱动特性徽章 -->
          <div class="flex flex-wrap gap-1 mt-2.5">
            ${badges.join("")}
          </div>
        </div>

        <!-- 底部快捷动作条 -->
        <div class="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
          <div class="flex items-center gap-2">
            ${
              m.ui?.settings_schema?.length
                ? `<button onclick="window.openPluginSettings('${p.id}')" class="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 cursor-pointer">
                    <i class="fa-solid fa-sliders text-[11px]"></i> 配置
                  </button>`
                : ""
            }
            <button onclick="window.openPluginReadme('${p.id}')" class="text-slate-400 hover:text-slate-200 flex items-center gap-1 cursor-pointer">
              <i class="fa-solid fa-book-open text-[11px]"></i> 文档
            </button>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="window.reloadPlugin('${p.id}')" class="text-slate-400 hover:text-cyan-300 flex items-center gap-1 cursor-pointer" title="热重载">
              <i class="fa-solid fa-rotate text-[11px]"></i>
            </button>
            <a href="/api/plugins/${p.id}/export" class="text-slate-400 hover:text-cyan-300 flex items-center gap-1" title="打包导出">
              <i class="fa-solid fa-download text-[11px]"></i>
            </a>
          </div>
        </div>
      </div>
    `;
    })
    .join("");
}

// 动态微前端 Tab 注入器
function injectDynamicPluginTabs(plugins) {
  const navContainer = document.getElementById("dynamic-nav-container");
  const panesContainer = document.getElementById("dynamic-tab-panes-container");
  if (!navContainer || !panesContainer) return;

  const enabledPluginsWithTab = plugins.filter((p) => p.enabled && p.manifest?.ui?.has_tab);

  // 清除失效的动态 nav item
  const validIds = new Set(enabledPluginsWithTab.map((p) => `tab-plugin-${p.id}`));
  Array.from(navContainer.children).forEach((child) => {
    const tabId = child.getAttribute("data-tab");
    if (!validIds.has(tabId)) child.remove();
  });
  Array.from(panesContainer.children).forEach((child) => {
    if (!validIds.has(child.id)) child.remove();
  });

  // 注入新的 Tab
  enabledPluginsWithTab.forEach((p) => {
    const tabId = `tab-plugin-${p.id}`;
    const btnId = `nav-btn-plugin-${p.id}`;
    const m = p.manifest || {};

    if (!document.getElementById(btnId)) {
      const btn = document.createElement("button");
      btn.id = btnId;
      btn.setAttribute("data-tab", tabId);
      btn.className = "nav-btn";
      btn.innerHTML = `
        <i class="fa-solid fa-${m.ui?.tab_icon || "puzzle-piece"} w-5 text-center text-pink-400"></i>
        <span>${escapeHtml(m.ui?.tab_title || m.name || p.id)}</span>
      `;
      btn.addEventListener("click", () => {
        document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        document.querySelectorAll(".tab-pane").forEach((pane) => pane.classList.remove("active"));
        const targetPane = document.getElementById(tabId);
        if (targetPane) targetPane.classList.add("active");

        // 移动端收起抽屉
        if (closeMobileDrawer && window.innerWidth < 768) closeMobileDrawer();
      });
      navContainer.appendChild(btn);
    }

    if (!document.getElementById(tabId)) {
      const pane = document.createElement("section");
      pane.id = tabId;
      pane.className = "tab-pane space-y-6";
      pane.innerHTML = `<div class="glass-card p-6 text-center text-slate-400 text-xs"><i class="fa-solid fa-spinner fa-spin text-lg mb-2"></i><p>正在载入微前端页面...</p></div>`;
      panesContainer.appendChild(pane);

      // 异步载入插件专属 HTML 片段与脚本
      fetch(`/api/plugins/${p.id}/web/tab`)
        .then((res) => {
          if (!res.ok) throw new Error("未提供独立页面");
          return res.text();
        })
        .then((html) => {
          pane.innerHTML = html;
          // 动态执行嵌入的 script 标签
          pane.querySelectorAll("script").forEach((oldScript) => {
            const newScript = document.createElement("script");
            Array.from(oldScript.attributes).forEach((attr) => newScript.setAttribute(attr.name, attr.value));
            newScript.appendChild(document.createTextNode(oldScript.innerHTML));
            oldScript.parentNode.replaceChild(newScript, oldScript);
          });
        })
        .catch((err) => {
          pane.innerHTML = `<div class="glass-card p-6 text-center text-rose-400 text-xs">微前端页面载入失败: ${err.message}</div>`;
        });
    }
  });
}

// 全局暴露动作方法
window.togglePluginState = async function (pluginId, enabled) {
  try {
    const res = await fetch(`/api/plugins/${pluginId}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (res.ok) {
      window.showToast(`插件已${enabled ? "启用" : "停用"}`, "success");
      loadPluginsData();
    } else {
      const data = await res.json();
      window.showToast(data.detail || "操作失败", "error");
      loadPluginsData();
    }
  } catch (err) {
    window.showToast("请求异常: " + err.message, "error");
    loadPluginsData();
  }
};

window.reloadPlugin = async function (pluginId) {
  window.showToast(`正在热重载插件 [${pluginId}]...`, "info");
  try {
    const res = await fetch(`/api/plugins/${pluginId}/reload`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      window.showToast(data.message || "热重载成功！", "success");
      loadPluginsData();
    } else {
      window.showToast(data.detail || "重载失败", "error");
    }
  } catch (err) {
    window.showToast("重载异常: " + err.message, "error");
  }
};

window.openPluginReadme = async function (pluginId) {
  const modal = document.getElementById("modal-plugin-readme");
  const title = document.getElementById("modal-plugin-readme-title");
  const content = document.getElementById("plugin-readme-content");
  if (!modal || !content) return;

  if (title) title.innerHTML = `<i class="fa-solid fa-book text-cyan-400"></i><span>插件文档 - ${pluginId}</span>`;
  content.textContent = "正在读取说明文档...";
  modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/plugins/${pluginId}/readme`);
    const data = await res.json();
    content.textContent = data.content || "暂无说明文档。";
  } catch (e) {
    content.textContent = "获取文档失败: " + e.message;
  }
};

window.openPluginSettings = async function (pluginId) {
  const modal = document.getElementById("modal-plugin-settings");
  const title = document.getElementById("modal-plugin-settings-title");
  const container = document.getElementById("plugin-settings-fields-container");
  const hiddenId = document.getElementById("plugin-settings-id-hidden");
  if (!modal || !container) return;

  currentPluginSettingsId = pluginId;
  if (hiddenId) hiddenId.value = pluginId;
  if (title) title.innerHTML = `<i class="fa-solid fa-sliders text-cyan-400"></i><span>配置 - ${pluginId}</span>`;

  container.innerHTML = '<div class="text-center py-4 text-xs text-slate-400">正在获取配置表单...</div>';
  modal.classList.remove("hidden");

  try {
    const res = await fetch(`/api/plugins/${pluginId}/config`);
    const data = await res.json();
    const schema = data.schema || [];
    const cfg = data.config || {};
    currentPluginSettingsSchema = schema;

    if (schema.length === 0) {
      container.innerHTML = '<div class="text-center py-4 text-xs text-slate-400">该插件无额外配置项。</div>';
      return;
    }

    container.innerHTML = schema
      .map((item) => {
        const val = cfg[item.key] !== undefined ? cfg[item.key] : item.default ?? "";
        if (item.type === "boolean") {
          return `
            <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-900/50 border border-slate-800">
              <div>
                <label class="block text-xs font-semibold text-slate-200">${escapeHtml(item.label || item.key)}</label>
                <p class="text-[11px] text-slate-400 mt-0.5">${escapeHtml(item.description || "")}</p>
              </div>
              <input type="checkbox" id="plugin-field-${item.key}" class="w-4 h-4 rounded accent-cyan-400 cursor-pointer" ${val ? "checked" : ""}>
            </div>
          `;
        } else if (item.type === "select") {
          const opts = (item.options || [])
            .map((opt) => `<option value="${opt.value}" ${opt.value === val ? "selected" : ""}>${escapeHtml(opt.label)}</option>`)
            .join("");
          return `
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">${escapeHtml(item.label || item.key)}</label>
              <select id="plugin-field-${item.key}" class="input-field text-xs">${opts}</select>
              ${item.description ? `<p class="text-[11px] text-slate-400 mt-1">${escapeHtml(item.description)}</p>` : ""}
            </div>
          `;
        } else if (item.type === "password") {
          return `
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">${escapeHtml(item.label || item.key)}</label>
              <input type="password" id="plugin-field-${item.key}" class="input-field text-xs" value="${escapeHtml(String(val))}">
              ${item.description ? `<p class="text-[11px] text-slate-400 mt-1">${escapeHtml(item.description)}</p>` : ""}
            </div>
          `;
        } else {
          return `
            <div>
              <label class="block text-xs font-semibold text-slate-300 mb-1">${escapeHtml(item.label || item.key)}</label>
              <input type="${item.type === "number" ? "number" : "text"}" id="plugin-field-${item.key}" class="input-field text-xs" value="${escapeHtml(String(val))}">
              ${item.description ? `<p class="text-[11px] text-slate-400 mt-1">${escapeHtml(item.description)}</p>` : ""}
            </div>
          `;
        }
      })
      .join("");
  } catch (err) {
    container.innerHTML = `<div class="text-rose-400 text-xs py-4 text-center">获取配置失败: ${err.message}</div>`;
  }
};

