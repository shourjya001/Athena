/* LinkedIn audit page: builds results with DOM APIs (never innerHTML with user data). */
(function () {
  "use strict";
  var form = document.getElementById("li-form"); if (!form) return;
  var $ = function (id) { return document.getElementById(id); };
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-copy-from]"); if (!b) return;
    var src = $(b.getAttribute("data-copy-from")); if (!src) return;
    navigator.clipboard && navigator.clipboard.writeText(src.textContent || "").then(function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy"; }, 1500); });
  });

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (form.getAttribute("data-authenticated") !== "1") return;
    var btn = $("li-submit"), status = $("li-status");
    var mode = (form.querySelector('input[name="mode"]:checked') || {}).value || "standard";
    var payload = {
      linkedin_url: $("li-url").value.trim(), target_audience: $("li-audience").value.trim(), goal: $("li-goal").value,
      headline: $("li-headline").value.trim(), about: $("li-about").value.trim(), experiences: $("li-experiences").value.trim(), mode: mode
    };
    btn.disabled = true; status.textContent = "Running the " + mode + " audit…";
    window.athenaFetch("/a/linkedin/optimize", payload).then(function (r) {
      if (r.status === 429) throw new Error("Too many audits in a short time. Try again in a few minutes.");
      if (r.status === 403) throw new Error("Session expired. Reload the page and try again.");
      return r.json();
    }).then(function (data) {
      if (!data.ok) throw new Error(data.error || "The audit failed.");
      render(data.data, data.llm); status.textContent = "";
    }).catch(function (e) { status.textContent = e.message || String(e); }).finally(function () { btn.disabled = false; });
  });

  function render(d, llmUsed) {
    var res = $("li-results"); res.hidden = false;
    $("li-offline").hidden = !!llmUsed;
    var a = d.audit_scores || {};
    $("li-total").textContent = a.total != null ? a.total : "—";
    var scores = $("li-scores"); clear(scores);
    [["Headline", a.headline], ["About", a.about], ["Experience", a.experience], ["Featured / proof", a.featured], ["Fit for goal", a.fit]].forEach(function (p) {
      var row = el("div", "pillar"); row.appendChild(el("span", null, p[0]));
      var bar = el("div", "bar"); var fill = el("i"); fill.style.width = Math.max(0, Math.min(100, (p[1] || 0) * 10)) + "%"; bar.appendChild(fill); row.appendChild(bar);
      row.appendChild(el("span", "score", (p[1] != null ? p[1] : "—") + "/10")); scores.appendChild(row);
    });
    var fixes = $("li-fixes"); clear(fixes);
    (d.priority_fixes || []).forEach(function (f) { var li = el("li"); var b = el("b", null, (f.section || "") + ": "); li.appendChild(b); li.appendChild(document.createTextNode(f.fix || "")); fixes.appendChild(li); });
    var buzz = $("li-buzz"); clear(buzz);
    if ((d.buzzwords_found || []).length) { d.buzzwords_found.forEach(function (b) { var p = el("p", "small"); p.appendChild(el("b", null, b.buzzword)); p.appendChild(document.createTextNode(" → " + (b.replacement || ""))); buzz.appendChild(p); }); }
    else buzz.appendChild(el("p", "muted", "No generic buzzwords found."));
    var hls = $("li-headlines"); clear(hls); var h = d.headlines || {};
    [["Authority-forward", h.variant_a], ["Outcome-forward", h.variant_b], ["Niche-specific", h.variant_c]].forEach(function (v, i) {
      if (!v[1]) return; var box = el("div", "notice"); var span = el("span"); span.id = "li-hl-" + i; span.appendChild(el("b", null, v[0] + ": ")); span.appendChild(document.createTextNode(v[1])); box.appendChild(span);
      var c = el("button", "btn sm", "Copy"); c.type = "button"; c.setAttribute("data-copy-from", "li-hl-" + i); box.appendChild(c); hls.appendChild(box);
    });
    if (!hls.children.length) hls.appendChild(el("p", "muted", "No headline rewrite available for this run."));
    $("li-ab").textContent = h.ab_recommendation ? "A/B suggestion: " + h.ab_recommendation : "";
    var ab = d.about || {}; $("li-about-text").textContent = ab.rewrite || "No About rewrite available for this run.";
    $("li-about-wc").textContent = ab.rewrite ? (ab.word_count || ab.rewrite.split(/\s+/).length) + " words" : "";
    var bl = $("li-bullets"); clear(bl);
    (d.experience_bullets || []).forEach(function (b) { var box = el("div", "notice"); var w = el("div"); w.appendChild(el("div", "small muted", "Before: " + (b.before || ""))); w.appendChild(el("div", null, "After: " + (b.after || ""))); box.appendChild(w); bl.appendChild(box); });
    if (!bl.children.length) bl.appendChild(el("p", "muted", "Add a few experience bullets to get rewrites."));
    var ai = d.ai_visibility || {}; $("li-ai").textContent = ai.score != null ? ai.score : "—";
    var ch = $("li-ai-checks"); clear(ch);
    (ai.checks || []).forEach(function (c) { var box = el("div", "notice " + (c.status === "pass" ? "ok" : c.status === "needs_work" ? "warn" : "danger")); var w = el("div"); w.appendChild(el("b", null, c.name || "")); w.appendChild(el("div", "small", c.detail || "")); box.appendChild(w); ch.appendChild(box); });
    var mv = $("li-ai-moves"); clear(mv); (ai.top_moves || []).forEach(function (m) { mv.appendChild(el("li", null, m)); });
    var posts = d.sample_posts || []; $("li-posts-wrap").hidden = !posts.length; var pc = $("li-posts"); clear(pc);
    posts.forEach(function (p, i) { var box = el("div", "notice"); var t = el("div"); t.id = "li-post-" + i; t.style.whiteSpace = "pre-wrap"; t.textContent = p; box.appendChild(t); var c = el("button", "btn sm", "Copy"); c.type = "button"; c.setAttribute("data-copy-from", "li-post-" + i); box.appendChild(c); pc.appendChild(box); });
    res.scrollIntoView({ behavior: "smooth", block: "start" });
  }
})();
