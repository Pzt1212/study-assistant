/* ============================================================
   媒体库前端（media/index.html + blueprints/media.py）
   功能：
   1. 设备自适应（自动/手机/电脑，手动切换 → 影响上传并发与体验）
   2. 上传双通道：
      - r2    ：浏览器把文件切成小块，PUT 到 Cloudflare R2 预签名 URL
                （字节不经过本站/Tunnel，支持断点续传/分块重试）
      - proxy ：resumable.js 分块 POST 到本站（本地加密落盘→异步转 R2）
   3. 播放：私有桶预签名 Range 直连（防盗链；URL 过期自动续签并从原位置续播）
   4. 完成态自动云端校验与备份（服务端异步任务）
   ============================================================ */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var LS_DEV = "sa_media_device";       // auto | mobile | desktop
  var BATCH = 16;                        // 每批签发的分块 URL 数（与后端一致上限内）

  var cfg = null;                       // /api/config
  var device = loadPref(LS_DEV, "auto");
  var uploads = {};                     // itemId -> 进行中的上传句柄 {cancel}
  var itemsCache = [];                  // 最近一次列表，播放标题等用
  var resumeMap = {};                   // "name|size" -> item
  var playingId = null;
  var _refreshBusy = false;             // 播放源失效自动换新防抖

  // ---------------- 基础工具 ----------------
  function loadPref(key, def) {
    try { return localStorage.getItem(key) || def; } catch (e) { return def; }
  }
  function savePref(key, val) {
    try { localStorage.setItem(key, val); } catch (e) { /* ignore */ }
  }
  function toast(msg, ms) {
    var el = $("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.remove("show"); }, ms || 2600);
  }
  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
  function fmtSize(n) {
    n = n || 0;
    if (n < 1024) return n + " B";
    var u = ["KB", "MB", "GB", "TB"], i = -1;
    do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
    return n.toFixed(n >= 100 ? 0 : 1) + " " + u[i];
  }
  function isMobileUA() {
    return /Android|iPhone|iPad|iPod|Mobile|Mobi/i.test(navigator.userAgent) ||
      (navigator.maxTouchPoints > 0 && window.innerWidth < 820);
  }
  function concurrency() {
    var d = device === "auto" ? (isMobileUA() ? "mobile" : "desktop") : device;
    return d === "mobile" ? 1 : 3;
  }
  function devLabel() {
    var d = device === "auto" ? (isMobileUA() ? "手机(自动)" : "电脑(自动)") :
      (device === "mobile" ? "手机" : "电脑");
    return d;
  }
  function extOf(name) {
    var i = (name || "").lastIndexOf(".");
    return i < 0 ? "" : name.slice(i + 1).toLowerCase();
  }
  function keyOfFile(f) { return f.name + "|" + f.size; }

  // ---------------- API（fetch 已被 csrf.js 包装，自动带 X-CSRFToken） ----------------
  function apiFetch(url, method, body) {
    var opts = { method: method || "GET", headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (resp) {
      return resp.json().catch(function () {
        return { ok: false, error: "服务器返回异常（HTTP " + resp.status + "）" };
      }).then(function (data) {
        if (!resp.ok || data.ok === false) {
          var e = new Error(data.error || ("HTTP " + resp.status));
          e.status = resp.status;
          throw e;
        }
        return data;
      });
    });
  }
  var api = {
    get: function (u) { return apiFetch(u); },
    post: function (u, body) { return apiFetch(u, "POST", body); },
    del: function (u) { return apiFetch(u, "DELETE"); }
  };

  // ---------------- 设备模式 ----------------
  function paintDevice() {
    var seg = $("devSeg");
    if (!seg) return;
    seg.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-dev") === device);
    });
    var chip = $("modeChip");
    if (chip) chip.textContent = "设备：" + devLabel() + " · 并发 " + concurrency();
  }
  function bindDevice() {
    var seg = $("devSeg");
    if (!seg) return;
    seg.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-dev]");
      if (!b) return;
      device = b.getAttribute("data-dev");
      savePref(LS_DEV, device);
      paintDevice();
    });
  }

  // ---------------- 上传：r2 直传（S3 multipart 预签名） ----------------
  function createSession(file) {
    return api.post("/media/api/items", {
      filename: file.name, size: file.size, mime: file.type || ""
    });
  }

  function uploadR2(data, file, ui) {
    var item = data.item, upload = data.upload || {};
    var id = item.id;
    var size = item.sizeBytes, ps = upload.partSize || cfg.partSize;
    var totalParts = upload.partCount ||
      Math.max(1, Math.ceil(size / ps));
    var done = 0, stopped = false, inflight = 0, cursor = 1;
    var urlPool = {};   // partNumber -> url
    var urlTail = 0;    // 已签发到的分块号
    var uploadedSet = {};

    function mark(bytes) {
      if (stopped) return;
      done += bytes;
      ui.progress(Math.min(100, done * 100 / size));
      ui.meta(fmtSize(done) + " / " + fmtSize(size));
    }
    function takeNext() {
      while (cursor <= totalParts && inflight < concurrency()) {
        var num = cursor++;
        inflight++;
        uploadOne(num).then(function () {
          inflight--;
          mark(Math.min(ps, size - (num - 1) * ps));
          if (num === totalParts && inflight === 0) finish();
          else takeNext();
        }).catch(function (err) {
          inflight--;
          if (stopped) return;
          ui.fail("分块 " + num + " 上传失败：" + err.message);
        });
      }
    }
    function urlFor(num) {
      if (urlPool[num]) return Promise.resolve(urlPool[num]);
      // 从远端批量签发一批分块 URL（服务端签名，客户端不可伪造）
      var start = num, count = Math.min(BATCH, totalParts - num + 1);
      return api.post("/media/api/items/" + id + "/part-urls",
        { start: start, count: count }).then(function (d) {
        urlTail = Math.max(urlTail, start + count - 1);
        Object.keys(d.urls).forEach(function (k) {
          urlPool[parseInt(k, 10)] = d.urls[k];
        });
        return urlPool[num];
      });
    }
    function xhrPut(url, blob) {
      return new Promise(function (resolve, reject) {
        var x = new XMLHttpRequest();
        x.open("PUT", url);
        x.setRequestHeader("Content-Type", "application/octet-stream");
        x.onload = function () {
          if (x.status >= 200 && x.status < 300) resolve(x.status);
          else {
            var e = new Error("HTTP " + x.status);
            e.status = x.status;
            reject(e);
          }
        };
        x.onerror = function () { reject(new Error("网络错误")); };
        x.send(blob);
      });
    }
    function uploadOne(num) {
      var attempts = 0;
      var step = function () {
        return urlFor(num).then(function (url) {
          var startB = (num - 1) * ps;
          var blob = file.slice(startB, Math.min(startB + ps, size));
          return xhrPut(url, blob);
        }).catch(function (err) {
          if (stopped) return;
          attempts++;
          if (err.status === 403 && attempts < 4) {   // 签名过期 → 换新 URL 重试
            delete urlPool[num];
            return step();
          }
          if (attempts < 3) {                          // 网络抖动 → 退避重试
            return new Promise(function (res) {
              setTimeout(res, attempts * 1200);
            }).then(step);
          }
          throw err;
        });
      };
      return step();
    }
    function finish() {
      if (stopped || finishedFlag) return;
      finishedFlag = true;
      ui.meta("分块齐全，正在完成…");
      api.post("/media/api/items/" + id + "/complete", {}).then(function () {
        if (stopped) return;
        ui.done("上传完成，已入队云端校验/备份");
        delete uploads[id];
        refreshList();
      }).catch(function (err) { ui.fail(err.message); });
    }
    var finishedFlag = false;

    // 断点续传：先查 R2 侧已上传分块，跳过它们
    api.get("/media/api/items/" + id + "/parts").then(function (d) {
      if (stopped) return;
      (d.uploaded || []).forEach(function (n) { uploadedSet[n] = 1; });
      // 已上传的分块编号从待上传游标中剔除：直接从缺失的最小号开始
      var missing = [];
      for (var n = 1; n <= totalParts; n++) if (!uploadedSet[n]) missing.push(n);
      if (!missing.length) { finish(); return; }
      done = d.uploadedBytes || 0;
      ui.progress(Math.min(100, done * 100 / size));
      cursor = 1;
      var missingSet = {};
      missing.forEach(function (n) { missingSet[n] = 1; });
      // 调整 takeNext 逻辑：只上传 missing 中的分块
      var origTakeNext = takeNext;
      takeNext = function () {
        while (inflight < concurrency()) {
          var num = cursor++;
          while (num <= totalParts && !missingSet[num]) num = cursor++;
          if (num > totalParts) break;
          inflight++;
          (function (n) {
            uploadOne(n).then(function () {
              inflight--;
              delete missingSet[n];
              mark(Math.min(ps, size - (n - 1) * ps));
              if (Object.keys(missingSet).length === 0 && inflight === 0) finish();
              else takeNext();
            }).catch(function (err) {
              inflight--;
              if (!stopped) ui.fail("分块 " + n + " 上传失败：" + err.message);
            });
          })(num);
        }
      };
      takeNext();
    }).catch(function (err) {
      // 无上传会话（例如刚创建但 R2 侧尚未有记录）直接开始
      if (err.status && err.status !== 404 && err.status !== 409) {
        ui.fail(err.message); return;
      }
      takeNext();
    });

    return {
      cancel: function () {
        stopped = true;
        api.post("/media/api/items/" + id + "/abort", {}).catch(function () {});
      }
    };
  }

  // ---------------- 上传：proxy 通道（resumable.js） ----------------
  function uploadProxy(item, file, ui) {
    if (!window.Resumable) {
      ui.fail("proxy 通道需要 static/vendor/resumable.js（见部署文档）");
      return { cancel: function () {} };
    }
    var csrf = csrfToken();
    var r = new Resumable({
      target: "/media/api/proxy/chunks/" + item.id,
      chunkSize: cfg.partSize,
      simultaneousUploads: concurrency(),
      testChunks: true,
      maxChunkRetries: 4,
      retryInterval: 2000,
      generateUniqueIdentifier: function () { return "m" + item.id; },
      headers: csrf ? { "X-CSRFToken": csrf } : {}
    });
    var finished = false;
    r.on("fileProgress", function (f) {
      if (finished) return;
      ui.progress(Math.round(f.progress() * 100));
      ui.meta(fmtSize(Math.round(f.progress() * item.sizeBytes)) + " / " + fmtSize(item.sizeBytes));
    });
    r.on("fileSuccess", function () {
      if (finished) return;
      finished = true;
      ui.meta("分块齐了，正在组装并转存云端…");
      api.post("/media/api/proxy/complete/" + item.id, {}).then(function () {
        ui.done("上传完成，正在后台转存/备份");
        delete uploads[item.id];
        refreshList();
      }).catch(function (err) { ui.fail(err.message); });
    });
    r.on("fileError", function (f, msg) {
      if (!finished) ui.fail("分块上传失败：" + (msg || "未知错误"));
    });
    try { r.addFile(file); r.upload(); }
    catch (e) { ui.fail("无法开始上传：" + e.message); }

    return {
      cancel: function () {
        finished = true;
        try { r.cancel(); } catch (e) { /* ignore */ }
        api.del("/media/api/proxy/session/" + item.id).catch(function () {});
      }
    };
  }

  // ---------------- 上传：统一入口 + UI ----------------
  function addUploadCard(item, file) {
    var wrap = $("activeUploads");
    if (!wrap) return;
    var empty = wrap.querySelector(".empty");
    if (empty) empty.remove();
    var div = document.createElement("div");
    div.className = "up-item";
    div.innerHTML =
      '<div class="row1"><span class="name">' + esc(file ? file.name : item.filename) +
      '</span><button type="button" class="btn btn-ghost btn-sm" data-cancel>取消</button></div>' +
      '<div class="bar"><i></i></div>' +
      '<div class="meta"></div>';
    wrap.appendChild(div);
    var bar = div.querySelector(".bar i"), meta = div.querySelector(".meta");
    var ui = {
      progress: function (p) { bar.style.width = Math.max(0, Math.min(100, p)) + "%"; },
      meta: function (t) { meta.textContent = t; },
      done: function (t) {
        meta.textContent = t;
        meta.style.color = "#16a34a";
        bar.style.background = "#16a34a";
      },
      fail: function (t) {
        meta.textContent = t;
        meta.style.color = "#dc2626";
        toast(t, 4200);
      }
    };
    div.querySelector("[data-cancel]").addEventListener("click", function () {
      if (uploads[item.id]) uploads[item.id].cancel();
      uploads[item.id] = { cancelled: true };
      meta.textContent = "已取消";
      div.querySelector("[data-cancel]").disabled = true;
    });
    return ui;
  }

  function startUpload(file) {
    // 客户端预校验
    var ext = extOf(file.name);
    if (cfg.allowedExtensions.indexOf(ext) < 0) {
      toast("不支持的文件类型：" + (ext || "无扩展名")); return;
    }
    if (file.size > cfg.maxSize) { toast("文件超过大小上限"); return; }
    if (file.size <= 0) { toast("空文件无法上传"); return; }

    // 断点续传匹配：同名的未完成任务 → 问用户是否续传
    var cand = resumeMap[keyOfFile(file)];
    if (cand) {
      if (!confirm("检测到《" + file.name + "》有未完成的上传（" +
          cand.statusLabel + "），是否断点续传？\n选择“取消”将重新上传一份。")) {
        newUpload(file);
      } else {
        resumeUpload(cand, file);
      }
      return;
    }
    newUpload(file);
  }

  function newUpload(file) {
    toast("正在创建上传会话…");
    createSession(file).then(function (data) {
      var item = data.item;
      var ui = addUploadCard(item, file);
      var h;
      if (cfg.channel === "proxy") {
        h = uploadProxy(item, file, ui);
      } else {
        h = uploadR2(data, file, ui);
      }
      if (h && h.cancel) uploads[item.id] = h;
      else if (h && h.cancelled) uploads[item.id] = h;
    }).catch(function (err) {
      toast("创建会话失败：" + err.message, 4200);
    });
  }

  function resumeUpload(item, file) {
    var ui = addUploadCard(item, file);
    // 重新取详情/上传配置
    api.get("/media/api/items/" + item.id).then(function (d) {
      var data = { item: d.item, upload: { partSize: d.item.partSize } };
      var h;
      if (cfg.channel === "proxy") h = uploadProxy(d.item, file, ui);
      else h = uploadR2(data, file, ui);
      if (h && h.cancel) uploads[d.item.id] = h;
    }).catch(function (err) { ui.fail(err.message); });
  }

  // ---------------- 媒体列表 ----------------
  function renderList(items, quota) {
    var body = $("mediaBody"), empty = $("mediaEmpty");
    if (!body) return;
    body.innerHTML = "";
    itemsCache = items;
    resumeMap = {};
    if (empty) empty.hidden = items.length > 0;
    items.forEach(function (it) {
      if (it.status === "uploading" || it.status === "init") {
        resumeMap[keyOfFile({ name: it.filename, size: it.sizeBytes })] = it;
      }
      var tr = document.createElement("tr");
      var act = "";
      if (it.playable) {
        act += '<button type="button" class="btn btn-primary btn-sm" data-play="' + it.id + '">播放</button>';
      } else if (it.status === "uploading" || it.status === "init") {
        act += '<button type="button" class="btn btn-ghost btn-sm" data-resume="' + it.id + '">续传</button>';
      }
      if ((it.status === "ready" || it.status === "verifying" || it.status === "failed") &&
          cfg.r2Ready && !it.uploadId) {
        act += '<button type="button" class="btn btn-ghost btn-sm" data-backup="' + it.id + '">备份</button>';
      }
      act += '<button type="button" class="btn btn-ghost btn-sm" data-del="' + it.id + '">删除</button>';
      tr.innerHTML =
        '<td><div style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" ' +
        'title="' + esc(it.filename) + '">' + esc(it.title) + '</div></td>' +
        '<td>' + fmtSize(it.sizeBytes) + '</td>' +
        '<td><span class="' + (it.status === "failed" ? "bad" : it.status === "backed_up" ? "ok" : "") +
        '">' + esc(it.statusLabel) + '</span>' +
        (it.error ? '<div class="muted" style="max-width:180px">' + esc(it.error) + '</div>' : '') + '</td>' +
        '<td><div class="row-act">' + act + '</div></td>';
      body.appendChild(tr);
    });
    body.querySelectorAll("[data-play]").forEach(function (b) {
      b.addEventListener("click", function () {
        playItem(parseInt(b.getAttribute("data-play"), 10));
      });
    });
    body.querySelectorAll("[data-resume]").forEach(function (b) {
      b.addEventListener("click", function () {
        var it = items.find(function (x) { return x.id === parseInt(b.getAttribute("data-resume"), 10); });
        if (!it) return;
        if (!confirm("选择同一个文件以续传《" + it.filename + "》")) return;
        pendingResume = it;
        $("fileInput").click();
      });
    });
    body.querySelectorAll("[data-backup]").forEach(function (b) {
      b.addEventListener("click", function () {
        var id = b.getAttribute("data-backup");
        api.post("/media/api/items/" + id + "/backup", {}).then(function (d) {
          toast(d.message || "已入队备份");
        }).catch(function (err) { toast(err.message); });
      });
    });
    body.querySelectorAll("[data-del]").forEach(function (b) {
      b.addEventListener("click", function () {
        var id = b.getAttribute("data-del");
        if (!confirm("确定删除该媒体？云端对象将一并清理（不可恢复）")) return;
        api.del("/media/api/items/" + id).then(function () {
          toast("已删除");
          if (playingId === parseInt(id, 10)) hidePlayer();
          refreshList();
        }).catch(function (err) { toast(err.message); });
      });
    });
    var q = $("quotaChip");
    if (q && quota) {
      q.textContent = "已用 " + fmtSize(quota.usedBytes) +
        (quota.limitBytes > 0 ? " / " + fmtSize(quota.limitBytes) : "");
    }
  }
  var pendingResume = null;

  function refreshList() {
    return api.get("/media/api/items").then(function (d) {
      renderList(d.items, d.quota);
    }).catch(function (err) {
      toast("刷新列表失败：" + err.message);
    });
  }

  // ---------------- 播放：预签名直连 + Range 续播 ----------------
  function hidePlayer() {
    var box = $("playerBox");
    if (box) box.hidden = true;
    var v = $("player");
    if (v) v.pause();
    playingId = null;
  }

  function playItem(id) {
    api.get("/media/api/items/" + id + "/play").then(function (d) {
      var v = $("player"), box = $("playerBox");
      if (!v || !box) return;
      playingId = id;
      box.hidden = false;
      var meta = itemsCache.find(function (x) { return x.id === id; });
      $("pTitle").textContent = meta ? (meta.title || meta.filename) : ("#" + id);
      // 服务端已按 MEDIA_PLAYBACK_SOURCE 定好播放源（r2 预签名直连，或 self 兜底）
      var keepTime = v.currentTime || 0;
      v.src = d.url;
      v.load();
      var mark = $("pSource");
      if (mark) mark.textContent = "源：" + srcLabel(d.source);
      v.onloadedmetadata = function () {
        if (keepTime > 0.5) {
          v.currentTime = keepTime;
          v.play().catch(function () {});
        }
      };
      v.play().catch(function () {});
    }).catch(function (err) { toast("无法播放：" + err.message); });
  }

  function srcLabel(k) {
    return k === "r2" ? "R2 直连(推荐)" : "本站(慢,应急)";
  }

  // ---------------- 页面初始化 ----------------
  function bindUploadUI() {
    var drop = $("dropZone"), input = $("fileInput");
    if (!drop || !input) return;
    drop.addEventListener("click", function () { input.click(); });
    ["dragenter", "dragover"].forEach(function (t) {
      drop.addEventListener(t, function (ev) { ev.preventDefault(); drop.classList.add("dragover"); });
    });
    ["dragleave", "drop"].forEach(function (t) {
      drop.addEventListener(t, function (ev) { ev.preventDefault(); drop.classList.remove("dragover"); });
    });
    drop.addEventListener("drop", function (ev) {
      var f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
      if (f) startUpload(f);
    });
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      input.value = "";
      if (!f) return;
      if (pendingResume) {
        // 续传：需要同名同大小文件
        var it = pendingResume;
        pendingResume = null;
        if (keyOfFile(f) !== keyOfFile({ name: it.filename, size: it.sizeBytes })) {
          toast("请选择同一个文件（名称与大小需一致）");
          return;
        }
        resumeUpload(it, f);
      } else {
        startUpload(f);
      }
    });
  }

  // 播放中途预签名 URL 过期/失效 → 自动换新并从当前位置续播（Range 续播）
  function bindPlayerRefresh() {
    var v = $("player");
    if (!v) return;
    v.addEventListener("loadedmetadata", function () { _refreshBusy = false; });
    v.addEventListener("error", function () {
      if (!playingId || _refreshBusy) return;
      _refreshBusy = true;
      var t = v.currentTime || 0;
      api.get("/media/api/items/" + playingId + "/play").then(function (d) {
        if (!d.url || playingId === null) { _refreshBusy = false; return; }
        v.src = d.url;
        v.load();
        var once = function () {
          v.removeEventListener("loadedmetadata", once);
          if (t > 0.5) {
            v.currentTime = t;
            v.play().catch(function () {});
          }
          _refreshBusy = false;
        };
        v.addEventListener("loadedmetadata", once);
      }).catch(function () { _refreshBusy = false; });
    });
  }

  function boot() {
    bindDevice();
    bindUploadUI();
    bindPlayerRefresh();
    api.get("/media/api/config").then(function (d) {
      cfg = d.config;
      var sub = $("dropSub");
      if (sub) {
        sub.textContent = "通道：" + (cfg.channel === "proxy" ? "本站中转(proxy)" : "R2 直传") +
          " · 分块 " + fmtSize(cfg.partSize) + " · 单文件上限 " + fmtSize(cfg.maxSize) +
          " · " + (cfg.verify ? "完成后自动校验+备份" : "完成后自动备份");
      }
      paintDevice();
      refreshList();
    }).catch(function (err) {
      toast("初始化失败：" + err.message, 5000);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
