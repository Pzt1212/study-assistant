/* ============================================================
   学习助手 - 管理端脚本
   职责：移动端侧边栏开合（汉堡按钮 + 遮罩 + 点击导航后自动收起）
   ============================================================ */
(function () {
  "use strict";

  var sidebar = document.getElementById("adminSidebar");
  var backdrop = document.getElementById("adminBackdrop");
  var menuBtn = document.getElementById("adminMenuBtn");

  function isMobile() {
    return window.innerWidth <= 980;
  }

  function openMenu() {
    if (!sidebar || !backdrop) return;
    sidebar.classList.add("is-open");
    backdrop.classList.add("is-show");
    document.body.style.overflow = "hidden";
  }

  function closeMenu() {
    if (!sidebar || !backdrop) return;
    sidebar.classList.remove("is-open");
    backdrop.classList.remove("is-show");
    document.body.style.overflow = "";
  }

  if (menuBtn) {
    menuBtn.addEventListener("click", function () {
      if (sidebar && sidebar.classList.contains("is-open")) {
        closeMenu();
      } else {
        openMenu();
      }
    });
  }

  if (backdrop) {
    backdrop.addEventListener("click", closeMenu);
  }

  // 点击侧边栏内的链接后，移动端自动收起菜单
  if (sidebar) {
    sidebar.addEventListener("click", function (event) {
      if (event.target.closest("a")) closeMenu();
    });
  }

  // 窗口拉宽时自动复位
  window.addEventListener("resize", function () {
    if (!isMobile()) closeMenu();
  });
})();
