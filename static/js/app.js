/* ============================================================
   学习助手 - 全局工具脚本
   ============================================================ */

// ---------- 前台侧栏开合（移动端抽屉） ----------
document.addEventListener("DOMContentLoaded", function () {
  var side = document.getElementById("appSide");
  var backdrop = document.getElementById("sideBackdrop");
  var menuBtn = document.getElementById("sideMenuBtn");

  function openSide() {
    if (!side || !backdrop) return;
    side.classList.add("is-open");
    backdrop.classList.add("is-show");
    document.body.style.overflow = "hidden";
  }
  function closeSide() {
    if (!side || !backdrop) return;
    side.classList.remove("is-open");
    backdrop.classList.remove("is-show");
    document.body.style.overflow = "";
  }
  if (menuBtn) menuBtn.addEventListener("click", function () {
    if (side && side.classList.contains("is-open")) closeSide();
    else openSide();
  });
  if (backdrop) backdrop.addEventListener("click", closeSide);
  if (side) {
    side.addEventListener("click", function (e) {
      if (e.target.closest("a")) closeSide();
    });
  }
});

// ---------- 删除确认（配合 data-confirm 属性） ----------
document.addEventListener("submit", function (event) {
  var form = event.target;
  var message = form.getAttribute("data-confirm");
  if (message && !window.confirm(message)) {
    event.preventDefault(); // 用户取消，阻止提交
  }
});

// ---------- Flash 消息自动消失（6 秒后淡出） ----------
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".flash").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.6s ease";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 700);
    }, 6000);
  });
});

// ---------- 提示音（Web Audio 生成，无需音频文件） ----------
function playBeep(sequence) {
  // sequence 为频率数组，例如 [880, 660, 880]
  try {
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    var ctx = new AudioCtx();
    var tones = sequence || [880, 660, 880];
    tones.forEach(function (freq, i) {
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = freq;
      var start = ctx.currentTime + i * 0.18;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
      osc.start(start);
      osc.stop(start + 0.18);
    });
  } catch (e) {
    // 浏览器不支持 Web Audio 时静默失败
  }
}
