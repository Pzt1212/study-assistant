/* ============================================================
   计时器逻辑
   - 秒表：开始 / 暂停 / 继续 / 清零（基于时间戳累计，精确计时）
   - 倒计时：自定义分钟数，结束播放提示音
   ============================================================ */
(function () {
  "use strict";

  /* ================= 秒表 ================= */
  var swDisplay = document.getElementById("stopwatch-display");
  var swProgress = document.getElementById("stopwatch-progress");
  var swStart = document.getElementById("sw-start");
  var swPause = document.getElementById("sw-pause");
  var swReset = document.getElementById("sw-reset");

  var CIRC = 552.9;            // 圆周长
  var swElapsed = 0;           // 已累计毫秒
  var swRunning = false;
  var swTimerId = null;
  var swLast = 0;              // 上次 tick 时间戳

  function swFormat(ms) {
    var totalTenths = Math.floor(ms / 100);
    var m = Math.floor(totalTenths / 600);
    var s = Math.floor((totalTenths % 600) / 10);
    var t = totalTenths % 10;
    return (
      String(m).padStart(2, "0") + ":" +
      String(s).padStart(2, "0") + "." + t
    );
  }

  function swRender() {
    swDisplay.textContent = swFormat(swElapsed);
    // 圆环：以 1 小时为一圈
    var ratio = Math.min(1, swElapsed / 3600000);
    swProgress.style.strokeDashoffset = String(CIRC * (1 - ratio));
  }

  function swTick() {
    var now = Date.now();
    swElapsed += now - swLast;
    swLast = now;
    swRender();
  }

  function swStartTimer() {
    if (swRunning) return;
    swRunning = true;
    swLast = Date.now();
    swTimerId = setInterval(swTick, 100);
    swStart.disabled = true;
    swPause.disabled = false;
    swReset.disabled = false;
  }

  function swPauseTimer() {
    if (!swRunning) return;
    swRunning = false;
    clearInterval(swTimerId);
    swTimerId = null;
    swStart.disabled = false;
    swStart.textContent = "继续";
    swPause.disabled = true;
  }

  function swResetTimer() {
    swRunning = false;
    clearInterval(swTimerId);
    swTimerId = null;
    swElapsed = 0;
    swRender();
    swStart.disabled = false;
    swStart.textContent = "开始";
    swPause.disabled = true;
    swReset.disabled = true;
  }

  /* ================= 倒计时 ================= */
  var cdDisplay = document.getElementById("countdown-display");
  var cdProgress = document.getElementById("countdown-progress");
  var cdStart = document.getElementById("cd-start");
  var cdPause = document.getElementById("cd-pause");
  var cdReset = document.getElementById("cd-reset");
  var cdMinutesInput = document.getElementById("cd-minutes");

  var cdTotal = 5 * 60;        // 总秒数
  var cdRemaining = 5 * 60;    // 剩余秒数
  var cdRunning = false;
  var cdTimerId = null;
  var cdEndAt = 0;             // 截止时间戳

  function cdSetTotal() {
    var mins = parseInt(cdMinutesInput.value, 10) || 5;
    mins = Math.min(999, Math.max(1, mins));
    cdTotal = mins * 60;
    cdRemaining = cdTotal;
  }

  function cdRender() {
    var m = String(Math.floor(cdRemaining / 60)).padStart(2, "0");
    var s = String(cdRemaining % 60).padStart(2, "0");
    cdDisplay.textContent = m + ":" + s;
    var ratio = cdTotal > 0 ? cdRemaining / cdTotal : 0;
    cdProgress.style.strokeDashoffset = String(CIRC * (1 - ratio));
  }

  function cdTick() {
    if (!cdRunning) return;
    // 按真实时间差计算（后台节流导致 interval 变慢/暂停时自动追平）
    cdRemaining = Math.max(0, Math.ceil((cdEndAt - Date.now()) / 1000));
    if (cdRemaining <= 0) {
      cdRemaining = 0;
      cdRender();
      playBeep([880, 660, 880, 1100]); // 结束提示音
      cdStop();
      return;
    }
    cdRender();
  }

  function cdStop() {
    cdRunning = false;
    clearInterval(cdTimerId);
    cdTimerId = null;
    cdEndAt = 0;
    cdStart.disabled = false;
    cdStart.textContent = "开始";
    cdPause.disabled = true;
  }

  function cdStartTimer() {
    if (cdRunning) return;
    if (cdRemaining <= 0) {
      cdSetTotal(); // 结束后再次开始则重新载入
    }
    cdRunning = true;
    cdEndAt = Date.now() + cdRemaining * 1000;
    cdTimerId = setInterval(cdTick, 1000);
    cdStart.disabled = true;
    cdStart.textContent = "计时中";
    cdPause.disabled = false;
    cdReset.disabled = false;
  }

  function cdPauseTimer() {
    if (!cdRunning) return;
    // 暂停时把剩余时间对齐到真实值
    cdRemaining = Math.max(0, Math.ceil((cdEndAt - Date.now()) / 1000));
    cdRunning = false;
    clearInterval(cdTimerId);
    cdTimerId = null;
    cdEndAt = 0;
    cdStart.disabled = false;
    cdStart.textContent = "继续";
    cdPause.disabled = true;
    cdRender();
  }

  function cdResetTimer() {
    cdStop();
    cdSetTotal();
    cdRender();
    cdReset.disabled = true;
  }

  /* ================= 事件绑定 ================= */
  swStart.addEventListener("click", swStartTimer);
  swPause.addEventListener("click", swPauseTimer);
  swReset.addEventListener("click", swResetTimer);

  cdStart.addEventListener("click", cdStartTimer);
  cdPause.addEventListener("click", cdPauseTimer);
  cdReset.addEventListener("click", cdResetTimer);

  // 从后台标签切回时立即追平显示（时间戳驱动，不受浏览器节流影响）
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) return;
    if (swRunning) swTick();
    if (cdRunning) cdTick();
  });

  // 初始化倒计时显示
  cdRender();
})();
