/* Live agent flow: polls /api/agents/state, lights nodes from real runs, and replays the
   last run as particles along the edges. No fabricated numbers: counters come from agent_runs. */
(function () {
  "use strict";
  var flow = document.getElementById("flow"); if (!flow) return;
  var svg = flow.querySelector("svg");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var state = {};
  try { state = JSON.parse(flow.getAttribute("data-state") || "{}"); } catch (e) {}

  function setText(el, t) { if (el) el.textContent = t; }
  function apply(s) {
    if (!s || !s.nodes) return;
    s.nodes.forEach(function (n) {
      var g = svg.querySelector('.agent[data-agent="' + n.key + '"]');
      if (g) {
        g.setAttribute("data-status", n.status);
        setText(g.querySelector("[data-sub]"), n.status === "idle" ? "no run yet" : n.status + " · " + (n.ago || "") + " · " + n.items_in + " in / " + n.items_out + " out");
      }
      var card = document.querySelector('.node-card[data-agent="' + n.key + '"]');
      if (card) {
        var st = card.querySelector("[data-status]"); if (st) { st.className = "status " + n.status; st.textContent = n.status; }
        setText(card.querySelector("[data-in]"), n.items_in); setText(card.querySelector("[data-out]"), n.items_out); setText(card.querySelector("[data-ago]"), n.ago || "no run yet");
      }
    });
    var jobs = svg.querySelector('[data-count="open_jobs"]'); if (jobs && s.totals) jobs.textContent = s.totals.open_jobs.toLocaleString() + " open · " + s.totals.companies + " companies";
    var badge = document.getElementById("live-badge"); if (badge) badge.classList.toggle("running", !!s.any_running);
    var tb = document.querySelector("#events tbody");
    if (tb && s.events && s.events.length) {
      while (tb.firstChild) tb.removeChild(tb.firstChild);
      s.events.forEach(function (e) {
        var tr = document.createElement("tr");
        [["Agent", e.agent], ["Status", e.status], ["When", e.ago], ["In", e.items_in], ["Out", e.items_out], ["LLM", e.llm_calls]].forEach(function (c, i) {
          var td = document.createElement("td"); td.setAttribute("data-label", c[0]);
          if (i === 1) { var sp = document.createElement("span"); sp.className = "status " + c[1]; sp.textContent = c[1]; td.appendChild(sp); }
          else { td.textContent = c[1]; if (i >= 3) td.className = "num"; }
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
    }
  }
  apply(state);

  function poll() {
    fetch("/api/agents/state", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) { if (s) { state = s; apply(s); } }).catch(function () {});
  }
  var timer = setInterval(poll, 15000);
  document.addEventListener("visibilitychange", function () { if (document.hidden) { clearInterval(timer); } else { poll(); timer = setInterval(poll, 15000); } });

  // ---- replay: walk the real pipeline order, light each node, fire particles on its edges ----
  var STEPS = [
    { agent: "scout", edges: ["e1", "e4"], table: "jobs" },
    { agent: "matcher", edges: ["e7", "e11"], table: "matches" },
    { agent: "digest", edges: ["e8", "e12"], table: null },
    { agent: "inbox", edges: ["e2", "e5"], table: "applications" },
    { agent: "tailor", edges: ["e9"], table: null },
    { agent: "leetcode_sync", edges: ["e3", "e6", "e10"], table: "reviews" }
  ];
  function fire(edgeId) {
    var p = svg.querySelector('.particle[data-edge="' + edgeId + '"]'); if (!p) return;
    var am = p.querySelector("animateMotion"); p.classList.add("on");
    var path = svg.querySelector("#" + edgeId); if (path) path.classList.add("hot");
    try { am.beginElement(); } catch (e) {}
    setTimeout(function () { p.classList.remove("on"); if (path) path.classList.remove("hot"); }, 1000);
  }
  function countTo(el, target, ms) {
    if (!el) return; var start = 0, t0 = performance.now(); target = Number(target) || 0;
    if (reduce) { el.textContent = target; return; }
    (function tick(now) { var k = Math.min(1, (now - t0) / ms); el.textContent = Math.round(start + (target - start) * k); if (k < 1) requestAnimationFrame(tick); })(t0);
  }
  var replaying = false;
  document.getElementById("replay-btn").addEventListener("click", function () {
    if (replaying) return; replaying = true; var btn = this; btn.disabled = true;
    var i = 0;
    (function step() {
      if (i >= STEPS.length) { replaying = false; btn.disabled = false; svg.querySelectorAll(".agent.active").forEach(function (g) { g.classList.remove("active"); }); return; }
      var st = STEPS[i++]; var g = svg.querySelector('.agent[data-agent="' + st.agent + '"]');
      svg.querySelectorAll(".agent.active").forEach(function (x) { x.classList.remove("active"); });
      if (g) g.classList.add("active");
      var n = (state.nodes || []).filter(function (x) { return x.key === st.agent; })[0] || { items_in: 0, items_out: 0 };
      var card = document.querySelector('.node-card[data-agent="' + st.agent + '"]');
      if (card) { countTo(card.querySelector("[data-in]"), n.items_in, 700); setTimeout(function () { countTo(card.querySelector("[data-out]"), n.items_out, 700); }, 400); }
      if (st.table) { var t = svg.querySelector('.tbl[data-table="' + st.table + '"]'); if (t) { t.classList.add("pulse"); setTimeout(function () { t.classList.remove("pulse"); }, 900); } }
      if (!reduce) st.edges.forEach(function (e, k) { setTimeout(function () { fire(e); }, k * 350); });
      setTimeout(step, reduce ? 300 : 1300);
    })();
  });
})();
