/* Athena — small, dependency-free behaviours. No inline handlers anywhere (CSP). */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement;

  // ---- theme ----
  var THEME_KEY = "athena.theme";
  function applyTheme(t) { if (t) root.setAttribute("data-theme", t); else root.removeAttribute("data-theme"); }
  try { applyTheme(localStorage.getItem(THEME_KEY) || ""); } catch (e) {}
  doc.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-theme-toggle]"); if (!b) return;
    var cur = root.getAttribute("data-theme");
    var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    var isDark = cur ? cur === "dark" : prefersDark;
    var next = isDark ? "light" : "dark";
    applyTheme(next); try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  });

  // ---- csrf for fetch/htmx ----
  var csrf = (doc.querySelector('meta[name="csrf-token"]') || {}).content || "";
  doc.body.addEventListener("htmx:configRequest", function (ev) { ev.detail.headers["X-CSRF-Token"] = csrf; });
  window.athenaFetch = function (url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(Object.assign({}, body || {}, { csrf_token: csrf })), credentials: "same-origin" });
  };

  // ---- job card expand/collapse ----
  doc.addEventListener("click", function (ev) {
    var h = ev.target.closest(".job-head"); if (!h) return;
    if (ev.target.closest("a,button:not(.job-head),form")) return;
    var body = h.parentNode.querySelector(".job-body"); if (!body) return;
    var open = h.getAttribute("aria-expanded") === "true";
    h.setAttribute("aria-expanded", open ? "false" : "true");
    body.classList.toggle("open", !open);
  });
  doc.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var h = ev.target.closest && ev.target.closest(".job");
    if (!h) return;
    var head = h.querySelector(".job-head"), body = h.querySelector(".job-body");
    if (head && head.getAttribute("aria-expanded") === "true") { head.setAttribute("aria-expanded", "false"); body.classList.remove("open"); head.focus(); }
  });

  // ---- copy chips ----
  doc.addEventListener("click", function (ev) {
    var c = ev.target.closest("[data-copy]"); if (!c) return;
    var text = c.getAttribute("data-copy") || "";
    var done = function () { c.setAttribute("data-copied", "1"); c.setAttribute("aria-label", "Copied"); setTimeout(function () { c.removeAttribute("data-copied"); }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, done);
    else { var ta = doc.createElement("textarea"); ta.value = text; doc.body.appendChild(ta); ta.select(); try { doc.execCommand("copy"); } catch (e) {} ta.remove(); done(); }
  });

  // ---- video facades (no iframe until click) ----
  doc.addEventListener("click", function (ev) {
    var t = ev.target.closest(".thumb[data-yt]"); if (!t) return;
    var id = t.getAttribute("data-yt"), start = t.getAttribute("data-start") || "0";
    var f = doc.createElement("iframe");
    f.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) + "?autoplay=1&start=" + encodeURIComponent(start) + "&rel=0";
    f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
    f.setAttribute("allowfullscreen", ""); f.title = t.getAttribute("aria-label") || "Video";
    t.replaceWith(f);
  });

  // ---- auto-submit selects (pipeline status) ----
  doc.addEventListener("change", function (ev) {
    var s = ev.target.closest("select[data-autosubmit]"); if (s && s.form) s.form.submit();
  });

  // ---- confirm dialogs ----
  doc.addEventListener("submit", function (ev) {
    var f = ev.target; var msg = f.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) ev.preventDefault();
  });

  // ---- filter forms: submit on change via htmx if present ----
  var fform = doc.getElementById("filters");
  if (fform) fform.addEventListener("change", function () { if (window.htmx) window.htmx.trigger(fform, "submit"); else fform.submit(); });

  // ---- keep a live region updated after htmx swaps ----
  doc.body.addEventListener("htmx:afterSwap", function (ev) {
    var live = doc.getElementById("live"); var count = doc.querySelector("[data-result-count]");
    if (live && count) live.textContent = count.getAttribute("data-result-count") + " results";
  });
})();
