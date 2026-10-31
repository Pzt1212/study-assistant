/* ============================================================
   笔记编辑器：文本 / 手写（Canvas → SVG）模式
   - 文本：textarea 直接编辑（原有逻辑）
   - 手写：Canvas 绘图，支持颜色 / 粗细 / 橡皮擦 / 撤销 / 清空
   - 保存：把手写笔迹序列化为内嵌 SVG（含 JSON 数据注释）写入 content 字段，
     后端 file_type 标记为 svg，详情页可直接渲染 SVG
   - 编辑手写笔记时自动切回手写模式并恢复笔迹
   无任何外部依赖，纯原生 JS。
   ============================================================ */
(function () {
  "use strict";

  var form = document.getElementById("note-form");
  var contentEl = document.getElementById("content");
  var tabs = document.getElementById("note-mode-tabs");
  var tabText = document.getElementById("tab-text");
  var tabHandwrite = document.getElementById("tab-handwrite");
  var paneText = document.getElementById("pane-text");
  var paneHandwrite = document.getElementById("pane-handwrite");
  var editorModeEl = document.getElementById("editor-mode");
  var canvas = document.getElementById("handwrite-canvas");

  // ---------- 手写状态 ----------
  var strokes = [];        // [{tool:'pen'|'eraser', color, size, points:[[x,y],...]}]
  var drawing = false;
  var currentStroke = null;
  var currentTool = "pen";
  var currentColor = "#1f2430";
  var currentSize = 4;

  var SVG_MARK = "<!--#!handwriting-svg-->";

  function isSvgContent(value) {
    return (value || "").indexOf(SVG_MARK) !== -1;
  }

  // ============================================================
  // 模式切换
  // ============================================================
  function setMode(mode) {
    var isHand = mode === "handwrite";
    editorModeEl.value = isHand ? "handwrite" : "text";
    paneText.hidden = isHand;
    paneHandwrite.hidden = !isHand;
    tabText.classList.toggle("is-active", !isHand);
    tabHandwrite.classList.toggle("is-active", isHand);
    if (isHand) {
      // 等面板显示后再初始化画布尺寸与重绘
      requestAnimationFrame(initCanvasSize);
      redrawCanvas();
    }
  }

  tabText.addEventListener("click", function () { setMode("text"); });
  tabHandwrite.addEventListener("click", function () { setMode("handwrite"); });

  // ============================================================
  // Canvas：尺寸自适应（逻辑坐标固定 900×560，CSS 等比缩放）
  // ============================================================
  var LOGICAL_W = 900;
  var LOGICAL_H = 560;
  var ctx = canvas ? canvas.getContext("2d") : null;

  function initCanvasSize() {
    if (!canvas || !ctx) return;
    canvas.width = LOGICAL_W;
    canvas.height = LOGICAL_H;
    // 保证逻辑坐标与事件坐标一致：由 CSS 负责缩放，事件时按比例换算
  }

  function logicalPoint(event) {
    var rect = canvas.getBoundingClientRect();
    var scaleX = LOGICAL_W / rect.width;
    var scaleY = LOGICAL_H / rect.height;
    return [
      Math.min(LOGICAL_W, Math.max(0, (event.clientX - rect.left) * scaleX)),
      Math.min(LOGICAL_H, Math.max(0, (event.clientY - rect.top) * scaleY)),
    ];
  }

  // ============================================================
  // 绘制与重绘
  // ============================================================
  function drawStrokeSegment(stroke, fromIndex) {
    if (!ctx) return;
    var pts = stroke.points;
    if (!pts.length) return;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (stroke.tool === "eraser") {
      ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = "rgba(0,0,0,1)";
      ctx.lineWidth = Math.max(stroke.size, 16);
    } else {
      ctx.globalCompositeOperation = "source-over";
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.size;
    }
    ctx.beginPath();
    var start = Math.max(0, (fromIndex || 0) - 1);
    ctx.moveTo(pts[start][0], pts[start][1]);
    for (var i = start + 1; i < pts.length; i++) {
      ctx.lineTo(pts[i][0], pts[i][1]);
    }
    ctx.stroke();
    ctx.restore();
  }

  function redrawCanvas() {
    if (!ctx) return;
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, LOGICAL_W, LOGICAL_H);
    ctx.restore();
    strokes.forEach(function (s) { drawStrokeSegment(s, 0); });
  }

  // 新增一小段（当前进行中的笔画增量绘制）
  function appendDrawingPoint(point) {
    if (!drawing || !currentStroke || !ctx) return;
    currentStroke.points.push(point);
    drawStrokeSegment(currentStroke, currentStroke.points.length - 1);
  }

  // ============================================================
  // 指针事件（鼠标 / 触屏 / 触控笔）
  // ============================================================
  function pointerId(e) { return e.pointerId != null ? e.pointerId : "mouse"; }

  canvas.addEventListener("pointerdown", function (e) {
    e.preventDefault();
    drawing = true;
    currentStroke = {
      tool: currentTool,
      color: currentTool === "eraser" ? "#ffffff" : currentColor,
      size: currentTool === "eraser" ? Math.max(currentSize, 10) : currentSize,
      points: [logicalPoint(e)],
    };
    try { canvas.setPointerCapture(pointerId(e)); } catch (err) { /* 忽略 */ }
    strokes.push(currentStroke);
    drawStrokeSegment(currentStroke, 0);
  });

  canvas.addEventListener("pointermove", function (e) {
    if (!drawing) return;
    e.preventDefault();
    appendDrawingPoint(logicalPoint(e));
  });

  function endStroke() {
    drawing = false;
    currentStroke = null;
  }
  canvas.addEventListener("pointerup", endStroke);
  canvas.addEventListener("pointercancel", endStroke);
  canvas.addEventListener("pointerleave", function () { if (drawing) endStroke(); });

  // ============================================================
  // 工具栏：颜色 / 粗细 / 橡皮擦 / 撤销 / 清空
  // ============================================================
  function bindToolbar() {
    document.querySelectorAll(".hw-color").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (currentTool === "eraser") currentTool = "pen"; // 换色自动回到画笔
        currentColor = btn.dataset.color;
        document.querySelectorAll(".hw-color").forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        updateEraserState();
      });
    });

    var widthSel = document.getElementById("hw-width");
    if (widthSel) {
      widthSel.addEventListener("change", function () {
        currentSize = parseInt(widthSel.value, 10) || 4;
        if (currentTool === "eraser") currentTool = "pen";
        updateEraserState();
      });
    }

    var eraser = document.getElementById("hw-eraser");
    if (eraser) {
      eraser.addEventListener("click", function () {
        currentTool = currentTool === "eraser" ? "pen" : "eraser";
        updateEraserState();
      });
    }

    var undoBtn = document.getElementById("hw-undo");
    if (undoBtn) {
      undoBtn.addEventListener("click", function () {
        strokes.pop();
        redrawCanvas();
      });
    }

    var clearBtn = document.getElementById("hw-clear");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        if (!strokes.length) return;
        if (!window.confirm("确定清空全部手写内容吗？")) return;
        strokes = [];
        redrawCanvas();
      });
    }
  }

  function updateEraserState() {
    var eraser = document.getElementById("hw-eraser");
    if (!eraser) return;
    eraser.classList.toggle("is-active", currentTool === "eraser");
  }

  // ============================================================
  // 笔迹 ↔ SVG 序列化 / 反序列化
  // ============================================================
  function strokeToSvgPath(stroke) {
    var pts = stroke.points;
    if (!pts.length) return "";
    var d = "M" + pts[0][0].toFixed(1) + " " + pts[0][1].toFixed(1);
    for (var i = 1; i < pts.length; i++) {
      d += "L" + pts[i][0].toFixed(1) + " " + pts[i][1].toFixed(1);
    }
    var strokeColor = stroke.tool === "eraser" ? "#ffffff" : stroke.color;
    var width = stroke.tool === "eraser" ? Math.max(stroke.size, 16) : stroke.size;
    return '<path d="' + d + '" fill="none" stroke="' + strokeColor +
           '" stroke-width="' + width + '" stroke-linecap="round" stroke-linejoin="round"/>';
  }

  function buildSvgContent() {
    var lines = [SVG_MARK];
    lines.push("<!--note-data:" + JSON.stringify({
      w: LOGICAL_W, h: LOGICAL_H, strokes: strokes,
    }) + "-->");
    lines.push('<svg xmlns="http://www.w3.org/2000/svg" width="' + LOGICAL_W +
              '" height="' + LOGICAL_H + '" viewBox="0 0 ' + LOGICAL_W + " " + LOGICAL_H + '">');
    lines.push('<rect x="0" y="0" width="' + LOGICAL_W + '" height="' + LOGICAL_H +
              '" fill="#ffffff"/>');
    strokes.forEach(function (s) { lines.push(strokeToSvgPath(s)); });
    lines.push("</svg>");
    return lines.join("\n");
  }

  // 从已有 SVG 笔记内容恢复笔迹（解析 note-data JSON）
  function parseSvgContent(value) {
    if (!isSvgContent(value)) return false;
    var match = /<!--note-data:(\{.*?\})-->/.exec(value);
    if (!match) return false;
    try {
      var data = JSON.parse(match[1]);
      strokes = Array.isArray(data.strokes) ? data.strokes : [];
      redrawCanvas();
      return true;
    } catch (err) {
      return false;
    }
  }

  // ============================================================
  // 保存前同步：手写模式 → 写回 content（textarea）
  // ============================================================
  form.addEventListener("submit", function (event) {
    var mode = editorModeEl.value;
    if (mode === "handwrite") {
      // 有笔画才有内容；否则视为空并交给后端校验（标题为空提示）
      contentEl.value = strokes.length ? buildSvgContent() : "";
    }
  });

  // ============================================================
  // 初始化
  // ============================================================
  bindToolbar();

  var initial = tabs ? tabs.dataset.initial : "text";
  if (initial === "handwrite") {
    // 手写笔记：先切模式再由编辑器已有内容恢复笔迹
    setMode("handwrite");
    parseSvgContent(contentEl ? contentEl.value : "");
  } else {
    setMode("text");
  }
})();
