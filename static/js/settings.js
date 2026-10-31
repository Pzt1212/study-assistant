/* ============================================================
   学习助手 - 设置（settings.js）
   - 主题：3 套预设（极简白/暗夜黑/森林绿），即时生效 + 记忆
   - 文字：字体族 / 字号 14-20px / 行高 1.5-2.0，即时生效 + 记忆
   - 头像：自定义头像（上传小图压缩 或 emoji 图标），经后端保存
   - 仅依赖 CSS 变量，无页面刷新
   ============================================================ */
(function () {
  "use strict";

  var STORE_KEY = "sa_ui_settings_v1";

  /* 预设主题：只给 CSS data-theme 用（色值在 theme.css） */
  var PRESET_IDS = ["minimal", "dark", "forest"];
  var DEFAULT_THEME = "minimal";

  var FONTS = {
    inter: {
      stack: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif',
    },
    system: {
      stack: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
    },
    serif: {
      stack: '"Iowan Old Style", "Songti SC", "STSong", "SimSun", Georgia, "Times New Roman", serif',
    },
    mono: {
      stack: 'ui-monospace, "SF Mono", "Cascadia Code", Consolas, "JetBrains Mono", monospace',
    },
  };

  var AVATAR_COLORS = ["#e8e6e1", "#f3d9c4", "#f7e2c2", "#cde7d0", "#bcd8ea", "#d9cfe8",
                       "#f3c6c8", "#c8e0d8", "#d6d3f0", "#f0d5e8", "#d9e6c8", "#f5dfc9"];

  var state = null;

  /* ---------- 工具 ---------- */
  function clamp(v, min, max) {
    v = parseFloat(v);
    if (isNaN(v)) v = min;
    return Math.min(max, Math.max(min, v));
  }
  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
  }
  function load() {
    var def = { theme: DEFAULT_THEME, fontId: "inter", fontSize: 15, lineHeight: 1.65 };
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (!raw) return def;
      var s = JSON.parse(raw);
      if (typeof s === "string") s = { theme: s };
      var out = Object.assign({}, def, s);
      if (PRESET_IDS.indexOf(out.theme) === -1) out.theme = DEFAULT_THEME;
      if (!FONTS[out.fontId]) out.fontId = def.fontId;
      return out;
    } catch (e) {
      return def;
    }
  }

  function ensureInterFont() {
    if (document.getElementById("font-inter")) return;
    var link = document.createElement("link");
    link.id = "font-inter";
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap";
    document.head.appendChild(link);
  }

  /* ---------- 应用（主题 + 文字） ---------- */
  function applyUI() {
    var html = document.documentElement;
    html.setAttribute("data-theme", state.theme);
    var fontStack = FONTS[state.fontId] ? FONTS[state.fontId].stack : FONTS.inter.stack;
    html.style.setProperty("--font", fontStack);
    html.style.setProperty("--fs", clamp(state.fontSize, 14, 20) + "px");
    html.style.setProperty("--lh", String(clamp(state.lineHeight, 1.5, 2.0)));
    syncControls();
  }

  /* ---------- DOM ---------- */
  function $(id) { return document.getElementById(id); }

  function syncControls() {
    if (!document.body.classList.contains("settings-ready")) return;
    document.querySelectorAll(".theme-preset").forEach(function (el) {
      el.classList.toggle("is-active", el.dataset.preset === state.theme);
    });
    if ($("set-font")) $("set-font").value = state.fontId;
    if ($("set-size")) $("set-size").value = state.fontSize;
    if ($("set-lh")) $("set-lh").value = state.lineHeight;
    if ($("val-size")) $("val-size").textContent = state.fontSize + " px";
    if ($("val-lh")) $("val-lh").textContent = state.lineHeight.toFixed(2);
  }

  /* ============================================================
     头像
     ============================================================ */
  var currentAvatar = window.SA_AVATAR || null;

  function avatarEl(kind, value, color) {
    var size = kind === "img" ? 34 : 30;
    if (kind === "img") {
      var i = document.createElement("img");
      i.src = value;
      i.alt = "";
      var span = document.createElement("span");
      span.className = "user-avatar user-avatar-img";
      span.appendChild(i);
      return span;
    }
    var el = document.createElement("span");
    el.className = "user-avatar";
    el.textContent = value;
    el.style.background = color || "#d9dde3";
    return el;
  }

  function refreshNavAvatar() {
    var navAvatar = document.querySelector(".user-box > .user-avatar");
    if (!navAvatar) return;
    var nu = navAvatar.cloneNode(false);
    if (currentAvatar && currentAvatar.kind === "image") {
      nu.className = "user-avatar user-avatar-img";
      var img = document.createElement("img");
      img.src = currentAvatar.value;
      img.alt = "";
      img.onload = function () { /* noop */ };
      nu.appendChild(img);
    } else if (currentAvatar && (currentAvatar.kind === "emoji" || currentAvatar.kind === "text")) {
      nu.textContent = currentAvatar.value;
      nu.style.background = currentAvatar.color || "#d9dde3";
      nu.classList.remove("user-avatar-img", "user-avatar-letter");
    } else {
      // 首字母兜底
      var name = (document.querySelector(".user-name") || {}).textContent || "?";
      nu.textContent = (name.trim().slice(0, 1) || "?").toUpperCase();
      nu.className = "user-avatar user-avatar-letter";
      nu.style.background = "";
    }
    navAvatar.replaceWith(nu);
  }

  function refreshPreview() {
    var wrap = $("avatar-preview");
    if (!wrap) return;
    wrap.innerHTML = "";
    var size = 52;
    if (currentAvatar && currentAvatar.kind === "image") {
      var img = document.createElement("img");
      img.src = currentAvatar.value;
      img.alt = "";
      var s = document.createElement("span");
      s.className = "user-avatar user-avatar-img";
      s.style.width = size + "px";
      s.style.height = size + "px";
      s.style.borderRadius = (size + 4) + "px";
      s.appendChild(img);
      wrap.appendChild(s);
    } else if (currentAvatar && (currentAvatar.kind === "emoji" || currentAvatar.kind === "text")) {
      var e = document.createElement("span");
      e.className = "user-avatar";
      e.style.width = size + "px";
      e.style.height = size + "px";
      e.style.borderRadius = (size + 4) + "px";
      e.style.fontSize = (size * 0.52) + "px";
      e.style.background = currentAvatar.color || "#d9dde3";
      e.textContent = currentAvatar.value;
      wrap.appendChild(e);
    } else {
      wrap.innerHTML = '<span class="user-avatar user-avatar-letter" style="width:52px;height:52px;border-radius:56px;font-size:24px">?</span>';
    }
  }

  function pushAvatar(payload, okMsg) {
    fetch("/api/avatar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          alert(data.error || "保存失败");
          return;
        }
        currentAvatar = data.avatar || null;
        refreshNavAvatar();
        refreshPreview();
        if (okMsg) showSettingTip(okMsg);
      })
      .catch(function () {
        alert("网络错误，保存失败");
      });
  }

  function showSettingTip(msg) {
    var tip = $("avatar-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "avatar-tip";
      tip.className = "setting-tip";
      var actions = $("avatar-remove");
      if (actions && actions.parentNode) {
        actions.parentNode.insertBefore(tip, actions);
      }
    }
    tip.textContent = msg;
    clearTimeout(showSettingTip._t);
    showSettingTip._t = setTimeout(function () { tip.textContent = ""; }, 2400);
  }

  /* 字母头像的首字母：优先 window.SA_ME（新页面），否则从侧栏用户名 DOM 读取，
     两者都缺（旧缓存页面）时兜底为当前头像已有文字或 "?" */
  function currentInitial() {
    var raw = "";
    try {
      var me = window.SA_ME || {};
      raw = String(me.name || "").trim();
    } catch (e) {}
    if (!raw) {
      var el = document.querySelector(".side-user-name") || document.querySelector(".topbar-title");
      if (el) raw = (el.textContent || "").replace(/\s/g, "").slice(0, 12);
    }
    raw = raw.replace(/[·•|]/g, "").trim();
    return (raw.slice(0, 1) || "?").toUpperCase();
  }

  function bindAvatar() {
    // 字母头像底色选择（字形取用户名首字母，替代 emoji）
    var pick = $("avatar-emoji-pick");
    if (pick) {
      var initial = currentInitial();
      AVATAR_COLORS.forEach(function (color) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "avatar-emoji-btn";
        b.textContent = initial;
        b.style.background = color;
        b.title = "字母头像（" + initial + "）· 底色";
        b.addEventListener("click", function () {
          pushAvatar({ kind: "text", value: initial, color: color });
        });
        pick.appendChild(b);
      });
    }

    // 上传图片 → 压缩到 ≤128px → dataURL
    var fileInput = $("avatar-file");
    if (fileInput) {
      fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) return;
        if (!/^image\//.test(file.type)) {
          alert("请选择图片文件。");
          return;
        }
        var reader = new FileReader();
        reader.onload = function () {
          var img = new Image();
          img.onload = function () {
            var MAX = 128;
            var w = img.naturalWidth, h = img.naturalHeight;
            if (w > MAX || h > MAX) {
              var r = Math.min(MAX / w, MAX / h);
              w = Math.round(w * r); h = Math.round(h * r);
            }
            var canvas = document.createElement("canvas");
            canvas.width = w; canvas.height = h;
            canvas.getContext("2d").drawImage(img, 0, 0, w, h);
            var dataUrl = canvas.toDataURL("image/jpeg", 0.82);
            if (dataUrl.length > 90 * 1024) dataUrl = canvas.toDataURL("image/jpeg", 0.6);
            if (dataUrl.length > 380 * 1024) dataUrl = canvas.toDataURL("image/jpeg", 0.4);
            pushAvatar({ kind: "image", value: dataUrl });
          };
          img.src = reader.result;
        };
        reader.readAsDataURL(file);
        fileInput.value = "";
      });
    }

    // 移除
    var rm = $("avatar-remove");
    if (rm) {
      rm.addEventListener("click", function () {
        pushAvatar({}, "已恢复默认头像");
      });
    }
  }

  /* ============================================================
     抽屉
     ============================================================ */
  function openDrawer() {
    var d = $("settings-drawer"), b = $("settings-backdrop");
    if (d) d.classList.add("is-open");
    if (b) b.classList.add("is-open");
    document.body.style.overflow = "hidden";
    refreshPreview();
  }
  function closeDrawer() {
    var d = $("settings-drawer"), b = $("settings-backdrop");
    if (d) d.classList.remove("is-open");
    if (b) b.classList.remove("is-open");
    document.body.style.overflow = "";
  }

  function init() {
    ensureInterFont();
    state = load();
    document.body.classList.add("settings-ready");
    applyUI();

    var btn = $("btn-settings");
    if (btn) btn.addEventListener("click", openDrawer);
    var closeBtn = $("settings-close");
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    var backdrop = $("settings-backdrop");
    if (backdrop) backdrop.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });

    // 预设主题
    document.querySelectorAll(".theme-preset").forEach(function (el) {
      el.addEventListener("click", function () {
        var id = el.dataset.preset;
        if (PRESET_IDS.indexOf(id) === -1) return;
        state.theme = id;
        applyUI();
        save();
      });
    });

    // 文字
    var fontSel = $("set-font");
    if (fontSel) {
      fontSel.addEventListener("change", function () {
        state.fontId = fontSel.value;
        applyUI();
        save();
      });
    }
    var sizeInput = $("set-size");
    if (sizeInput) {
      sizeInput.addEventListener("input", function () {
        state.fontSize = clamp(sizeInput.value, 14, 20);
        applyUI();
        save();
      });
    }
    var lhInput = $("set-lh");
    if (lhInput) {
      lhInput.addEventListener("input", function () {
        state.lineHeight = clamp(lhInput.value, 1.5, 2.0);
        applyUI();
        save();
      });
    }

    var resetAll = $("reset-all");
    if (resetAll) {
      resetAll.addEventListener("click", function () {
        state = { theme: DEFAULT_THEME, fontId: "inter", fontSize: 15, lineHeight: 1.65 };
        applyUI();
        save();
      });
    }

    bindAvatar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
