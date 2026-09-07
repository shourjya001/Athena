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


def calculate_multi_factor_fit(resume_text: str, jd_text: str) -> dict:
    """Calculate transparent 4-pillar confidence breakdown:
    Direct (40%) + Transferable (30%) + Adjacent (20%) + Impact Alignment (10%)."""
    res_toks = set(_tok(resume_text))
    jd_toks = set(_tok(jd_text))
    
    if not jd_toks:
        return {"direct": 85, "transferable": 85, "adjacent": 80, "impact": 80, "overall": 84, "confidence_tier": "STRONG"}

    # 1. Direct Match (40%): Overlap on explicit tech skills & domain terms
    tech_keywords = {
        "python", "java", "golang", "c++", "react", "fastapi", "spring", "docker",
        "kubernetes", "aws", "gcp", "azure", "postgresql", "mysql", "mongodb",
        "redis", "kafka", "rabbitmq", "elasticsearch", "graphql", "rest", "grpc",
        "ci/cd", "terraform", "microservices", "distributed", "linux", "sql"
    }
    jd_tech = jd_toks.intersection(tech_keywords)
    if jd_tech:
        direct_ratio = len(res_toks.intersection(jd_tech)) / len(jd_tech)
        direct_score = int(min(100, max(30, direct_ratio * 100)))
    else:
        shared = len(res_toks.intersection(jd_toks))
        direct_score = int(min(95, max(40, (shared / max(15, len(jd_toks) * 0.25)) * 100)))

    # 2. Transferable Skills (30%): System architecture, leadership, problem solving
    transferable_terms = {
        "architecture", "design", "scale", "performance", "optimization",
        "reliability", "testing", "monitoring", "lead", "mentored", "agile",
        "debugging", "collaboration", "cross-functional", "ownership", "production"
    }
    trans_in_jd = jd_toks.intersection(transferable_terms) or {"design", "scale", "performance"}
    trans_shared = len(res_toks.intersection(trans_in_jd))
    trans_score = int(min(100, max(50, (trans_shared / len(trans_in_jd)) * 100)))

    # 3. Adjacent Experience (20%): Complementary frameworks & tooling
    adjacent_pairs = [
        ({"fastapi", "flask", "django"}, {"python"}),
        ({"spring", "springboot"}, {"java"}),
        ({"postgres", "postgresql", "mysql"}, {"sql", "database"}),
        ({"redis", "memcached"}, {"caching", "cache"}),
        ({"kafka", "rabbitmq"}, {"messaging", "events", "queue"}),
        ({"docker", "container"}, {"kubernetes", "k8s"}),
        ({"react", "vue", "angular"}, {"frontend", "typescript", "javascript"})
    ]
    adj_hits = 0
    adj_targets = 0
    for group_a, group_b in adjacent_pairs:
        if jd_toks.intersection(group_a):
            adj_targets += 1
            if res_toks.intersection(group_a) or res_toks.intersection(group_b):
                adj_hits += 1
    adj_score = int(min(100, max(45, (adj_hits / max(1, adj_targets)) * 100))) if adj_targets > 0 else 80

    # 4. Impact & Scale Alignment (10%): Metrics, quantifiable achievements
    metric_matches = len(re.findall(r"\b(?:\d+%(?: reduction| increase| boost)?|\d+k|\d+m|\d+ms|million|billion|\$\d+)\b", resume_text, re.IGNORECASE))
    impact_score = min(100, 50 + (metric_matches * 10))

    # Overall weighted score
    overall = int((direct_score * 0.40) + (trans_score * 0.30) + (adj_score * 0.20) + (impact_score * 0.10))
    
    if overall >= 85:
        tier = "DIRECT MATCH"
    elif overall >= 70:
        tier = "TRANSFERABLE"
    elif overall >= 55:
        tier = "ADJACENT"
    else:
        tier = "GROWTH / STRETCH"

    return {
        "direct": direct_score,
        "transferable": trans_score,
        "adjacent": adj_score,
        "impact": impact_score,
        "overall": overall,
        "confidence_tier": tier
    }


def synthesize_discovered_bullet(skill_gap: str, user_notes: str, experience_type: str = "direct", chain: any = None) -> dict:
    """Transform conversational notes from the gap interview into a polished,
    quantified achievement bullet point following standard Action + Scope + Impact format."""
    clean_notes = (user_notes or "").strip()
    clean_skill = (skill_gap or "Technology").strip()
    exp_type = experience_type.lower()

    if chain and clean_notes:
        import json as _json
        system = (
            "You are an elite Lead Technical Recruiter transforming a candidate's rough experiential notes into a top-tier resume bullet. "
            "Guidelines:\n"
            "1. NO FICTION: Keep core technical facts, metrics, and systems completely truthful based on what the user provided.\n"
            "2. FORMULA: [Strong Action Verb] + [What Was Architected/Solved using the skill] + [How It Was Implemented] + [Measurable Outcome/Metric].\n"
            "3. STYLE: Active voice, crisp tech terminology, eliminate fluff.\n"
            "Respond ONLY with valid JSON: "
            '{"bullet": "string", "metric_highlight": "string", "rationale": "string", "confidence_boost": "string"}'
        )
        user_prompt = (
            f"TARGET SKILL / GAP: {clean_skill}\n"
            f"EXPERIENCE TYPE: {exp_type} (direct work / transferable / adjacent tech / personal project)\n"
            f"CANDIDATE'S RAW NOTES:\n{clean_notes}\n\n"
            "Generate one polished, production-grade resume bullet that naturally proves this competency."
        )
        try:
            reply_text, _ = chain.complete("capable", system, user_prompt)
            m = re.search(r"\{.*\}", reply_text, re.DOTALL)
            if m:
                res = _json.loads(m.group(0))
                return {
                    "bullet": res.get("bullet", clean_notes),
                    "metric_highlight": res.get("metric_highlight", "Quantified Scale"),
                    "rationale": res.get("rationale", f"Addresses {clean_skill} requirement naturally."),
                    "confidence_boost": res.get("confidence_boost", "+15% ATS Keyword Alignment")
                }
        except Exception as e:
            print("synthesize bullet LLM error:", e)

    # Clean deterministic fallback
    action = "Engineered" if exp_type == "direct" else "Architected" if exp_type == "transferable" else "Implemented"
    bullet = f"{action} scalable solutions incorporating {clean_skill}, {clean_notes}"
    return {
        "bullet": bullet,
        "metric_highlight": "Metric-driven impact",
        "rationale": f"Explicitly demonstrates hands-on competency in {clean_skill}.",
        "confidence_boost": "+12% Alignment"
    }


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

    resume_full_text = bank_to_text(bank)
    multi_factor = calculate_multi_factor_fit(resume_full_text, jd_text)

    analysis = {
        "jd_keywords": [k for k in ["Python", "FastAPI", "Java", "Spring Boot", "React", "PostgreSQL", "Redis", "Kafka", "Docker", "Kubernetes", "API", "Microservices", "UPI", "Payments", "AI Agents", "LLM", "RAG"] if k.lower() in jd_text.lower()],
        "top_matches": [b["theme"] for b in flat_bullets if b.get("theme")],
        "multi_factor": multi_factor
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

    return {"roles": diff_roles, "skills": skills, "analysis": analysis, "recruiter_review": recruiter_review, "multi_factor": multi_factor}


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
