/* ============================================================
   背景音乐播放器（升级版）
   - 曲目来源两类：
       * stream（在线流媒体）：<audio> 播放远程 mp3 直链
       * binaural（脑波音频）：Web Audio 双振荡器左右声道合成
         （base 载波 / beat 频率差 → 双耳节拍），离线可播
   - 分类筛选 chips + 客户端搜索
   - 交互保持：播放/暂停、上一首/下一首、音量、循环（off/all/one）
   - 在线曲目加载失败给出友好提示
   ============================================================ */
(function () {
  "use strict";

  // ---------- DOM ----------
  var audio = document.getElementById("audio-player");
  var playlist = document.getElementById("playlist");
  var btnPlay = document.getElementById("btn-play");
  var btnPrev = document.getElementById("btn-prev");
  var btnNext = document.getElementById("btn-next");
  var volumeSlider = document.getElementById("volume-slider");
  var loopBtn = document.getElementById("loop-btn");
  var progressFill = document.getElementById("progress-fill");
  var progressBar = document.getElementById("progress-bar");
  var timeCurrent = document.getElementById("time-current");
  var timeDuration = document.getElementById("time-duration");
  var musicTitle = document.getElementById("music-title");
  var musicArtist = document.getElementById("music-artist");
  var musicKind = document.getElementById("music-kind");
  var musicKindDesc = document.getElementById("music-kind-desc");
  var musicError = document.getElementById("music-error");
  var catChipsBox = document.getElementById("music-cat-chips");
  var searchInput = document.getElementById("music-search");

  // ---------- 状态 ----------
  var allTracks = window.TRACKS || [];
  var visibleTracks = [];
  var currentIndex = -1;
  var categoryFilter = "";
  var searchKeyword = "";
  var loopMode = localStorage.getItem("music_loop") || "off"; // off/all/one

  // ---------- 脑波引擎（Web Audio 合成） ----------
  var brainCtx = null;      // AudioContext
  var brainMaster = null;   // 主增益（音量）
  var brainNodes = [];      // 当前 oscillator/gain/panner 集合

  // ---------- 工具 ----------
  function formatTime(sec) {
    if (!isFinite(sec)) return "--:--";
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  function getKindLabel(track) {
    return track.kind === "binaural"
      ? { base: "脑波音频", desc: track.desc || "双耳节拍 · 建议戴耳机" }
      : { base: "在线轻音乐", desc: "在线流式音频 · " + (track.artist || "在线源") };
  }

  function currentTrack() {
    return visibleTracks[currentIndex] || null;
  }

  // ---------- 分类与搜索过滤 ----------
  function applyFilter() {
    var kw = searchKeyword.trim().toLowerCase();
    visibleTracks = allTracks.filter(function (t) {
      if (categoryFilter && t.category !== categoryFilter) return false;
      if (kw) {
        var hay = (t.name + " " + (t.artist || "") + " " + (t.desc || "")).toLowerCase();
        if (hay.indexOf(kw) === -1) return false;
      }
      return true;
    });
    // 保持当前播放项尽量可用
    if (currentIndex >= 0 && visibleTracks.indexOf(allTracks[currentIndex]) === -1) {
      stopPlayback();
      currentIndex = -1;
    }
    renderPlaylist();
  }

  // ---------- 播放列表渲染 ----------
  function renderPlaylist() {
    if (!playlist) return;
    playlist.innerHTML = "";
    if (!visibleTracks.length) {
      playlist.innerHTML =
        '<li class="playlist-empty">没有符合条件的曲目。' +
        (searchKeyword ? " 试试其它关键词。" : "") + "</li>";
      return;
    }
    visibleTracks.forEach(function (track, i) {
      var li = document.createElement("li");
      li.className = "playlist-item" + (currentIndex === i ? " active" : "");
      li.dataset.index = i;
      var kind = getKindLabel(track);
      var meta = track.kind === "binaural"
        ? "脑波 · " + (track.binaural ? track.binaural.beat + " Hz" : "")
        : "在线";
      li.innerHTML =
        '<span class="playlist-name"></span>' +
        '<span class="playlist-duration">--:--</span>';
      li.querySelector(".playlist-name").textContent = track.name;
      var durEl = li.querySelector(".playlist-duration");
      durEl.textContent = track.kind === "binaural" ? "∞" : meta + " · --:--";
      if (track.kind === "stream") {
        var probe = new Audio(track.url);
        probe.preload = "metadata";
        probe.addEventListener("loadedmetadata", function () {
          if (isFinite(probe.duration)) {
            durEl.textContent = meta + " · " + formatTime(probe.duration);
          }
        });
      }
      li.addEventListener("click", function () {
        loadTrack(i);
        playCurrent();
      });
      playlist.appendChild(li);
    });
  }

  // ---------- 播放控制（两种引擎统一入口） ----------
  function stopPlayback() {
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    stopBrainwave();
    btnPlay.textContent = "►";
    var cover = document.getElementById("music-cover");
    if (cover) cover.classList.remove("spinning");
    hideError();
  }

  function loadTrack(index) {
    if (index < 0 || index >= visibleTracks.length) return;
    stopPlayback();
    currentIndex = index;
    var track = visibleTracks[index];
    var kind = getKindLabel(track);
    musicTitle.textContent = track.name;
    if (musicArtist) musicArtist.textContent = track.artist || "";
    if (musicKind) musicKind.textContent = kind.base;
    if (musicKindDesc) musicKindDesc.textContent = kind.desc;
    progressFill.style.width = "0%";
    timeCurrent.textContent = "0:00";
    timeDuration.textContent = track.kind === "binaural" ? "∞" : "0:00";
    updatePlaylistActive();

    if (track.kind === "stream") {
      audio.src = track.url;
      audio.load();
    }
  }

  function playCurrent() {
    var track = currentTrack();
    if (!track) return;
    if (track.kind === "binaural") {
      startBrainwave(track);
      markPlaying(true);
    } else {
      audio.play().catch(function () {
        showError("在线音频播放失败：请检查网络连接，或换一首在线曲目重试。");
      });
    }
  }

  function pauseCurrent() {
    var track = currentTrack();
    if (track && track.kind === "binaural") {
      stopBrainwave();
      markPlaying(false);
    } else if (audio && !audio.paused) {
      audio.pause();
    }
  }

  function markPlaying(on) {
    btnPlay.textContent = on ? "II" : "►";
    var cover = document.getElementById("music-cover");
    if (cover) cover.classList.toggle("spinning", on);
  }

  // ---------- Web Audio：双耳节拍合成 ----------
  function ensureBrainCtx() {
    if (!brainCtx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return false;
      brainCtx = new AC();
      brainMaster = brainCtx.createGain();
      brainMaster.gain.value = parseFloat(volumeSlider.value);
      brainMaster.connect(brainCtx.destination);
    }
    if (brainCtx.state === "suspended") brainCtx.resume();
    return true;
  }

  function startBrainwave(track) {
    if (!ensureBrainCtx()) {
      showError("浏览器不支持 Web Audio，无法播放脑波音频。");
      return;
    }
    var b = track.binaural || { base: 200, beat: 10 };
    var waveType = track.wave || "sine";
    var leftFreq = Math.max(60, parseFloat(b.base) || 200);
    var rightFreq = leftFreq + (parseFloat(b.beat) || 10);

    brainNodes = [];
    [ // 左耳 base / 右耳 base+beat
      { freq: leftFreq, pan: -1 },
      { freq: rightFreq, pan: 1 },
    ].forEach(function (cfg) {
      var osc = brainCtx.createOscillator();
      osc.type = waveType;
      osc.frequency.value = cfg.freq;
      var gain = brainCtx.createGain();
      gain.gain.value = 0.9; // 轻柔音量
      var panner = brainCtx.createStereoPanner
        ? brainCtx.createStereoPanner()
        : null;
      if (panner) {
        panner.pan.value = cfg.pan;
        osc.connect(gain);
        gain.connect(panner);
        panner.connect(brainMaster);
      } else {
        osc.connect(gain);
        gain.connect(brainMaster);
      }
      osc.start();
      brainNodes.push(osc, gain);
    });

    timeDuration.textContent = "∞";
    timeCurrent.textContent = "0:00";
    progressFill.style.width = "0%";
    // 脑波为连续循环播放，不触发 ended
  }

  function stopBrainwave() {
    if (brainNodes && brainNodes.length) {
      brainNodes.forEach(function (node) {
        try { if (node.stop) node.stop(); else if (node.disconnect) node.disconnect(); }
        catch (err) { /* 忽略 */ }
      });
      brainNodes = [];
    }
  }

  // ---------- 上一首 / 下一首 / 循环 ----------
  function nextTrack() {
    if (!visibleTracks.length) return;
    if (loopMode === "one" && currentIndex >= 0) {
      // 单曲循环：重播当前曲目
      if (audio.src) { audio.currentTime = 0; playCurrent(); }
      else { stopBrainwave(); playCurrent(); }
      return;
    }
    var next = currentIndex + 1;
    if (next >= visibleTracks.length) {
      if (loopMode === "all") next = 0;
      else { stopPlayback(); return; }
    }
    loadTrack(next);
    playCurrent();
  }

  function prevTrack() {
    if (!visibleTracks.length) return;
    var track = currentTrack();
    if (track && track.kind === "stream" && audio.currentTime > 3) {
      audio.currentTime = 0;
      audio.play();
      return;
    }
    var prev = currentIndex - 1;
    if (prev < 0) {
      if (loopMode === "all") prev = visibleTracks.length - 1;
      else { loadTrack(0); playCurrent(); return; }
    }
    loadTrack(prev);
    playCurrent();
  }

  function toggleLoop() {
    var order = ["off", "all", "one"];
    var labels = { off: "不循环", all: "列表循环", one: "单曲循环" };
    var idx = order.indexOf(loopMode);
    loopMode = order[(idx + 1) % 3];
    localStorage.setItem("music_loop", loopMode);
    loopBtn.textContent = labels[loopMode];
  }

  function updatePlaylistActive() {
    var items = playlist ? playlist.querySelectorAll(".playlist-item") : [];
    items.forEach(function (li, i) {
      li.classList.toggle("active", i === currentIndex);
    });
  }

  // ---------- 错误提示 ----------
  function showError(msg) {
    if (!musicError) return;
    musicError.textContent = "⚠ " + msg;
    musicError.hidden = false;
  }
  function hideError() {
    if (musicError) musicError.hidden = true;
  }

  // ---------- 事件绑定 ----------
  btnPlay.addEventListener("click", function () {
    if (!visibleTracks.length) return;
    var track = currentTrack();
    if (currentIndex < 0 || !track) {
      loadTrack(0);
      playCurrent();
      return;
    }
    if (track.kind === "binaural") {
      // 脑波无 paused 概念：用 brainNodes 是否为空判断
      if (brainNodes.length) pauseCurrent();
      else playCurrent();
      return;
    }
    if (audio.paused) playCurrent(); else pauseCurrent();
  });

  btnNext.addEventListener("click", nextTrack);
  btnPrev.addEventListener("click", prevTrack);
  loopBtn.addEventListener("click", toggleLoop);

  audio.addEventListener("play", function () { markPlaying(true); });
  audio.addEventListener("pause", function () { markPlaying(false); });
  audio.addEventListener("error", function () {
    showError("在线音频加载失败：可能是网络不可达或曲目源失效。");
    markPlaying(false);
  });
  audio.addEventListener("ended", nextTrack);

  // 音量（同时作用于流媒体 audio 与脑波主增益）
  function applyVolume(v) {
    audio.volume = v;
    if (brainMaster && brainCtx) {
      brainMaster.gain.setValueAtTime(v, brainCtx.currentTime);
    }
    volumeSlider.value = v;
    localStorage.setItem("music_volume", String(v));
  }
  volumeSlider.addEventListener("input", function () {
    applyVolume(parseFloat(volumeSlider.value));
  });

  // 进度条（仅流媒体）
  audio.addEventListener("timeupdate", function () {
    if (!isFinite(audio.duration)) return;
    var pct = (audio.duration ? (audio.currentTime / audio.duration) * 100 : 0);
    progressFill.style.width = pct + "%";
    timeCurrent.textContent = formatTime(audio.currentTime);
    timeDuration.textContent = formatTime(audio.duration);
  });
  progressBar.addEventListener("click", function (event) {
    var rect = progressBar.getBoundingClientRect();
    var ratio = (event.clientX - rect.left) / rect.width;
    if (isFinite(audio.duration)) {
      audio.currentTime = ratio * audio.duration;
    }
  });

  // 分类 chips
  if (catChipsBox) {
    catChipsBox.addEventListener("click", function (event) {
      var chip = event.target.closest(".chip");
      if (!chip) return;
      catChipsBox.querySelectorAll(".chip").forEach(function (c) {
        c.classList.toggle("is-active", c === chip);
      });
      categoryFilter = chip.dataset.category || "";
      applyFilter();
    });
  }

  // 搜索（输入防抖）
  var searchTimer = null;
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        searchKeyword = searchInput.value;
        applyFilter();
      }, 200);
    });
  }

  // ---------- 初始化 ----------
  var savedVolume = parseFloat(localStorage.getItem("music_volume"));
  if (isNaN(savedVolume)) savedVolume = 0.5;
  applyVolume(Math.min(1, Math.max(0, savedVolume)));
  loopBtn.textContent = ({ off: "不循环", all: "列表循环", one: "单曲循环" })[loopMode];

  applyFilter();
  if (visibleTracks.length) {
    loadTrack(0); // 预载第一首，等待用户点击播放
  }
})();
