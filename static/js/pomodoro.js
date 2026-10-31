/* ============================================================
   番茄钟逻辑
   - 三种模式：focus(专注) / short_break(短休息) / long_break(长休息)
   - 时长可自定义并保存到 localStorage
   - 倒计时驱动 SVG 圆环进度
   - 完成后播放提示音；专注完成则上报后端记录并刷新今日统计
   ============================================================ */
(function () {
  "use strict";

  // ---------- DOM 引用 ----------
  var display = document.getElementById("timer-display");
  var progressCircle = document.getElementById("timer-progress");
  var modeButtons = document.querySelectorAll(".mode-btn");
  var btnStart = document.getElementById("btn-start");
  var btnPause = document.getElementById("btn-pause");
  var btnReset = document.getElementById("btn-reset");
  var btnApply = document.getElementById("btn-apply-settings");
  var todayCountEl = document.getElementById("today-count");

  // ---------- 状态 ----------
  var CIRCUMFERENCE = 552.9; // SVG 圆周长（与 CSS 中一致）
  var mode = "focus";                       // 当前模式
  var durations = { focus: 25, short_break: 5, long_break: 15 }; // 单位：分钟
  var totalSeconds = 25 * 60;               // 当前模式总秒数
  var remaining = totalSeconds;             // 剩余秒数
  var timerId = null;                       // setInterval 句柄
  var endAt = 0;                            // 运行截止时间戳（Date.now()）
  var running = false;

  // ---------- 初始化 ----------
  function init() {
    loadSettings();
    switchMode("focus");
    bindEvents();
  }

  // 从 localStorage 读取自定义时长（JSON）
  function loadSettings() {
    try {
      var saved = JSON.parse(localStorage.getItem("pomodoro_durations") || "{}");
      if (saved.focus) durations.focus = parseInt(saved.focus, 10) || 25;
      if (saved.short_break) durations.short_break = parseInt(saved.short_break, 10) || 5;
      if (saved.long_break) durations.long_break = parseInt(saved.long_break, 10) || 15;
    } catch (e) { /* 解析失败则使用默认值 */ }
    document.getElementById("setting-focus").value = durations.focus;
    document.getElementById("setting-short").value = durations.short_break;
    document.getElementById("setting-long").value = durations.long_break;
  }

  // 保存自定义时长到 localStorage
  function saveSettings() {
    localStorage.setItem("pomodoro_durations", JSON.stringify(durations));
  }

  // ---------- 计时核心 ----------
  function switchMode(newMode) {
    stopTimer();
    mode = newMode;
    totalSeconds = durations[newMode] * 60;
    remaining = totalSeconds;
    updateDisplay();

    // 高亮当前模式按钮
    modeButtons.forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
    setControls(false);
  }

  function startTimer() {
    if (running) return;
    if (remaining <= 0) remaining = totalSeconds; // 结束时再次开始则重置
    running = true;
    // 以时间戳驱动：浏览器后台节流 setInterval 时，恢复后仍按真实剩余时间显示
    endAt = Date.now() + remaining * 1000;
    timerId = setInterval(tick, 1000);
    setControls(true);
  }

  function pauseTimer() {
    // 暂停时先把 remaining 对齐到真实剩余
    remaining = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
    running = false;
    clearInterval(timerId);
    timerId = null;
    setControls(false);
    updateDisplay();
  }

  function resetTimer() {
    stopTimer();
    remaining = totalSeconds;
    updateDisplay();
    setControls(false);
  }

  function stopTimer() {
    running = false;
    clearInterval(timerId);
    timerId = null;
    endAt = 0;
  }

  function tick() {
    if (!running) return;
    // 按真实时间差计算剩余（自动纠正后台节流造成的累计误差）
    remaining = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
    if (remaining <= 0) {
      remaining = 0;
      updateDisplay();
      playBeep([880, 660, 880, 1100]); // 完成提示音
      stopTimer();
      setControls(false);              // 复位按钮状态，允许再次开始
      onComplete();
      return;
    }
    updateDisplay();
  }

  // 更新显示：文本 + 圆环进度
  function updateDisplay() {
    var mm = String(Math.floor(remaining / 60)).padStart(2, "0");
    var ss = String(remaining % 60).padStart(2, "0");
    display.textContent = mm + ":" + ss;

    var ratio = totalSeconds > 0 ? remaining / totalSeconds : 0;
    progressCircle.style.strokeDashoffset = String(CIRCUMFERENCE * (1 - ratio));
  }

  // 完成回调：专注模式上报后端
  function onComplete() {
    if (mode === "focus") {
      fetch("/pomodoro/record", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: mode, duration_seconds: totalSeconds })
      })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
          if (data.ok && todayCountEl) {
            todayCountEl.textContent = data.today_focus;
          }
        })
        .catch(function () { /* 网络失败静默 */ });
    }
  }

  // 控制按钮状态
  function setControls(isRunning) {
    btnStart.disabled = isRunning;
    btnPause.disabled = !isRunning;
    btnReset.disabled = !(isRunning || remaining !== totalSeconds);
  }

  // ---------- 事件绑定 ----------
  function bindEvents() {
    modeButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        switchMode(btn.dataset.mode);
      });
    });
    btnStart.addEventListener("click", startTimer);
    btnPause.addEventListener("click", pauseTimer);
    btnReset.addEventListener("click", resetTimer);

    btnApply.addEventListener("click", function () {
      var f = parseInt(document.getElementById("setting-focus").value, 10) || 25;
      var s = parseInt(document.getElementById("setting-short").value, 10) || 5;
      var l = parseInt(document.getElementById("setting-long").value, 10) || 15;
      // 数值范围限制
      durations.focus = Math.min(120, Math.max(1, f));
      durations.short_break = Math.min(30, Math.max(1, s));
      durations.long_break = Math.min(60, Math.max(1, l));
      saveSettings();
      // 若正停留在某模式，重新按新时长加载
      switchMode(mode);
    });
  }

  // 从后台标签切回时立即按时间戳刷新（不受节流影响）
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && running) tick();
  });

  init();
})();
