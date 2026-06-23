document.addEventListener("DOMContentLoaded", function () {
  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

  // Hamburger / sidebar toggle
  var hamburger = document.getElementById("hamburger");
  var sidebar = document.getElementById("sidebar");
  var overlay = document.getElementById("overlay");

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("open");
    if (overlay) overlay.classList.remove("show");
    if (hamburger) hamburger.classList.remove("active");
  }

  function toggleSidebar() {
    if (sidebar) sidebar.classList.toggle("open");
    if (overlay) overlay.classList.toggle("show");
    if (hamburger) hamburger.classList.toggle("active");
  }

  if (hamburger) hamburger.addEventListener("click", toggleSidebar);
  if (overlay) overlay.addEventListener("click", closeSidebar);

  // Notification bell badge polling
  var bellBadge = document.getElementById("bellBadge");
  function pollNotifications() {
    fetch("/notifications/poll")
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data || !bellBadge) return;
        if (data.unread > 0) {
          bellBadge.textContent = data.unread > 99 ? "99+" : data.unread;
          bellBadge.style.display = "inline-block";
        } else {
          bellBadge.style.display = "none";
        }
      })
      .catch(function () {});
  }
  if (bellBadge) {
    pollNotifications();
    setInterval(pollNotifications, 20000);
  }

  // Mark single notification read on click
  document.querySelectorAll(".notif-mark-read").forEach(function (el) {
    el.addEventListener("click", function (e) {
      var id = el.getAttribute("data-id");
      fetch("/notifications/mark-read/" + id, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken }
      }).then(function () {
        el.closest(".notif-item").classList.remove("unread");
      });
    });
  });

  var markAllBtn = document.getElementById("markAllRead");
  if (markAllBtn) {
    markAllBtn.addEventListener("click", function () {
      fetch("/notifications/mark-all-read", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken }
      }).then(function () {
        document.querySelectorAll(".notif-item.unread").forEach(function (el) {
          el.classList.remove("unread");
        });
        if (bellBadge) bellBadge.style.display = "none";
      });
    });
  }

  // Live client-side filter for simple tables (data-search-row)
  var liveSearch = document.getElementById("liveSearch");
  if (liveSearch) {
    liveSearch.addEventListener("input", function () {
      var term = liveSearch.value.toLowerCase();
      var rows = document.querySelectorAll("[data-search-row]");
      rows.forEach(function (row) {
        var text = row.textContent.toLowerCase();
        row.style.display = text.indexOf(term) > -1 ? "" : "none";
      });
    });
  }

  // Password show/hide eye-icon toggles
  document.querySelectorAll(".pw-eye").forEach(function (icon) {
    icon.addEventListener("click", function () {
      var input = document.getElementById(icon.getAttribute("data-target"));
      if (!input) return;
      if (input.type === "password") {
        input.type = "text";
        icon.classList.remove("fa-eye");
        icon.classList.add("fa-eye-slash");
      } else {
        input.type = "password";
        icon.classList.remove("fa-eye-slash");
        icon.classList.add("fa-eye");
      }
    });
  });

  // Auto-dismiss flash alerts
  document.querySelectorAll(".alert[data-autodismiss]").forEach(function (el) {
    setTimeout(function () {
      el.style.transition = "opacity 0.4s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 400);
    }, 4500);
  });
});
