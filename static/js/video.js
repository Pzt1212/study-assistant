/* ============================================================
   学习助手 - 视频播放 + 后台播放浮窗
   - 解析 B站链接 → 官方 iframe 播放器
   - 本地 video/downloads 视频直接播放
   - 后台播放：记录真实播放进度，切到其它页面时右下角浮窗精确续播
   ============================================================ */
(function () {
  "use strict";

  var LS_KEY = "sa_video_background";   // {kind:'bili'|'local', title, page, file?, time?}
  var MINI_ID = "sa-mini-player";

  function $(id) { return document.getElementById(id); }
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
  /* file 可能是子目录相对路径（含 /），逐段编码避免整体 %2F 导致 404 */
  function fileUrl(file) {
    return String(file || "").split("/").map(encodeURIComponent).join("/");
  }

  /* ---------- 主播放器（视频页内） ---------- */
  var wrap = $("video-player-wrap"), player = $("video-player");

  function showBili(info) {
    if (!wrap || !player) return;
    stopActiveBg();
    wrap.hidden = false;
    player.innerHTML = '<iframe src="' + esc(info.embed_url) + '" scrolling="no" border="0" '
      + 'frameborder="no" framespacing="0" allowfullscreen="true" '
      + 'style="width:100%;height:100%"></iframe>';
    $("video-title").textContent = info.title || "";
    $("video-author").textContent = info.author ? ("作者：" + info.author) : "";
    revealPlayer();
  }

  function showLocal(file, title) {
    if (!wrap || !player) return;
    stopActiveBg();
    wrap.hidden = false;
    player.innerHTML = '<video controls autoplay src="' + esc("/video/files/" + fileUrl(file))
      + '" style="width:100%;height:100%"></video>';
    $("video-title").textContent = title || file;
    $("video-author").textContent = "本地视频";
    revealPlayer();
  }

  /* 播放器被新视频激活：滚动到可视处并给一次短暂高亮，提示已切换 */
  function revealPlayer() {
    if (!wrap) return;
    wrap.classList.remove("player-flash");
    void wrap.offsetWidth;               // 重置动画
    wrap.classList.add("player-flash");
    try { wrap.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
  }

  function fail(msg) {
    var e = $("video-error");
    if (!e) return;
    e.hidden = false;
    e.textContent = msg;
    setTimeout(function () { e.hidden = true; }, 6000);
  }

  /* ---------- 解析 B 站链接 ---------- */
  var form = $("video-form");
  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var url = $("video-url").value.trim();
      if (!url) return;
      fetch("/video/api/resolve?url=" + encodeURIComponent(url))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { fail(d.error || "解析失败"); return; }
          showBili(d.video);
        })
        .catch(function () { fail("网络错误，请重试"); });
    });
  }

  /* ---------- 本地视频 ---------- */
  document.querySelectorAll(".js-play-local").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var card = btn.closest(".portal-card");
      if (!card) return;
      showLocal(card.dataset.file, card.dataset.title);
    });
  });

  /* 点击卡片任意位置（封面/三角/标题区）也可播放；按钮由上方单独处理 */
  document.querySelectorAll(".portal-card.js-local-card").forEach(function (card) {
    card.addEventListener("click", function (ev) {
      if (ev.target.closest("button")) return;
      if (!card.dataset.file) return;
      showLocal(card.dataset.file, card.dataset.title);
    });
  });

  /* 封面帧缩略图：进入视口才请求，避免首屏同时抽 40+ 张帧 */
  function loadThumb(im) {
    var f = im.getAttribute("data-file");
    if (!f) return;
    im.src = "/video/thumb?file=" + encodeURIComponent(f);
  }
  var thImgs = document.querySelectorAll(".video-cover img.vthumb[data-file]");
  if (thImgs.length) {
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) { loadThumb(en.target); io.unobserve(en.target); }
        });
      }, { rootMargin: "240px" });
      thImgs.forEach(function (im) { io.observe(im); });
    } else {
      thImgs.forEach(loadThumb);
    }
  }

  /* ---------- 后台播放：真实进度记忆 + 浮窗精确续播 ---------- */

  // 每 4 秒把“正在播放的本地视频”当前进度写回 localStorage，
  // 保证切到任意页面都能从真实位置接续（而非点按钮那一刻的快照）。
  var saveTimer = null;
  function stopTicker() {
    if (saveTimer) { clearInterval(saveTimer); saveTimer = null; }
  }
  function saveTick() {
    var data = null;
    try { data = JSON.parse(localStorage.getItem(LS_KEY) || "null"); } catch (e) { data = null; }
    if (!data || data.kind !== "local") { stopTicker(); return; }
    var src = null;
    var m = document.getElementById(MINI_ID);
    if (m) {
      var cv = m.querySelector("video");
      if (cv && !cv.paused && isFinite(cv.currentTime)) src = cv;
    }
    if (!src && player) {
      var mv = player.querySelector("video");
      if (mv && !mv.paused && isFinite(mv.currentTime)) src = mv;
    }
    if (src) {
      try {
        data.time = Math.max(0, src.currentTime);
        localStorage.setItem(LS_KEY, JSON.stringify(data));
      } catch (e) {}
    }
  }
  function startTicker() {
    if (!saveTimer) saveTimer = setInterval(saveTick, 4000);
  }

  var bgBtn = $("btn-background");
  /* 用户在主播放器显式换台时：结束旧的跨页后台播放（浮窗/记忆/计时），避免双音或串台 */
  function stopActiveBg() {
    var m = document.getElementById(MINI_ID);
    if (m) m.remove();
    try { localStorage.removeItem(LS_KEY); } catch (e) {}
    stopTicker();
    setBgIdle();
  }
  function setBgActive() {
    if (!bgBtn) return;
    bgBtn.classList.add("bg-active");
    var lb = $("bg-label");
    if (lb) lb.textContent = "后台播放中 · 切页自动续播";
  }
  function setBgIdle() {
    if (!bgBtn) return;
    bgBtn.classList.remove("bg-active");
    var lb = $("bg-label");
    if (lb) lb.textContent = "▶ 后台播放 · 切页续播";
  }
  if (bgBtn) {
    bgBtn.addEventListener("click", function () {
      var iframe = player && player.querySelector("iframe");
      var video = player && player.querySelector("video");
      if (iframe) {
        // B站：记录官方播放页链接（跨页 iframe 续播；进度由 B站自身记忆）
        var src = iframe.src;
        var bvidMatch = src.match(/bvid=([A-Za-z0-9]+)/);
        var page = src.match(/[?&]page=(\d+)/);
        if (bvidMatch) {
          localStorage.setItem(LS_KEY, JSON.stringify({
            kind: "bili", title: $("video-title").textContent || "",
            page: page ? page[1] : "1", bvid: bvidMatch[1],
          }));
          spawnMini();
          setBgActive();
        }
      } else if (video) {
        var srcv = video.currentSrc || video.src;
        localStorage.setItem(LS_KEY, JSON.stringify({
          kind: "local", title: $("video-title").textContent || "",
          file: decodeURIComponent(srcv.split("/files/")[1] || ""),
          time: Math.max(0, video.currentTime || 0),
        }));
        spawnMini();
        setBgActive();
        startTicker();
      }
    });
  }

  /* 当前页主播放器是否正在出声（用于避免同页双音：此时浮窗静音占位） */
  function mainAudibleNow() {
    if (!player) return false;
    var v = player.querySelector("video");
    if (v && !v.paused && !v.muted && v.volume > 0) return true;
    var f = player.querySelector("iframe");
    if (f && f.getAttribute("src")) return true;   // B站 iframe 视为出声
    return false;
  }

  /* ---------- 跨页后台播放浮窗（任何登录页都会加载 video.js 时检测） ---------- */
  function spawnMini() {
    var data;
    try { data = JSON.parse(localStorage.getItem(LS_KEY) || "null"); } catch (e) { data = null; }
    if (!data) return;
    if (document.getElementById(MINI_ID)) return;

    var mini = document.createElement("div");
    mini.id = MINI_ID;
    mini.className = "mini-player";
    mini.innerHTML =
      '<div class="mini-head">' +
      '  <span class="mini-title"></span>' +
      '  <button type="button" class="mini-close" aria-label="关闭后台播放">&#10005;</button>' +
      '</div>' +
      '<div class="mini-body"></div>';
    mini.querySelector(".mini-title").textContent = data.title || "视频";

    var body = mini.querySelector(".mini-body");
    if (data.kind === "bili") {
      var page = data.page || "1";
      body.innerHTML = '<iframe src="https://player.bilibili.com/player.html?bvid=' +
        encodeURIComponent(data.bvid) + '&page=' + encodeURIComponent(page) +
        '&high_quality=1&danmaku=1&autoplay=1" frameborder="0" '
        + 'allowfullscreen="true" style="width:100%;height:100%"></iframe>';
    } else if (data.kind === "local") {
      var ctrl = document.createElement("video");
      ctrl.controls = true;
      ctrl.autoplay = true;
      // 同页主播放器正在出声 → 浮窗静音，避免双重声音；切到其它页面后重新生成即有声
      ctrl.muted = mainAudibleNow();
      ctrl.src = "/video/files/" + fileUrl(data.file || "");
      ctrl.style.width = "100%";
      ctrl.style.height = "100%";
      var seeked = false;
      var tryPlay = function () {
        var pr = ctrl.play();
        if (pr && pr.catch) pr.catch(function () { /* 浏览器拦截自动播放：控件可手动点 */ });
      };
      ctrl.addEventListener("loadedmetadata", function () {
        if (data.time > 0 && !seeked) {
          seeked = true;
          try { ctrl.currentTime = data.time; } catch (e) {}
        }
        tryPlay();
      });
      // 若自动播放被策略拦截，用户任意一次点击即尝试续播
      if (!ctrl.muted) {
        document.addEventListener("pointerdown", tryPlay, { once: true });
      }
      body.appendChild(ctrl);
    }

    mini.querySelector(".mini-close").addEventListener("click", function () {
      localStorage.removeItem(LS_KEY);
      mini.remove();
      stopTicker();
      setBgIdle();
    });
    document.body.appendChild(mini);
    // 浮窗存在即持续回写进度（任意页面都生效）
    if (data && data.kind === "local") startTicker();
  }

  // 离开页面瞬间把最新进度冲刷进 localStorage（切页时最多落后 ~1 次 tick）
  window.addEventListener("pagehide", saveTick);

  // 任意登录页面加载即检测
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", spawnMini);
  } else {
    spawnMini();
  }
})();
