import json
import re
import sys
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))
from build_pattern_approaches import main as get_multi_approach_patterns

patterns_data = get_multi_approach_patterns()

# Read the base template from pattern.html
pattern_html_path = Path("src/trackboard/templates/pages/pattern.html")
html = pattern_html_path.read_text(encoding="utf-8")

# 1. Add CSS for Approach Buttons
approach_css = """
.pt-appr-btn {
  background: #161b22;
  border: 1px solid #30363d;
  color: #c9d1d9;
  font-size: 11.5px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.pt-appr-btn:hover {
  background: #21262d;
  border-color: #8b949e;
  color: #f0f6fc;
}
.pt-appr-btn.active {
  background: rgba(56, 139, 253, 0.15);
  border-color: #58a6ff;
  color: #58a6ff;
  box-shadow: 0 0 8px rgba(88, 166, 255, 0.25);
}
"""

if ".pt-appr-btn" not in html:
    html = html.replace("</style>", f"{approach_css}\n</style>", 1)

# 2. Add Approach Selector Bar inside pt-workbench right above pt-split
approach_bar_html = """  {# Approach Selector Bar: Brute Force vs Optimal vs Best #}
  <div class="pt-approach-bar" id="pt-approach-bar" style="display:flex;justify-content:space-between;align-items:center;padding:10px 16px;background:rgba(255,255,255,0.02);border-bottom:1px solid #21262d;flex-wrap:wrap;gap:8px;">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      <span style="font-size:11px;font-weight:700;color:#8b949e;text-transform:uppercase;letter-spacing:0.05em;">Algorithm Approach:</span>
      <button type="button" class="pt-appr-btn active" data-approach="optimal" id="appr-optimal">⚡ Optimal Solution</button>
      <button type="button" class="pt-appr-btn" data-approach="brute" id="appr-brute">🐢 Brute Force O(N²)</button>
      <button type="button" class="pt-appr-btn" data-approach="best" id="appr-best">🏆 Best (Space-Optimal O(1))</button>
    </div>
    <div id="pt-complexity-badge" style="font-family:monospace;font-size:11.5px;color:#e3b341;background:rgba(227,179,65,0.1);padding:3px 10px;border-radius:6px;border:1px solid rgba(227,179,65,0.25);">
      Time: O(N) · Space: O(1)
    </div>
  </div>

  {# Split-Pane Workbench #}"""

if "pt-approach-bar" not in html:
    html = html.replace("{# Split-Pane Workbench #}", approach_bar_html, 1)

# 3. Replace the DB definition with the multi-approach dataset
patterns_json = json.dumps(patterns_data, indent=2)
db_replacement = f"  const DB = {patterns_json};\n"

start_idx = html.find("  const DB = {")
end_idx = html.find("  let activeLang = 'python';", start_idx)
if start_idx != -1 and end_idx != -1:
    html = html[:start_idx] + db_replacement + html[end_idx:]

# 4. Update the JavaScript state and event listeners for approaches
old_js_init = "  let activeLang = 'python';"
new_js_init = """  let activeLang = 'python';
  let activeApproach = 'optimal';

  function getActiveModel() {
    const pData = DB[slug];
    if (!pData) return null;
    if (pData.approaches && pData.approaches[activeApproach]) {
      return pData.approaches[activeApproach];
    }
    return pData;
  }

  let model = getActiveModel();
  if (!model) {
    console.error("No model found for pattern:", slug);
    return;
  }"""

if "let activeApproach = 'optimal';" not in html:
    html = html.replace(old_js_init, new_js_init, 1)

# Update approach buttons listener
old_listeners_hook = "// Language Tab Toggles"
new_listeners_hook = """  // Approach Selector Toggles (Brute Force vs Optimal vs Best)
  const apprBtns = document.querySelectorAll('.pt-appr-btn');
  const complexityBadge = document.getElementById('pt-complexity-badge');

  apprBtns.forEach(btn => {
    btn.onclick = function() {
      apprBtns.forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      activeApproach = this.getAttribute('data-approach');
      model = getActiveModel();
      currentStep = 0;
      if (complexityBadge && model.complexity) {
        complexityBadge.textContent = model.complexity;
      }
      const lines = (activeLang === 'cpp' && model.code_cpp) ? model.code_cpp : 
                    (activeLang === 'java' && model.code_java) ? model.code_java : 
                    model.code;
      if (activeFunc && lines.length > 0) {
        activeFunc.textContent = lines[0].replace(/\\s*\\{.*$/, '');
      }
      render();
    };
  });

  // Language Tab Toggles"""

if "// Approach Selector Toggles" not in html:
    html = html.replace(old_listeners_hook, new_listeners_hook, 1)

pattern_html_path.write_text(html, encoding="utf-8")
print(f"✓ Successfully compiled pattern.html ({len(html)} bytes) with Brute Force / Optimal / Best across Python, C++, and Java!")
