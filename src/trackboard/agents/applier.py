"""Assisted apply (BUILD_SPEC §8.5): open the real form headed, pre-fill from
profile_answers, attach the resume, STOP before submit. Never scheduled;
needs the [full] extra (`pip install -e ".[full]" && playwright install chromium`).

The field-matching logic is a pure function so it is testable without a
browser: labels and autocomplete attributes map to profile_answers keys.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

FIELD_MAP = [
    (r"first\s*name|given\s*name", "first_name"),
    (r"last\s*name|surname|family\s*name", "last_name"),
    (r"full\s*name|^name$", "full_name"),
    (r"e-?mail", "email"),
    (r"phone|mobile|contact\s*number", "phone"),
    (r"linkedin", "linkedin_url"),
    (r"github|portfolio|website", "github_url"),
    (r"notice\s*period", "notice_period_days"),
    (r"current\s*(ctc|salary|compensation)", "current_ctc"),
    (r"expected\s*(ctc|salary|compensation)", "expected_ctc"),
    (r"experience|years", "years_experience"),
    (r"location|city", "current_location"),
    (r"country", "country"),
    (r"company|organization|employer", "current_company"),
    (r"title|designation|role", "current_title"),
    (r"start\s*date.*month|month.*start", "start_date_month"),
    (r"start\s*date.*year|year.*start", "start_date_year"),
    (r"gender|sex", "gender"),
    (r"industry", "current_industry"),
    (r"career\s*stage", "career_stage"),
    (r"u\.?s\.?\s*visa", "visa_sponsorship"),
    (r"relocat", "willing_to_relocate"),
    (r"(work\s*)?(authorization|visa|sponsorship)", "work_authorization"),
]


def match_field(label: str, autocomplete: str | None = None) -> str | None:
    """Map a form field's visible label (or autocomplete attr) to an answers key."""
    if autocomplete:
        ac = autocomplete.lower()
        direct = {
            "email": "email",
            "tel": "phone",
            "name": "full_name",
            "given-name": "first_name",
            "family-name": "last_name",
            "address-level2": "current_location",
            "country": "country",
            "organization": "current_company",
            "organization-title": "current_title",
        }
        if ac in direct:
            return direct[ac]
    text = (label or "").lower()
    for rx, key in FIELD_MAP:
        if re.search(rx, text):
            return key
    return None


def ensure_master_pdf() -> Path:
    """Ensure a valid PDF exists on disk to attach to applications."""
    resumes_dir = Path.home() / ".trackboard" / "resumes"
    resumes_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = resumes_dir / "master_resume.pdf"
    if not pdf_path.exists() or pdf_path.stat().st_size < 100:
        bank_path = Path("config/resume.yaml")
        if bank_path.exists():
            import yaml
            from .. import tailor
            bank = yaml.safe_load(bank_path.read_text()) or {}
            tailor.render_pdf(
                bank,
                tailor.select_bullets(bank, ""),
                tailor.reorder_skills(bank, ""),
                pdf_path,
            )
    return pdf_path


