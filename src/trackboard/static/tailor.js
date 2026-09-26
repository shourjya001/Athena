(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  document.addEventListener("change", function (ev) {
    var cb = ev.target.closest("[data-toggle-target]"); if (!cb) return;
    var ta = $(cb.getAttribute("data-toggle-target")); if (!ta) return;
    ta.disabled = !cb.checked; ta.style.opacity = cb.checked ? "1" : ".5";
  });
  var run = $("dv-run"); if (!run) return;
  run.addEventListener("click", function () {
    var skill = $("dv-skill").value.trim(), notes = $("dv-notes").value.trim(), status = $("dv-status");
    var branch = (document.querySelector('input[name="dv-branch"]:checked') || {}).value || "direct";
    if (!skill || !notes) { status.textContent = "Add the skill and a sentence about what you did."; return; }
    run.disabled = true; status.textContent = "Writing…";
    window.athenaFetch("/a/jobs/" + run.getAttribute("data-job") + "/discover-bullet", { skill_gap: skill, user_notes: notes, experience_type: branch })
      .then(function (r) { if (r.status === 429) throw new Error("Too many requests. Wait a few minutes."); return r.json(); })
      .then(function (d) { if (!d.ok) throw new Error(d.error || "Failed"); $("dv-result").hidden = false; $("dv-bullet").value = d.data.bullet || ""; $("dv-metric").textContent = d.data.metric_highlight ? "Highlights: " + d.data.metric_highlight : ""; status.textContent = ""; })
      .catch(function (e) { status.textContent = e.message; }).finally(function () { run.disabled = false; });
  });
  $("dv-save").addEventListener("click", function () {
    var b = $("dv-bullet").value.trim(), status = $("dv-status"); if (!b) return;
    window.athenaFetch("/a/jobs/" + run.getAttribute("data-job") + "/save-bullet-to-bank", { bullet: b, skill: $("dv-skill").value.trim() })
      .then(function (r) { return r.json(); }).then(function (d) { status.textContent = d.ok ? (d.message || "Saved.") : (d.error || "Failed"); })
      .catch(function (e) { status.textContent = e.message; });
  });
})();
