"""Per-JD resume generation from the bullet bank (BUILD_SPEC §8.4).

The master resume is resume.yaml — structured, honest, written once. Tailoring
selects and reorders; it can never invent. Rendering is a single-column fpdf2
template designed to parse cleanly by construction, and §8.4.3's gate re-runs
the parse simulator on the output and refuses to save regressions.

Note: fpdf2 core fonts are latin-1; non-latin characters are transliterated.
Swap in an embedded unicode font (fpdf2 add_font) if the resume needs one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from fpdf import FPDF
from rank_bm25 import BM25Okapi

from .analyst import ParseReport, analyse_pdf, report_regression

BUDGET = {"recent": 5, "older": 3}   # bullets per role


def load_bank(path: Path) -> dict:
    bank = yaml.safe_load(path.read_text())
    ids = [b["id"] for role in bank.get("roles", []) for b in role.get("bullets", [])]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate bullet ids in resume.yaml")
    return bank


def _tok(t: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", (t or "").lower())


def select_bullets(bank: dict, jd_text: str) -> dict[str, list[dict]]:
    """Per role: bullets ranked by BM25 relevance to the JD, capped by budget.
    Returns {role_company: [bullet, ...]} preserving rank order."""
    chosen: dict[str, list[dict]] = {}
    for idx, role in enumerate(bank.get("roles", [])):
        bullets = role.get("bullets", [])
        if not bullets:
            continue
        corpus = [_tok(b["text"] + " " + " ".join(b.get("skills", []))) for b in bullets]
        scores = BM25Okapi(corpus).get_scores(_tok(jd_text)) if jd_text else [0] * len(bullets)
        ranked = sorted(zip(bullets, scores), key=lambda x: x[1], reverse=True)
        cap = BUDGET["recent"] if idx == 0 else BUDGET["older"]
        chosen[role["company"]] = [b for b, _ in ranked[:cap]]
    return chosen


def reorder_skills(bank: dict, jd_text: str) -> list[str]:
    flat: list[str] = []
    for group in (bank.get("skills") or {}).values():
        flat.extend(group or [])
    jd = (jd_text or "").lower()
    return sorted(dict.fromkeys(flat), key=lambda s: (s.lower() not in jd, flat.index(s)))


@dataclass
class RenderResult:
    path: Path | None
    report: ParseReport | None
    regressions: list[str]
    bullet_ids: list[str]


def _latin(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1")


def render_pdf(bank: dict, chosen: dict[str, list[dict]], skills: list[str],
               out_path: Path) -> list[str]:
    ident = bank.get("identity", {})
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(16, 14, 16)

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _latin(ident.get("name", "")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    contact = " | ".join(x for x in [ident.get("email"), ident.get("phone"),
                                     ident.get("linkedin"), ident.get("github"),
                                     ident.get("location")] if x)
    pdf.cell(0, 5, _latin(contact), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    def heading(text: str):
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9.5)

    if skills:
        heading("Skills")
        pdf.multi_cell(0, 4.6, _latin(", ".join(skills)), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    heading("Experience")
    used: list[str] = []
    for role in bank.get("roles", []):
        picks = chosen.get(role["company"], [])
        if not picks:
            continue
        pdf.set_font("Helvetica", "B", 10)
        span = f"{role.get('start','')} - {role.get('end','')}"
        pdf.cell(0, 5.4, _latin(f"{role.get('title','')} · {role['company']}  ({span})"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9.5)
        for b in picks:
            pdf.multi_cell(0, 4.6, _latin("- " + b["text"]), new_x="LMARGIN", new_y="NEXT")
            used.append(b["id"])
        pdf.ln(1)

    edu = bank.get("education") or []
    if edu:
        heading("Education")
        for e in edu:
            pdf.multi_cell(0, 4.6, _latin(f"{e.get('degree','')} - {e.get('school','')} "
                                          f"({e.get('year','')})"), new_x="LMARGIN", new_y="NEXT")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    return used


def bank_to_text(bank: dict) -> str:
    """Format bullet bank into readable text for ATS matching/scoring."""
    parts = []
    ident = bank.get("identity") or {}
    if ident.get("name"):
        parts.append(f"{ident['name']} | {ident.get('email','')} | {ident.get('location','')}")
    if bank.get("summary"):
        parts.append(f"Summary: {bank['summary']}")
    for role in bank.get("roles", []):
        parts.append(f"\n{role.get('title')} · {role.get('company')} ({role.get('start')} - {role.get('end')})")
        for b in role.get("bullets", []):
            parts.append(f"- {b['text']}")
    if bank.get("projects"):
        parts.append("\nProjects:")
        for p in bank["projects"]:
            parts.append(f"- {p.get('name')}: {p.get('description')}")
    if bank.get("skills"):
        parts.append("\nSkills:")
        for grp, sks in bank["skills"].items():
            parts.append(f"  {grp}: {', '.join(sks)}")
    return "\n".join(parts)


def suggest_tailoring(bank: dict, jd_text: str, chain: any = None) -> dict:
    """Select top bullets per role, reorder skills, and optionally call LLM
    to suggest vocabulary alignment rewrites without changing factual meaning."""
    chosen = select_bullets(bank, jd_text)
    skills = reorder_skills(bank, jd_text)

    diff_roles = []
    flat_bullets = []
    for role in bank.get("roles", []):
        picks = chosen.get(role["company"], [])
        if not picks:
            continue
        role_diffs = []
        for b in picks:
            diff_item = {
                "id": b["id"],
                "original": b["text"],
                "tailored": b["text"],
                "skills": b.get("skills", []),
                "theme": b.get("theme", ""),
                "rationale": "Selected as high-priority match for this job description.",
            }
            role_diffs.append(diff_item)
            flat_bullets.append(diff_item)
        diff_roles.append({
            "company": role["company"],
            "title": role.get("title", ""),
            "bullets": role_diffs,
        })

    analysis = {
        "jd_keywords": [k for k in ["Python", "FastAPI", "Java", "Spring Boot", "React", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes", "API", "Microservices", "UPI", "Payments", "AI Agents", "LLM", "RAG"] if k.lower() in jd_text.lower()],
        "top_matches": [b["theme"] for b in flat_bullets if b.get("theme")],
    }
    recruiter_review = None

    if chain and flat_bullets:
        import json as _json
        system = (
            "You are an elite Lead Technical Recruiter and Head of Talent Acquisition evaluating an engineering resume against a specific Job Description. "
            "You conduct a master-at-work, brutally honest assessment following 5 strict pillars:\n"
            "1. THE 10-SECOND ATTENTION TEST: What catches your eye immediately? What feels like forgettable filler? What is your raw first impression?\n"
            "2. THE RECRUITER MINDSET BREAKDOWN: Raw competitive assessment. Point out unclear positioning, weak achievements, or missing credibility signals compared to top applicants.\n"
            "3. THE ATS VISIBILITY ENGINE: Missing JD keywords, underrepresented competencies, and exact natural injection hints.\n"
            "4. THE IMPACT STATEMENT REBUILDER: Transform bullets into high-value achievement lines (Action + Scope + Architecture + Measurable Metric). NO FICTION: Keep core facts/metrics 100% true.\n"
            "5. THE MARKET POSITIONING REWRITE: Custom executive summary and role positioning tailored to this company's hiring standards.\n\n"
            "Respond ONLY with valid JSON with this exact schema:\n"
            "{\n"
            '  "attention_test": {"scan_impression": "str", "standout_elements": ["str"], "forgettable_elements": ["str"], "interview_verdict": "str"},\n'
            '  "mindset_breakdown": {"positioning_clarity": "str", "credibility_signals": ["str"], "red_flags": ["str"], "competitive_edge": "str"},\n'
            '  "ats_visibility": {"missing_keywords": [{"term": "str", "category": "str", "injection_hint": "str"}], "underrepresented_skills": ["str"]},\n'
            '  "impact_rebuilder": [{"id": "str", "original": "str", "tailored": "str", "metric_highlight": "str", "rationale": "str"}],\n'
            '  "market_positioning": {"company_alignment": "str", "recommended_headline": "str", "strategic_summary": "str"}\n'
            "}"
        )
        bullet_prompts = [{"id": b["id"], "text": b["original"], "skills": b.get("skills", [])} for b in flat_bullets]
        user_msg = (
            f"JOB DESCRIPTION:\n{jd_text[:3500]}\n\n"
            f"CANDIDATE BULLETS TO AUDIT & REWRITE:\n{_json.dumps(bullet_prompts, indent=2)}"
        )
        try:
            reply_text, _ = chain.complete("capable", system, user_msg)
            m = re.search(r"\{.*\}", reply_text, re.DOTALL)
            if m:
                data = _json.loads(m.group(0))
                recruiter_review = data
                rewrites = {r["id"]: r for r in data.get("impact_rebuilder", []) if "id" in r}
                for b in flat_bullets:
                    if b["id"] in rewrites:
                        rw = rewrites[b["id"]]
                        if rw.get("tailored"):
                            b["tailored"] = rw["tailored"].strip()
                        if rw.get("rationale"):
                            b["rationale"] = rw["rationale"].strip()
                if data.get("market_positioning"):
                    analysis["target_focus"] = data["market_positioning"].get("recommended_headline", "")
        except Exception as e:
            print("tailor recruiter analysis error:", e)

    return {"roles": diff_roles, "skills": skills, "analysis": analysis, "recruiter_review": recruiter_review}


def tailor(bank_path: Path, jd_text: str, out_path: Path,
           master_report: ParseReport | None = None) -> RenderResult:
    bank = load_bank(bank_path)
    chosen = select_bullets(bank, jd_text)
    skills = reorder_skills(bank, jd_text)
    used = render_pdf(bank, chosen, skills, out_path)

    report = analyse_pdf(out_path)
    regressions = report_regression(master_report, report) if master_report else []
    if regressions:                       # §8.4.3: refuse to keep a worse resume
        out_path.unlink(missing_ok=True)
        return RenderResult(None, report, regressions, used)
    return RenderResult(out_path, report, [], used)