def fill(apply_url: str, answers: dict[str, str], resume_path: str | None, headless: bool = False) -> int:
    from playwright.sync_api import sync_playwright

    # Ensure defaults for common questions
    answers = dict(answers)
    full_name = answers.get("full_name") or "Shourjya Hazra"
    parts = full_name.strip().split()
    answers.setdefault("full_name", full_name)
    answers.setdefault("first_name", parts[0] if parts else "Shourjya")
    answers.setdefault("last_name", " ".join(parts[1:]) if len(parts) > 1 else "Hazra")
    answers.setdefault("email", "shourjya001@gmail.com")
    answers.setdefault("phone", "+91-7679530903")
    raw_p = answers.get("phone") or "7679530903"
    digs = re.sub(r"\D", "", raw_p)
    if digs.startswith("91") and len(digs) > 10:
        digs = digs[2:]
    answers["phone_digits"] = digs[-10:] if len(digs) >= 10 else digs
    answers.setdefault("current_location", "Mumbai, India")
    answers.setdefault("city", "Mumbai")
    answers.setdefault("country", "India")
    answers.setdefault("current_company", "National Payments Corporation of India (NPCI)")
    answers.setdefault("current_title", "Software Developer")
    answers.setdefault("start_date_month", "10")
    answers.setdefault("start_date_year", "2024")
    answers.setdefault("linkedin_url", "https://www.linkedin.com/in/shourjya-hazra-683128200/")
    answers.setdefault("github_url", "https://github.com/shourjya01")
    answers.setdefault("years_experience", "2")
    answers.setdefault("notice_period_days", "30")
    answers.setdefault("current_ctc", "Confidential")
    answers.setdefault("expected_ctc", "Competitive")
    answers.setdefault("gender", "Male")
    answers.setdefault("current_industry", "FinTech / Financial Services")
    answers.setdefault("career_stage", "Mid-Level")
    answers.setdefault("visa_sponsorship", "No")
    answers.setdefault("work_authorization", "Yes")

    # Verify resume file path exists on disk
    if not resume_path or not Path(resume_path).exists() or resume_path.startswith("profile://"):
        resume_path = str(ensure_master_pdf())

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(apply_url, wait_until="domcontentloaded")

        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        # If page has an "Apply" button before form is visible, click it
        for btn_sel in [
            "a:has-text('Apply for this job')", "button:has-text('Apply for this job')",
            "a:has-text('Apply Now')", "button:has-text('Apply Now')",
            "a:has-text('Apply 1-Minute')", "button:has-text('Apply')",
            ".postings-btn", "[data-qa='apply-button']", "#apply_button",
        ]:
            btn = page.query_selector(btn_sel)
            if btn and btn.is_visible():
                try:
                    btn.click()
                    page.wait_for_timeout(1000)
                    break
                except Exception:
                    pass

        filled = 0
        seen_inputs = set()
        all_frames = [page] + page.frames

        # ── 1. File Upload (Resume/CV) across all frames ──
        if resume_path and Path(resume_path).exists():
            for frame in all_frames:
                for file_sel in [
                    "#resume",
                    "#_systemfield_resume",
                    "input[name='resume']",
                    "#resume-upload-input",
                    "input[type=file]",
                    "[data-qa='resume-upload']",
                ]:
                    for up in frame.query_selector_all(file_sel):
                        try:
                            up.set_input_files(str(resume_path))
                            up.dispatch_event("input")
                            up.dispatch_event("change")
                            filled += 1
                        except Exception:
                            pass

        # ── 2. Direct ATS Selectors (Greenhouse, Lever, Ashby) ──
        direct_selectors = [
            ("#first_name", "first_name"),
            ("#last_name", "last_name"),
            ("#email", "email"),
            ("#phone", "phone_digits"),
            ("input[name='name']", "full_name"),
            ("input[name='email']", "email"),
            ("input[name='phone']", "phone_digits"),
            ("input[name='phoneNumber']", "phone_digits"),
            ("input[name='org']", "current_company"),
            ("#company-name-0", "current_company"),
            ("#title-0", "current_title"),
            ("#start-date-month-0", "start_date_month"),
            ("#start-date-year-0", "start_date_year"),
            ("#question_8970664005", "linkedin_url"),
            ("#question_8970665005", "github_url"),
            ("#question_8970666005", "years_experience"),
            ("#question_8970671005", "current_location"),
            ("input[name*='urls[LinkedIn]']", "linkedin_url"),
            ("input[name*='urls[GitHub]']", "github_url"),
            ("input[name*='urls[Portfolio]']", "github_url"),
            ("input[name*='urls[Website]']", "github_url"),
            ("input[name*='linkedIn']", "linkedin_url"),
            ("input[name*='github']", "github_url"),
            ("input[id*='job_application_answers_attributes'][id*='linkedin']", "linkedin_url"),
            ("input[id*='job_application_answers_attributes'][id*='github']", "github_url"),
        ]

        for frame in all_frames:
            for sel, key in direct_selectors:
                val = answers.get(key)
                if not val:
                    continue
                for el in frame.query_selector_all(sel):
                    try:
                        if el.is_visible() and el not in seen_inputs:
                            el.fill(val)
                            el.dispatch_event("input")
                            el.dispatch_event("change")
                            seen_inputs.add(el)
                            filled += 1
                    except Exception:
                        pass

        # ── 3. Comboboxes & Custom Dropdowns (e.g. Greenhouse react-select) ──
        for frame in all_frames:
            for cb in frame.query_selector_all("input[role='combobox'], .select__input, input[aria-autocomplete='list']"):
                if cb in seen_inputs:
                    continue
                cid = cb.get_attribute("id") or ""
                label_text = ""
                if cid:
                    lab = frame.query_selector(f"label[for='{cid}']")
                    if lab:
                        label_text = lab.inner_text().strip().lower()
                if not label_text:
                    label_text = (cb.get_attribute("aria-label") or cb.get_attribute("placeholder") or "").lower()

                target_val = None
                if "gender" in label_text or "sex" in label_text:
                    target_val = "Male"
                elif "country" in label_text:
                    target_val = "India"
                elif "u.s. visa" in label_text or "sponsorship" in label_text:
                    target_val = "No"
                elif "industry" in label_text:
                    target_val = "Information Technology"
                elif "career stage" in label_text:
                    target_val = "Experienced Professional"
                elif "experience" in label_text:
                    target_val = "2"
                elif "location" in label_text or "city" in label_text:
                    target_val = "Mumbai"

                if target_val:
                    try:
                        cb.click()
                        page.wait_for_timeout(150)
                        page.keyboard.type(target_val, delay=30)
                        page.wait_for_timeout(250)
                        
                        # Find and click the exact matching option
                        clicked_opt = False
                        option_selectors = [
                            f"div[id^='react-select-{cid}-option']",
                            ".select__option",
                            "[role='option']",
                        ]
                        for o_sel in option_selectors:
                            opts = frame.query_selector_all(o_sel)
                            for opt in opts:
                                try:
                                    txt = opt.inner_text().strip()
                                    if target_val == "India":
                                        if txt.startswith("India ") or txt == "India" or txt == "India +91":
                                            opt.click()
                                            clicked_opt = True
                                            break
                                    elif target_val.lower() in txt.lower():
                                        opt.click()
                                        clicked_opt = True
                                        break
                                except Exception:
                                    pass
                            if clicked_opt:
                                break
                        
                        if not clicked_opt:
                            page.keyboard.press("Enter")
                        page.wait_for_timeout(150)
                        seen_inputs.add(cb)
                        filled += 1
                    except Exception:
                        pass

        # ── 4. Native <select> Elements (Lever, Workday, BambooHR) ──
        for frame in all_frames:
            for sel in frame.query_selector_all("select"):
                if sel in seen_inputs:
                    continue
                sid = sel.get_attribute("id") or ""
                sname = (sel.get_attribute("name") or "").lower()
                label_text = ""
                if sid:
                    lab = frame.query_selector(f"label[for='{sid}']")
                    if lab:
                        label_text = lab.inner_text().strip().lower()
                combined = f"{sid} {sname} {label_text}"

                target_text = None
                if "gender" in combined:
                    target_text = "Male"
                elif "race" in combined or "ethnicity" in combined:
                    target_text = "Asian"
                elif "veteran" in combined:
                    target_text = "not a veteran"
                elif "disability" in combined:
                    target_text = "No"
                elif "authorized" in combined:
                    target_text = "Yes"
                elif "sponsorship" in combined:
                    target_text = "No"
                elif "country" in combined:
                    target_text = "India"

                if target_text:
                    options = sel.query_selector_all("option")
                    matched_val = None
                    for opt in options:
                        opt_text = opt.inner_text().strip()
                        if target_text.lower() in opt_text.lower():
                            matched_val = opt.get_attribute("value") or opt_text
                            break
                    if matched_val:
                        try:
                            sel.select_option(value=matched_val)
                            sel.dispatch_event("input")
                            sel.dispatch_event("change")
                            seen_inputs.add(sel)
                            filled += 1
                        except Exception:
                            pass

        # ── 5. Checkboxes (Current Role, Consent, Agreements) ──
        for frame in all_frames:
            for chk in frame.query_selector_all("input[type=checkbox]"):
                cid = chk.get_attribute("id") or ""
                label_text = ""
                if cid:
                    lab = frame.query_selector(f"label[for='{cid}']")
                    if lab:
                        label_text = lab.inner_text().strip().lower()
                if "current role" in label_text or "currently work here" in label_text or "current-role" in cid:
                    try:
                        chk.check()
                        chk.dispatch_event("input")
                        chk.dispatch_event("change")
                        filled += 1
                    except Exception:
                        pass

        # ── 6. Heuristic Scan for all remaining text inputs & textareas ──
        for frame in all_frames:
            for inp in frame.query_selector_all("input[type=text], input[type=email], input[type=tel], input:not([type]), textarea"):
                if inp in seen_inputs:
                    continue
                label = ""
                fid = inp.get_attribute("id")
                if fid:
                    lab = frame.query_selector(f'label[for="{fid}"]')
                    label = lab.inner_text().strip() if lab else ""
                label = label or inp.get_attribute("name") or inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""
                key = match_field(label, inp.get_attribute("autocomplete"))
                if key and answers.get(key):
                    try:
                        val = answers[key]
                        inp.fill(val)
                        inp.dispatch_event("input")
                        inp.dispatch_event("change")
                        seen_inputs.add(inp)
                        filled += 1
                    except Exception:
                        pass

        # ── 7. Floating Feedback Banner ──
        banner_script = f"""() => {{
            const existing = document.getElementById('trackboard-assist-banner');
            if (existing) existing.remove();
            const b = document.createElement('div');
            b.id = 'trackboard-assist-banner';
            b.innerHTML = `
                <div style="display:flex;align-items:center;justify-content:space-between;max-width:960px;margin:0 auto;gap:16px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="background:#E3B341;color:#0D1117;font-weight:700;font-size:11px;padding:3px 8px;border-radius:4px;">⚡ AUTO-FILL</span>
                        <span style="font-weight:600;font-size:13px;color:#F0F6FC;">Trackboard pre-filled {filled} fields & attached your resume.</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:12px;">
                        <span style="font-size:12px;color:#8B949E;">Review answers carefully, then submit yourself.</span>
                        <button onclick="this.closest('#trackboard-assist-banner').remove()" style="background:transparent;border:1px solid #30363D;color:#C9D1D9;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:11px;">Dismiss</button>
                    </div>
                </div>
            `;
            b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:999999;background:rgba(13, 17, 23, 0.95);backdrop-filter:blur(12px);border-bottom:1px solid #30363D;color:#F0F6FC;font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:10px 16px;box-shadow:0 4px 20px rgba(0,0,0,0.5);';
            document.body.prepend(b);
        }}"""
        try:
            page.evaluate(banner_script)
        except Exception:
            pass

        if not headless:
            print(f"filled {filled} fields — browser stays open; review and submit yourself.")
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            browser.close()
        else:
            browser.close()
        return filled


def main() -> None:
    import sys
    from .. import db
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id", type=int)
    ap.add_argument("--user", required=True)
    args = ap.parse_args()
    user = db.query_one("SELECT id FROM users WHERE email=?", (args.user.lower(),))
    job = db.query_one("SELECT * FROM jobs WHERE id=?", (args.job_id,))
    if not user or not job:
        sys.exit("unknown user or job")
    answers = {r["key"]: r["value"] for r in
               db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))}
    tailored = db.query_one(
        "SELECT file_path FROM resumes WHERE user_id=? AND label LIKE ? ORDER BY id DESC LIMIT 1",
        (user["id"], f"%Job {args.job_id}%"),
    )
    resume = tailored or db.query_one(
        "SELECT file_path FROM resumes WHERE user_id=? AND file_path NOT LIKE 'profile://%' ORDER BY is_master DESC, id DESC LIMIT 1",
        (user["id"],),
    )
    resume_path = resume["file_path"] if resume else str(ensure_master_pdf())
    fill(job["apply_url"], answers, resume_path)


if __name__ == "__main__":
    main()
