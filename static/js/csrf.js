/* ============================================================
   全站 CSRF 令牌注入（配合服务端 services/csrf.py）
   - 读取 <head> 中的 meta[name="csrf-token"]
   - 给页面上每个 <form> 自动追加 hidden[name="csrf_token"]
   - 包装 window.fetch：非 GET 请求自动带 X-CSRFToken 头
   ============================================================ */
(function () {
  "use strict";
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta) return;
  var token = meta.getAttribute("content") || "";

  function patchForms() {
    if (!token) return;
    document.querySelectorAll("form").forEach(function (f) {
      if (!f.querySelector('input[name="csrf_token"]')) {
        var i = document.createElement("input");
        i.type = "hidden";
        i.name = "csrf_token";
        i.value = token;
        f.appendChild(i);
      }
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", patchForms);
  } else {
    patchForms();
  }

  var nativeFetch = window.fetch;
  if (typeof nativeFetch === "function" && token) {
    window.fetch = function (input, init) {
      init = init || {};
      var method = ((init.method || (input && input.method) || "GET") + "").toUpperCase();
      if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
        if (init.headers instanceof Headers) {
          if (!init.headers.has("X-CSRFToken")) init.headers.set("X-CSRFToken", token);
        } else {
          init.headers = init.headers || {};
          if (!init.headers["X-CSRFToken"]) init.headers["X-CSRFToken"] = token;
        }
      }
      return nativeFetch.call(this, input, init);
    };
  }
})();
