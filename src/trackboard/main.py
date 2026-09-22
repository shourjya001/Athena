from __future__ import annotations

import argparse
import os
from datetime import UTC
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import content, db, drill, llm, practice, users
from .settings import get_settings

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
_RUNNING_AGENT: dict[str, any] = {}


def format_ist(val: any) -> str:
    if not val:
        return ""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        s = str(val).strip()
        dt = datetime.fromisoformat(s.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        ist_dt = dt.astimezone(ZoneInfo("Asia/Kolkata"))
        return ist_dt.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return str(val)

templates.env.filters["ist"] = format_ist


def create_app() -> FastAPI:
    app = FastAPI(title="Trackboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def today(request: Request):
        user = users.current_user(request)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        live_jobs_count = db.query_one("SELECT count(*) as c FROM jobs WHERE closed_at IS NULL")
        companies_count = db.query_one("SELECT count(DISTINCT company_name) as c FROM jobs WHERE closed_at IS NULL")
        applied_count = db.query_one("SELECT count(*) as c FROM applications WHERE user_id=?", (user["id"],))
        matches_count = db.query_one("SELECT count(*) as c FROM matches WHERE user_id=? AND dismissed_at IS NULL", (user["id"],))
        agent_runs = db.query("SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT 6")

        return templates.TemplateResponse(
            request,
            "pages/today.html",
            {
                "user": user,
                "answers": answers,
                "health": content.content_health(),
                "patterns": content.list_patterns(user["id"])[:6],
                "live_jobs_count": live_jobs_count["c"] if live_jobs_count else 0,
                "companies_count": companies_count["c"] if companies_count else 0,
                "applied_count": applied_count["c"] if applied_count else 0,
                "matches_count": matches_count["c"] if matches_count else 0,
                "agent_runs": agent_runs,
            },
        )

    @app.get("/practice", response_class=HTMLResponse)
    def practice_page(request: Request):
        user = users.current_user(request)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        return templates.TemplateResponse(
            request,
            "pages/practice.html",
            {
                "user": user,
                "q": practice.build_queue(user["id"]),
                "answers": answers,
            },
        )

    @app.get("/patterns", response_class=HTMLResponse)
    def pattern_index(request: Request):
        user = users.current_user(request)
        pats = content.list_patterns(user["id"])
        families: dict[str, list] = {}
        for p in pats:
            families.setdefault(p["family"], []).append(p)
        return templates.TemplateResponse(
            request, "pages/patterns.html",
            {"user": user, "families": families, "total": len(pats)})

    @app.get("/patterns/{slug}", response_class=HTMLResponse)
    def pattern_detail(request: Request, slug: str):
        try:
            user = users.current_user(request)
            pat = content.get_pattern(slug)
            if not pat:
                return RedirectResponse("/patterns", status_code=303)
            return templates.TemplateResponse(
                request,
                "pages/pattern.html",
                {
                    "user": user,
                    "p": pat,
                    "problems": content.pattern_problems(pat["id"], user["id"]),
                    "resources": content.pattern_resources(pat["id"]),
                },
            )
        except Exception as e:
            import sys
            print(f"Error rendering pattern {slug}: {e}", file=sys.stderr)
            return RedirectResponse("/patterns", status_code=303)

    @app.get("/linkedin", response_class=HTMLResponse)
    def linkedin_page(request: Request):
        user = users.current_user(request)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }

        # Pre-fill linkedin if available
        user_li = answers.get("linkedin", "")
        master_resume = db.query_one("SELECT parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1", (user["id"],))
        parsed = master_resume["parsed_text"] if master_resume and master_resume["parsed_text"] else ""
        if not user_li and parsed:
            import re
            m = re.search(r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+", parsed)
            if m:
                user_li = m.group(0)

        current_hl = answers.get("titles") or (f"{user.get('display_name', 'Software Engineer')} | Distributed Systems & Cloud Architecture")
        lines = [l.strip().lstrip("-•* ") for l in parsed.splitlines() if len(l.strip()) > 25]
        current_exp = "\n".join(lines[:3]) if lines else "Engineered high-scale backend microservices serving millions of requests.\nOptimized database queries and Redis caching, cutting p95 response times by 40%."
        current_about = f"Software engineer specializing in high-throughput distributed systems and backend architecture. Deep hands-on experience in {answers.get('keywords', 'Python, Go, PostgreSQL, Redis, and Cloud Infrastructure')}. Focused on solving scalability and reliability bottlenecks."

        return templates.TemplateResponse(
            request,
            "pages/linkedin.html",
            {
                "user": user,
                "nav": "linkedin",
                "user_linkedin": user_li,
                "current_headline": current_hl,
                "current_about": current_about,
                "current_exp": current_exp,
            },
        )

    @app.post("/a/linkedin/optimize")
    async def optimize_linkedin_endpoint(request: Request):
        from . import linkedin_optimizer
        chain = None
        try:
            from .llm import Chain
            chain = Chain.from_env()
        except Exception:
            chain = None
        try:
            body = await request.json()
        except Exception:
            body = {}
        result = linkedin_optimizer.audit_and_optimize_profile(
            headline=body.get("headline", ""),
            about=body.get("about", ""),
            experiences=body.get("experiences", ""),
            target_audience=body.get("target_audience", "Engineering Leaders & Technical Recruiters"),
            goal=body.get("goal", "job seeker"),
            linkedin_url=body.get("linkedin_url", ""),
            mode=body.get("mode", "standard"),
            chain=chain
        )
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True, "data": result})

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(request: Request, background_tasks: BackgroundTasks):
        user = users.current_user(request)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }

        # Check if user has uploaded a resume
        has_resume = db.query_one(
            "SELECT COUNT(*) n FROM resumes WHERE user_id=? AND is_master=1",
            (user["id"],),
        )["n"] > 0

        # Non-blocking background pass: automatically verify liveness and remove expired jobs
        from . import jobs as jobs_mod
        background_tasks.add_task(jobs_mod.clean_expired_matched_jobs, user["id"], 25)

        items = []
        if has_resume:
            match_count = db.query_one("SELECT COUNT(*) n FROM matches WHERE user_id=?", (user["id"],))["n"]
            if match_count == 0:
                # Auto-initialize matching and scoring for the candidate immediately
                try:
                    from .agents.matcher import run_matcher_for_user
                    run_matcher_for_user(user, force_bm25=False)
                except Exception as e:
                    import sys
                    print(f"Notice on auto-match cold start: {e}", file=sys.stderr)

            # Query matches — strictly exclude jobs already applied to or dismissed, and filter low fits (<40)
            rows = db.query(
                "SELECT m.bm25_score, m.fit_score, m.verdict, m.reasoning, m.gaps_json, m.strengths_json, "
                "j.* , m.id AS match_id FROM matches m JOIN jobs j ON j.id = m.job_id "
                "WHERE m.user_id=? AND m.dismissed_at IS NULL AND j.closed_at IS NULL "
                "AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
                "AND (m.fit_score IS NULL OR m.fit_score >= 40) "
                "ORDER BY m.fit_score IS NULL, m.fit_score DESC, m.bm25_score DESC LIMIT 80",
                (user["id"], user["id"]))
            import json as _json

            from .matcher import BUSINESS_TRACK_EXCLUSIONS, TECH_TRACK_EXCLUSIONS, load_avoid_titles
            user_track = answers.get("track", "tech")
            user_avoids = [a.strip().lower() for a in answers.get("avoid_titles", "").split(",") if a.strip()]
            full_avoids = load_avoid_titles(user_track) + user_avoids
            track_exclusions = TECH_TRACK_EXCLUSIONS if user_track == "tech" else BUSINESS_TRACK_EXCLUSIONS

            for r in rows:
                d = dict(r)
                title_lower = (d.get("title") or "").lower()
                if any(av in title_lower for av in full_avoids) or any(tx in title_lower for tx in track_exclusions):
                    continue
                d["gaps"] = _json.loads(d.get("gaps_json") or "[]")
                d["strengths"] = _json.loads(d.get("strengths_json") or "[]")
                items.append(d)
                if len(items) >= 40:
                    break

        if not items:
            # Fallback: display freshest open jobs filtered strictly by avoid list (excluding Senior, Lead, Manager, SDE-2/3, 3+ YOE)
            avoid_list = [
                "senior", "sr.", "sr ", "sr-", "staff", "principal", "lead", "manager", "director",
                "vp", "head of", "architect", "sde-2", "sde 2", "sde-ii", "sde ii", "sde2",
                "sde-3", "sde 3", "sde-iii", "sde iii", "sde3", "2+", "3+", "4+", "5+", "6+"
            ]
            high_exp_pats = [
                r"(?:at least|minimum|min|have|\+)\s*(?:3|4|5|6|7|8|9|10)\s*(?:\+)?\s*(?:years?|yrs?|yoe)",
                r"(?:3|4|5|6|7|8|9|10)\s*(?:\+)\s*(?:years?|yrs?|yoe)",
                r"(?:3|4|5|6|7|8|9|10)\s*(?:-|to)\s*(?:\d+)\s*(?:years?|yrs?|yoe)",
                r"(?:3|4|5|6|7|8|9|10)\s*years?\s*of\s*(?:relevant\s*)?(?:hands-on\s*)?experience",
            ]
            rows = db.query(
                "SELECT 0.0 as bm25_score, NULL as fit_score, NULL as verdict, NULL as reasoning, '[]' as gaps_json, '[]' as strengths_json, "
                "j.*, 0 as match_id FROM jobs j WHERE j.closed_at IS NULL "
                "AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
                "ORDER BY j.first_seen_at DESC LIMIT 150",
                (user["id"],)
            )
            import re as _re
            for r in rows:
                d = dict(r)
                t = (d.get("title") or "").lower()
                desc = (d.get("description_md") or "").lower()
                if any(av in t for av in avoid_list):
                    continue
                if any(_re.search(pat, f"{t}\n{desc}") for pat in high_exp_pats):
                    continue
                d["gaps"] = []
                d["strengths"] = []
                items.append(d)
                if len(items) >= 40:
                    break

        # Compute transparent multi-factor breakdown and high-leverage skills across top items
        from .tailor import calculate_multi_factor_fit
        master_resume_row = db.query_one("SELECT parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1", (user["id"],))
        master_text = master_resume_row["parsed_text"] if master_resume_row and master_resume_row["parsed_text"] else ""
        
        skill_occurrences: dict[str, int] = {}
        tracked_core_skills = [
            ("Microservices & Distributed Systems", ["microservices", "distributed", "grpc"]),
            ("Redis & In-Memory Caching", ["redis", "cache", "memcached"]),
            ("Docker & Containerization", ["docker", "container", "kubernetes"]),
            ("Kafka & Event Streaming", ["kafka", "rabbitmq", "event-driven", "streaming"]),
            ("PostgreSQL & Relational Architecture", ["postgresql", "postgres", "sql", "mysql"]),
            ("System Design & High Concurrency", ["system design", "high concurrency", "tps", "scale", "latency"]),
            ("FastAPI & Async Python", ["fastapi", "asyncio", "python"]),
            ("API Security & Cloud Infra", ["jwt", "oauth", "security", "aws", "gcp"]),
        ]

        for item in items:
            jd_t = f"{item.get('title', '')}\n{item.get('description_md', '')}".lower()
            if master_text:
                item["multi_factor"] = calculate_multi_factor_fit(master_text, jd_t)
            else:
                score = item.get("fit_score") or 80
                item["multi_factor"] = {
                    "direct": score, "transferable": min(100, score + 5),
                    "adjacent": min(100, score + 2), "impact": max(50, score - 5),
                    "overall": score, "confidence_tier": "STRONG" if score >= 80 else "TRANSFERABLE"
                }
            for skill_name, skill_aliases in tracked_core_skills:
                if any(al in jd_t for al in skill_aliases):
                    skill_occurrences[skill_name] = skill_occurrences.get(skill_name, 0) + 1

        top_jobs_count = max(1, min(len(items), 25))
        high_leverage_skills = [
            {
                "name": name,
                "count": count,
                "pct": int((count / top_jobs_count) * 100)
            }
            for name, count in sorted(skill_occurrences.items(), key=lambda x: x[1], reverse=True)[:4]
            if count >= 2
        ]

        total_open = db.query_one("SELECT COUNT(*) n FROM jobs WHERE closed_at IS NULL")["n"]
        applied = request.query_params.get("applied") == "1"
        matched = request.query_params.get("matched") == "1"

        proc = _RUNNING_AGENT.get("proc")
        agent_running = proc is not None and proc.poll() is None
        agent_name = _RUNNING_AGENT.get("name") if agent_running else None
        agent_started = request.query_params.get("agent_started")
        agent_stopped = request.query_params.get("agent_stopped") == "1"
        agent_busy = request.query_params.get("agent_busy") == "1"
        digest_sent = request.query_params.get("digest_sent") == "1"
        closed_notice = request.query_params.get("closed_notice") == "1"
        expired_company = request.query_params.get("expired_company") or "Company"

        from datetime import datetime
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")

        return templates.TemplateResponse(
            request, "pages/jobs.html",
            {
                "user": user, "items": items, "total_open": total_open,
                "matched_count": len(items), "answers": answers,
                "applied": applied, "matched": matched,
                "has_resume": has_resume,
                "today_str": today_str,
                "agent_running": agent_running,
                "agent_name": agent_name, "agent_started": agent_started,
                "agent_stopped": agent_stopped, "agent_busy": agent_busy,
                "digest_sent": digest_sent,
                "closed_notice": closed_notice,
                "expired_company": expired_company,
                "high_leverage_skills": high_leverage_skills,
            })

    @app.post("/a/agent/run")
    def run_agent(agent: str = Form("matcher")):
        import subprocess
        import sys
        if agent == "matcher":
            # Direct in-process run for reliability
            user = users.current_user()
            from .agents.matcher import run_matcher_for_user
            run_matcher_for_user(user, force_bm25=False)
            return RedirectResponse("/jobs?agent_started=matcher", status_code=303)

        proc = _RUNNING_AGENT.get("proc")
        if proc is not None and proc.poll() is None:
            return RedirectResponse("/jobs?agent_busy=1", status_code=303)

        p = subprocess.Popen([sys.executable, "-m", f"trackboard.agents.{agent}"])
        _RUNNING_AGENT["proc"] = p
        _RUNNING_AGENT["name"] = agent
        return RedirectResponse(f"/jobs?agent_started={agent}", status_code=303)

    @app.post("/a/agent/stop")
    def stop_agent():
        proc = _RUNNING_AGENT.get("proc")
        if proc is not None and proc.poll() is None:
            proc.terminate()
            _RUNNING_AGENT.clear()
            return RedirectResponse("/jobs?agent_stopped=1", status_code=303)
        return RedirectResponse("/jobs", status_code=303)

    @app.get("/jobs/{job_id}/tailor", response_class=HTMLResponse)
    def tailor_page(request: Request, job_id: int):
        try:
            user = users.current_user(request)
            if not user.get("is_authenticated"):
                return RedirectResponse(f"/login?error=Please+sign+in+to+generate+a+tailored+resume&next=/jobs/{job_id}/tailor", status_code=303)
            job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
            if not job:
                return RedirectResponse("/jobs", status_code=303)
            job = dict(job)

            import yaml

            from . import tailor
            
            # Locate resume.yaml in project root or current working dir
            candidate_paths = [
                BASE.parents[1] / "config" / "resume.yaml",
                Path("config/resume.yaml"),
                BASE.parent / "config" / "resume.yaml",
            ]
            bank = {}
            for cp in candidate_paths:
                if cp.exists():
                    try:
                        bank = yaml.safe_load(cp.read_text()) or {}
                        if bank.get("roles"):
                            break
                    except Exception:
                        pass

            # If user has uploaded a custom resume, construct user bank
            master_resume = db.query_one(
                "SELECT * FROM resumes WHERE user_id=? ORDER BY is_master DESC, id DESC LIMIT 1",
                (user["id"],),
            )
            if master_resume and master_resume["parsed_text"] and user.get("email") != "shourjya001@gmail.com":
                lines = [l.strip().lstrip("-•* ") for l in master_resume["parsed_text"].splitlines() if len(l.strip()) > 15]
                bullets = [
                    {"id": f"b{i+1}", "text": line, "skills": [], "theme": "Core Responsibility"}
                    for i, line in enumerate(lines[:12])
                ]
                bank = {
                    "name": user.get("display_name") or "Candidate",
                    "roles": [{"company": "Professional Experience", "title": user.get("answers", {}).get("titles", "Specialist"), "bullets": bullets}],
                    "skills": {"core": [k.strip() for k in user.get("answers", {}).get("keywords", "").split(",") if k.strip()]}
                }

            if not bank.get("roles"):
                # Safe default bank if none exists
                bank = {
                    "name": user.get("display_name") or "Candidate",
                    "roles": [{
                        "company": "Current Experience",
                        "title": user.get("answers", {}).get("titles", "Specialist"),
                        "bullets": [{"id": "b1", "text": "Delivered high-impact solutions aligning with organizational goals and operational standards.", "skills": [], "theme": "General"}]
                    }],
                    "skills": {"core": ["Problem Solving", "Execution", "Communication"]}
                }

            tailored_resume = db.query_one(
                "SELECT * FROM resumes WHERE user_id=? AND label LIKE ? ORDER BY id DESC LIMIT 1",
                (user["id"], f"%Job {job_id}%"),
            )

            chain = None
            try:
                chain = llm.Chain()
            except Exception:
                pass

            data = tailor.suggest_tailoring(bank, job.get("description_md") or "", chain=chain)
            saved = request.query_params.get("saved") == "1"
            applied = request.query_params.get("applied") == "1"

            return templates.TemplateResponse(
                request,
                "pages/tailor.html",
                {
                    "user": user,
                    "job": job,
                    "data": data,
                    "bank": bank,
                    "tailored_resume": tailored_resume,
                    "saved": saved,
                    "applied": applied,
                },
            )
        except Exception as e:
            import logging
            logging.getLogger("trackboard.tailor").error("Tailor page error: %s", e)
            return RedirectResponse("/jobs", status_code=303)

    @app.post("/jobs/{job_id}/tailor/approve")
    async def approve_tailor(request: Request, job_id: int):
        user = users.current_user(request)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            return RedirectResponse("/jobs", status_code=303)
        job = dict(job)

        import yaml

        from . import tailor
        bank_path = Path("config/resume.yaml")
        bank = yaml.safe_load(bank_path.read_text()) if bank_path.exists() else {}

        form_data = await request.form()
        chosen_bullets: dict[str, list[dict]] = {}
        for role in bank.get("roles", []):
            role_comp = role["company"]
            role_list = []
            for b in role.get("bullets", []):
                bid = b["id"]
                val = form_data.get(f"bullet_{bid}")
                if val:
                    b_copy = dict(b)
                    b_copy["text"] = str(val).strip()
                    role_list.append(b_copy)
            if role_list:
                chosen_bullets[role_comp] = role_list

        custom_skills_raw = form_data.get("custom_skills")
        if custom_skills_raw:
            skills = [s.strip() for s in str(custom_skills_raw).split(",") if s.strip()]
        else:
            skills = tailor.reorder_skills(bank, job.get("description_md") or "")
        out_dir = Path("/tmp/resumes") if os.getenv("VERCEL") else (BASE / "static" / "resumes")
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_name = f"tailored_{user['id']}_{job_id}.pdf"
        out_pdf = out_dir / pdf_name

        tailor.render_pdf(
            bank,
            chosen_bullets or tailor.select_bullets(bank, job.get("description_md") or ""),
            skills,
            out_pdf,
        )

        label = f"Tailored: {job['title']} @ {job['company_name']} (Job {job_id})"
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) "
                "VALUES (?, ?, ?, ?, 0, datetime('now'))",
                (user["id"], label, f"/static/resumes/{pdf_name}", str(chosen_bullets)),
            )
            res_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

            conn.execute(
                "INSERT INTO applications (user_id, job_id, resume_id, status, status_source, last_event_at) "
                "VALUES (?, ?, ?, 'prepared', 'user', datetime('now')) "
                "ON CONFLICT(user_id, job_id) DO UPDATE SET "
                "resume_id=excluded.resume_id, last_event_at=datetime('now')",
                (user["id"], job_id, res_id),
            )
        return RedirectResponse(f"/jobs/{job_id}/tailor?saved=1", status_code=303)

    @app.post("/a/jobs/{job_id}/discover-bullet")
    async def discover_bullet(job_id: int, request: Request):
        """Interactive experience discovery: turns raw user context into a tailored, quantified bullet."""
        _ = users.current_user(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        skill_gap = body.get("skill_gap", "Core Technology")
        experience_type = body.get("experience_type", "direct")
        user_notes = body.get("user_notes", "")

        from . import llm, tailor
        chain = None
        try:
            chain = llm.Chain()
        except Exception:
            pass

        result = tailor.synthesize_discovered_bullet(skill_gap, user_notes, experience_type, chain)
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True, "data": result})

    @app.post("/a/jobs/{job_id}/save-bullet-to-bank")
    async def save_bullet_to_bank(job_id: int, request: Request):
        """Append approved tailored bullet into the candidate's permanent master resume/library."""
        user = users.current_user(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        bullet = (body.get("bullet") or "").strip()
        skill = (body.get("skill") or "Technical Skills").strip()
        if not bullet:
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": False, "error": "Bullet text is required"}, status_code=400)

        # Append to user's master resume in SQLite
        master_resume = db.query_one(
            "SELECT id, parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1",
            (user["id"],),
        )
        new_entry = f"\n- {bullet} (Skills: {skill})"
        if master_resume:
            existing = master_resume["parsed_text"] or ""
            if "DISCOVERED EXPERIENCES & BULLETS:" not in existing:
                updated_text = existing + "\n\nDISCOVERED EXPERIENCES & BULLETS:" + new_entry
            else:
                updated_text = existing + new_entry
            db.execute("UPDATE resumes SET parsed_text=? WHERE id=?", (updated_text, master_resume["id"]))
        else:
            db.execute(
                "INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) "
                "VALUES (?, 'master_bullet_bank', 'internal/bank', ?, 1, datetime('now'))",
                (user["id"], f"DISCOVERED EXPERIENCES & BULLETS:{new_entry}"),
            )

        from fastapi.responses import JSONResponse
        return JSONResponse({
            "ok": True,
            "message": f"Successfully saved bullet to your Master Library for {skill}!"
        })

    @app.post("/a/jobs/{job_id}/linkedin-seo")
    def job_linkedin_seo_endpoint(request: Request, job_id: int):
        from . import linkedin_optimizer
        chain = None
        try:
            from .llm import Chain
            chain = Chain.from_env()
        except Exception:
            chain = None

        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": False, "error": "Job not found"}, status_code=404)
        job = dict(job)

        user = users.current_user(request)
        master_resume = db.query_one("SELECT parsed_text FROM resumes WHERE user_id=? AND is_master=1 LIMIT 1", (user["id"],))
        master_text = master_resume["parsed_text"] if master_resume and master_resume["parsed_text"] else ""

        seo_res = linkedin_optimizer.generate_job_targeted_linkedin_seo(
            job_title=job.get("title", "Software Engineer"),
            company=job.get("company_name", "Technology Company"),
            jd_text=job.get("description_md", ""),
            resume_text=master_text,
            chain=chain
        )
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True, "data": seo_res})

    @app.post("/a/jobs/{job_id}/apply")
    def launch_applier(request: Request, job_id: int):
        user = users.current_user(request)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        job = dict(job) if job else None
        
        # 1. Update application status
        db.execute(
            "INSERT INTO applications (user_id, job_id, status, status_source, applied_at, last_event_at) "
            "VALUES (?, ?, 'submitted', 'user', datetime('now'), datetime('now')) "
            "ON CONFLICT(user_id, job_id) DO UPDATE SET "
            "status='submitted', status_source='user', applied_at=coalesce(applications.applied_at, datetime('now')), last_event_at=datetime('now')",
            (user["id"], job_id)
        )
        app_row = db.query_one("SELECT id FROM applications WHERE user_id=? AND job_id=?", (user["id"], job_id))
        if app_row:
            db.execute(
                "INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
                "VALUES (?, 'submitted', datetime('now'), 'applier', 'Auto-fill application initiated', datetime('now'))",
                (app_row["id"],)
            )

        # 2. Auto-dismiss from active matches queue so it moves to /pipeline
        db.execute(
            "UPDATE matches SET dismissed_at=datetime('now') WHERE user_id=? AND job_id=?",
            (user["id"], job_id)
        )

        # 3. If running locally on desktop, spawn Playwright headed browser
        if not os.getenv("VERCEL"):
            try:
                import subprocess
                import sys
                subprocess.Popen([
                    sys.executable, "-m", "trackboard.agents.applier",
                    str(job_id), "--user", user["email"]
                ])
            except Exception as e:
                import sys
                print(f"Notice on applier process spawn: {e}", file=sys.stderr)

        # 4. Redirect directly to official apply URL or to pipeline
        if job and job.get("apply_url") and job["apply_url"].startswith("http"):
            return RedirectResponse(job["apply_url"], status_code=303)
        return RedirectResponse("/pipeline", status_code=303)

    @app.get("/a/jobs/{job_id}/go")
    def apply_go_route(request: Request, job_id: int):
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            return RedirectResponse("/jobs?error=Job+not+found", status_code=303)
        job = dict(job)
        apply_url = job.get("apply_url")
        if not apply_url or not apply_url.startswith("http"):
            return RedirectResponse("/jobs?error=Job+not+found", status_code=303)

        try:
            from . import jobs as jobs_mod
            if jobs_mod.is_job_url_closed(apply_url):
                try:
                    db.execute("UPDATE jobs SET closed_at=datetime('now') WHERE id=?", (job_id,))
                except Exception:
                    pass
                company = job.get("company_name") or "the company"
                return RedirectResponse(f"/jobs?closed_notice=1&expired_company={company}", status_code=303)
        except Exception as e:
            print("Notice on job liveness verification:", e)

        return RedirectResponse(apply_url, status_code=303)

    @app.post("/a/jobs/{job_id}/mark-applied")
    def mark_applied_route(request: Request, job_id: int):
        user = users.current_user(request)
        db.execute(
            "INSERT INTO applications (user_id, job_id, status, status_source, applied_at, last_event_at) "
            "VALUES (?, ?, 'submitted', 'user', datetime('now'), datetime('now')) "
            "ON CONFLICT(user_id, job_id) DO UPDATE SET "
            "status='submitted', status_source='user', applied_at=coalesce(applications.applied_at, datetime('now')), last_event_at=datetime('now')",
            (user["id"], job_id)
        )
        app_row = db.query_one("SELECT id FROM applications WHERE user_id=? AND job_id=?", (user["id"], job_id))
        if app_row:
            db.execute(
                "INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
                "VALUES (?, 'submitted', datetime('now'), 'user', 'Marked as applied manually', datetime('now'))",
                (app_row["id"],)
            )
        # Auto-dismiss from /jobs queue so it moves exclusively to /pipeline
        db.execute(
            "UPDATE matches SET dismissed_at=datetime('now') WHERE user_id=? AND job_id=?",
            (user["id"], job_id)
        )
        return RedirectResponse("/pipeline", status_code=303)

    @app.post("/a/applications/{app_id}/status")
    async def update_application_status_route(request: Request, app_id: int):
        user = users.current_user(request)
        form = await request.form()
        new_status = form.get("status")
        valid = {'prepared','submitted','acknowledged','screening','assessment','interview','offer','rejected','withdrawn','ghosted'}
        if new_status in valid:
            db.execute(
                "UPDATE applications SET status=?, status_source='user', last_event_at=datetime('now') "
                "WHERE id=? AND user_id=?", (new_status, app_id, user["id"])
            )
            db.execute(
                "INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
                "VALUES (?, ?, datetime('now'), 'user', 'Status changed manually in pipeline', datetime('now'))",
                (app_id, new_status)
            )
        return RedirectResponse("/pipeline", status_code=303)

    @app.post("/a/match/{match_id}/dismiss")
    def dismiss_match(request: Request, match_id: int):
        user = users.current_user(request)
        db.execute("UPDATE matches SET dismissed_at=datetime('now') "
                   "WHERE id=? AND user_id=?", (match_id, user["id"]))
        return RedirectResponse("/jobs", status_code=303)

    @app.post("/a/digest/send")
    def send_digest_route(request: Request):
        user = users.current_user(request)
        from .agents.digest import send_digest_email
        send_digest_email(user["id"])
        return RedirectResponse("/jobs?digest_sent=1", status_code=303)

    @app.get("/pipeline", response_class=HTMLResponse)
    def pipeline_page(request: Request):
        user = users.current_user(request)
        if not user.get("is_authenticated"):
            return RedirectResponse("/login?error=Please+sign+in+to+view+your+private+application+pipeline&next=/pipeline", status_code=303)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        rows = db.query(
            "SELECT a.*, j.company_name, j.title FROM applications a "
            "JOIN jobs j ON j.id = a.job_id WHERE a.user_id=? "
            "ORDER BY a.last_event_at DESC NULLS LAST", (user["id"],))
        cols: dict[str, list] = {}
        for r in rows:
            cols.setdefault(r["status"], []).append(dict(r))
        return templates.TemplateResponse(
            request, "pages/pipeline.html", {"user": user, "cols": cols, "answers": answers})


    @app.post("/a/attempt")
    def record_attempt(
        request: Request,
        problem_id: int = Form(...),
        outcome: str = Form(...),
        confidence: int = Form(3),
    ):
        user = users.current_user(request)
        practice.record_attempt(user["id"], problem_id, outcome, confidence)
        return RedirectResponse("/practice", status_code=303)

    @app.get("/drill", response_class=HTMLResponse)
    def drill_page(request: Request):
        user = users.current_user(request)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        return templates.TemplateResponse(
            request, "pages/drill.html",
            {"user": user, "item": drill.next_drill(user["id"]),
             "choices": drill.choices(), "result": None,
             "general_resources": content.general_resources(), "answers": answers},
        )

    @app.post("/drill", response_class=HTMLResponse)
    def drill_answer(
        request: Request,
        problem_id: int = Form(...),
        chosen_pattern_id: int = Form(...),
        seconds: int = Form(0),
    ):
        user = users.current_user(request)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        result = drill.answer(user["id"], problem_id, chosen_pattern_id, seconds or None)
        return templates.TemplateResponse(
            request, "pages/drill.html",
            {"user": user, "item": drill.next_drill(user["id"]),
             "choices": drill.choices(), "result": result,
             "general_resources": content.general_resources(), "answers": answers},
        )

    @app.get("/system", response_class=HTMLResponse)
    def system(request: Request):
        user = users.current_user(request)
        if not user.get("is_authenticated") or user.get("email") not in ["shourjya001@gmail.com", "you@example.com"]:
            return RedirectResponse("/login?error=System+telemetry+is+restricted+to+system+architects", status_code=303)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        runs = db.query("SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT 50")
        registered_users = db.query("""
            SELECT u.*,
                   (SELECT COUNT(*) FROM resumes r WHERE r.user_id = u.id) as resume_count,
                   (SELECT COUNT(*) FROM applications a WHERE a.user_id = u.id) as app_count,
                   (SELECT COUNT(*) FROM matches m WHERE m.user_id = u.id) as match_count
            FROM users u
            ORDER BY u.last_seen_at DESC
        """)
        return templates.TemplateResponse(
            request,
            "pages/system.html",
            {
                "user": user,
                "answers": answers,
                "runs": [dict(r) for r in runs],
                "registered_users": [dict(u) for u in registered_users],
                "health": content.content_health(),
                "db_path": str(get_settings().db_path),
                "db_kb": (
                    get_settings().db_path.stat().st_size // 1024
                    if get_settings().db_path.exists()
                    else 0
                ),
            },
        )

    @app.post("/system/users/{uid}/delete")
    def admin_delete_user(request: Request, uid: int):
        user = users.current_user(request)
        if not user.get("is_authenticated") or user.get("email") not in ["shourjya001@gmail.com", "you@example.com"]:
            return RedirectResponse("/login?error=Unauthorized", status_code=303)
        if uid == user["id"]:
            return RedirectResponse("/system?error=Cannot+delete+your+own+master+admin+account", status_code=303)
        
        # Complete cascade deletion across all candidate tables
        db.execute("DELETE FROM application_events WHERE application_id IN (SELECT id FROM applications WHERE user_id = ?)", (uid,))
        db.execute("DELETE FROM applications WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM matches WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM resumes WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM profile_answers WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM reviews WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM attempts WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM drill_attempts WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM pattern_reviews WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        return RedirectResponse("/system?notice=Candidate+account+and+data+permanently+erased", status_code=303)

    @app.post("/profile/delete")
    def self_delete_profile(request: Request):
        user = users.current_user(request)
        if not user.get("is_authenticated"):
            return RedirectResponse("/login", status_code=303)
        uid = user["id"]
        db.execute("DELETE FROM application_events WHERE application_id IN (SELECT id FROM applications WHERE user_id = ?)", (uid,))
        db.execute("DELETE FROM applications WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM matches WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM resumes WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM profile_answers WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM reviews WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM attempts WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM drill_attempts WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM pattern_reviews WHERE user_id = ?", (uid,))
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        
        resp = RedirectResponse("/login?notice=Your+candidate+profile+and+data+have+been+completely+wiped.", status_code=303)
        resp.delete_cookie("trackboard_user")
        return resp

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots_txt():
        return (
            "User-agent: *\n"
            "Allow: /\n"
            "Allow: /jobs\n"
            "Allow: /patterns\n"
            "Allow: /patterns/*\n"
            "Allow: /linkedin\n"
            "Allow: /login\n"
            "Disallow: /profile\n"
            "Disallow: /pipeline\n"
            "Disallow: /system\n"
            "Disallow: /auth/\n\n"
            "Sitemap: https://athena-phi-one.vercel.app/sitemap.xml\n"
        )

    @app.get("/sitemap.xml")
    def sitemap_xml():
        pats = db.query("SELECT slug FROM patterns")
        urls = [
            "https://athena-phi-one.vercel.app/",
            "https://athena-phi-one.vercel.app/jobs",
            "https://athena-phi-one.vercel.app/patterns",
            "https://athena-phi-one.vercel.app/linkedin",
            "https://athena-phi-one.vercel.app/login",
        ]
        for p in pats:
            urls.append(f"https://athena-phi-one.vercel.app/patterns/{p['slug']}")
        
        xml_items = "\n".join(f"  <url><loc>{u}</loc><changefreq>daily</changefreq><priority>0.8</priority></url>" for u in urls)
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{xml_items}
</urlset>"""
        return Response(content=content, media_type="application/xml")

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, saved: int = 0, resume_saved: int = 0, matched: int = 0, error: str | None = None):
        user = users.current_user(request)
        if not user.get("is_authenticated"):
            return RedirectResponse("/login?error=Please+sign+in+to+access+your+candidate+profile&next=/profile", status_code=303)
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        master_resume = db.query_one(
            "SELECT * FROM resumes WHERE user_id=? ORDER BY is_master DESC, id DESC LIMIT 1",
            (user["id"],)
        )
        resume_words = len((master_resume["parsed_text"] or "").split()) if master_resume else 0
        total_jobs = db.query_one("SELECT COUNT(*) as c FROM jobs WHERE closed_at IS NULL")["c"]
        return templates.TemplateResponse(
            request,
            "pages/profile.html",
            {
                "user": user,
                "answers": answers,
                "master_resume": dict(master_resume) if master_resume else None,
                "resume_words": resume_words,
                "total_jobs": total_jobs,
                "saved": bool(saved),
                "resume_saved": bool(resume_saved),
                "matched": bool(matched),
                "error": error,
            },
        )

    @app.post("/profile/targets")
    def save_targets(
        request: Request,
        display_name: str = Form(""),
        titles: str = Form(""),
        avoid_titles: str = Form(""),
        keywords: str = Form(""),
        locations: str = Form(""),
        min_ctc: str = Form(""),
        experience_years: str = Form(""),
        leetcode_user: str = Form(""),
        track: str = Form("tech"),
    ):
        user = users.current_user(request)
        if not user.get("is_authenticated"):
            return RedirectResponse("/login?error=Please+sign+in+to+save+profile+settings", status_code=303)
        uid = user["id"]
        if display_name or leetcode_user:
            db.execute(
                "UPDATE users SET display_name=coalesce(nullif(?, ''), display_name), "
                "leetcode_user=coalesce(nullif(?, ''), leetcode_user) WHERE id=?",
                (display_name.strip() or None, leetcode_user.strip() or None, uid),
            )
        fields = {
            "titles": titles.strip(),
            "avoid_titles": avoid_titles.strip(),
            "keywords": keywords.strip(),
            "locations": locations.strip(),
            "min_ctc": min_ctc.strip(),
            "experience_years": experience_years.strip(),
            "track": track.strip() or "tech",
        }
        with db.transaction() as conn:
            for k, v in fields.items():
                conn.execute(
                    "INSERT INTO profile_answers (user_id, key, value) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value",
                    (uid, k, v),
                )
        return RedirectResponse("/profile?saved=1", status_code=303)

    @app.post("/profile/resume")
    async def upload_resume(
        request: Request,
        resume_file: UploadFile = File(None),
        resume_text: str = Form(""),
    ):
        user = users.current_user(request)
        if not user.get("is_authenticated"):
            return RedirectResponse("/login?error=Please+sign+in+to+upload+a+resume", status_code=303)
        uid = user["id"]
        extracted_text = (resume_text or "").strip()
        label = "Master Resume"

        try:
            if resume_file and getattr(resume_file, "filename", None):
                fname = resume_file.filename.strip()
                if fname:
                    label = fname
                    content_bytes = await resume_file.read()
                    if content_bytes:
                        if fname.lower().endswith(".pdf"):
                            try:
                                import io

                                from pdfminer.high_level import extract_text as pdf_extract
                                pdf_txt = pdf_extract(io.BytesIO(content_bytes)).strip()
                                if pdf_txt:
                                    extracted_text = pdf_txt
                            except Exception as pdf_err:
                                extracted_text = f"Notice: PDF extraction note: {pdf_err}\n\n" + (extracted_text or "")

                            # Extract hyperlinks (LinkedIn, GitHub, email) from PDF annotations
                            try:
                                import io

                                from pdfminer.pdfdocument import PDFDocument
                                from pdfminer.pdfpage import PDFPage
                                from pdfminer.pdfparser import PDFParser
                                from pdfminer.psparser import PSLiteral

                                hyperlinks: list[str] = []
                                parser = PDFParser(io.BytesIO(content_bytes))
                                doc = PDFDocument(parser)
                                for page in PDFPage.create_pages(doc):
                                    if page.annots:
                                        annot_refs = page.annots
                                        if hasattr(annot_refs, '__iter__'):
                                            for annot_ref in annot_refs:
                                                try:
                                                    annot_obj = annot_ref.resolve() if hasattr(annot_ref, 'resolve') else annot_ref
                                                    if isinstance(annot_obj, dict):
                                                        a_dict = annot_obj.get('A') or {}
                                                        if hasattr(a_dict, 'resolve'):
                                                            a_dict = a_dict.resolve()
                                                        uri = a_dict.get('URI') if isinstance(a_dict, dict) else None
                                                        if uri:
                                                            if isinstance(uri, bytes):
                                                                uri = uri.decode('utf-8', errors='ignore')
                                                            elif isinstance(uri, PSLiteral):
                                                                uri = uri.name if hasattr(uri, 'name') else str(uri)
                                                            if uri and uri.startswith('http'):
                                                                hyperlinks.append(uri)
                                                except Exception:
                                                    pass

                                if hyperlinks:
                                    unique_links = list(dict.fromkeys(hyperlinks))
                                    links_section = "\n\nEXTRACTED LINKS:\n" + "\n".join(f"- {lnk}" for lnk in unique_links)
                                    extracted_text += links_section
                            except Exception:
                                pass
                        else:
                            try:
                                extracted_text = content_bytes.decode("utf-8", errors="ignore").strip()
                            except Exception:
                                pass

            if not extracted_text:
                return RedirectResponse("/profile?error=Please+provide+resume+text+or+upload+a+valid+file.", status_code=303)

            with db.transaction() as conn:
                conn.execute("UPDATE resumes SET is_master=0 WHERE user_id=?", (uid,))
                conn.execute(
                    "INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) "
                    "VALUES (?, ?, ?, ?, 1, datetime('now'))",
                    (uid, label, f"upload/{label}", extracted_text),
                )

            # Auto-run matcher so matches are immediately generated upon resume submission
            try:
                from .agents.matcher import run_matcher_for_user
                user_obj = users.current_user(request)
                run_matcher_for_user(user_obj, force_bm25=False)
            except Exception as e:
                import sys
                print(f"Notice on auto-match after resume upload: {e}", file=sys.stderr)

            return RedirectResponse("/jobs?matched=1", status_code=303)
        except Exception as e:
            import urllib.parse
            err_msg = urllib.parse.quote_plus(f"Upload notice: {e}")
            return RedirectResponse(f"/profile?error={err_msg}", status_code=303)

    @app.api_route("/a/matcher/run", methods=["GET", "POST"])
    def run_matcher_on_demand(request: Request, background_tasks: BackgroundTasks):
        user = users.current_user(request)
        from .agents.matcher import run_matcher_for_user
        # Instant BM25 match
        run_matcher_for_user(user, force_bm25=True)
        # Background score up to 6 batches (30 jobs) with multi-provider LLM cascade
        background_tasks.add_task(run_matcher_for_user, user, False, False, 6)
        return RedirectResponse("/jobs?matched=1", status_code=303)

    @app.api_route("/api/cron/sync-and-match", methods=["GET", "POST"])
    @app.api_route("/api/cron/daily", methods=["GET", "POST"])
    def cron_sync_and_match(request: Request):
        """Vercel cron endpoint for automated syncing, matching & digest dispatch."""
        import os
        cron_secret = os.getenv("CRON_SECRET", "")
        auth_header = request.headers.get("authorization", "")
        if cron_secret and auth_header != f"Bearer {cron_secret}":
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        from . import email
        from .agents.matcher import run_matcher_for_user
        results = []
        all_users = db.query("SELECT * FROM users ORDER BY id")
        do_match = request.query_params.get("match", "1") != "0"

        for u in all_users:
            u = dict(u)
            user_res = {"user": u["email"]}

            if do_match:
                try:
                    # Score up to 4 batches (20 net-new jobs) per user during nightly cron
                    m_res = run_matcher_for_user(u, force_bm25=False, max_batches=4)
                    user_res["matched"] = m_res
                except Exception as e:
                    user_res["matcher_error"] = str(e)[:200]

            # Auto-dispatch daily HTML digest to registered email with consolidated fresh & top-fit jobs
            try:
                from .agents.digest import get_consolidated_digest_matches
                top_matches = get_consolidated_digest_matches(u["id"], total_limit=25)

                if top_matches:
                    digest_payload = {
                        "top_matches": top_matches,
                        "pipeline_moves": [],
                        "problems_practiced": 0,
                        "source_failures": []
                    }
                    html = email.render_digest_html(digest_payload, u["email"])
                    sent = email.send_email(
                        to_email=u["email"],
                        subject=f"⚡ Trackboard Digest: {len(top_matches)} Fresh Job Recommendations for {u.get('display_name') or 'You'}",
                        html_body=html
                    )
                    if sent:
                        now_iso = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
                        for m in top_matches:
                            if "job_id" in m:
                                db.execute("UPDATE matches SET digest_sent_at=? WHERE user_id=? AND job_id=?", (now_iso, u["id"], m["job_id"]))
                    user_res["digest_dispatched"] = sent
                    user_res["jobs_sent"] = len(top_matches)
                else:
                    user_res["digest_dispatched"] = False
                    user_res["notice"] = "No open matched jobs found"
            except Exception as e:
                user_res["digest_error"] = str(e)[:200]

            results.append(user_res)

        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True, "users_processed": len(results), "results": results})

    @app.post("/a/digest/send-test")
    def send_test_digest_route(request: Request):
        user = users.current_user(request)
        from . import email
        from .agents.digest import get_consolidated_digest_matches
        top_matches = get_consolidated_digest_matches(user["id"], total_limit=25)
        digest_payload = {
            "top_matches": top_matches,
            "pipeline_moves": [],
            "problems_practiced": 0,
            "source_failures": []
        }
        html = email.render_digest_html(digest_payload, user["email"])
        sent = email.send_email(
            to_email=user["email"],
            subject=f"⚡ Trackboard Digest: {len(top_matches)} Verified Job Recommendations for {user.get('display_name') or 'You'}",
            html_body=html
        )
        return RedirectResponse(f"/jobs?digest_sent={'1' if sent else 'error'}", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str | None = None, notice: str | None = None, next: str = "/"):
        s = get_settings()
        user = users.current_user(request)
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "user": user,
                "allowlist": s.allowlist,
                "error": error,
                "notice": notice,
                "next": next if next and next.startswith("/") else "/",
                "google_configured": bool(s.google_client_id),
            },
        )

    @app.get("/auth/google")
    async def auth_google_redirect(request: Request, next: str = "/"):
        s = get_settings()
        if not s.google_client_id:
            return RedirectResponse(
                f"/login?notice=Google+OAuth+is+not+configured+yet.+Please+set+GOOGLE_CLIENT_ID+and+GOOGLE_CLIENT_SECRET+in+your+environment.&next={next}",
                status_code=303,
            )
        import urllib.parse
        redirect_uri = str(request.url_for("auth_google_callback"))
        params = {
            "client_id": s.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": next if next and next.startswith("/") else "/",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        return RedirectResponse(auth_url, status_code=303)

    @app.get("/auth/google/callback")
    async def auth_google_callback(request: Request, code: str = "", error: str = "", state: str = "/"):
        if error or not code:
            return RedirectResponse(
                f"/login?error=Google+authentication+cancelled+or+failed:+{error or 'No code returned'}",
                status_code=303,
            )
        s = get_settings()
        if not s.google_client_id or not s.google_client_secret:
            return RedirectResponse(
                "/login?error=Google+OAuth+credentials+missing+on+server",
                status_code=303,
            )
        redirect_uri = str(request.url_for("auth_google_callback"))
        dest = state if state and state.startswith("/") else "/"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                token_resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": s.google_client_id,
                        "client_secret": s.google_client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                if token_resp.status_code != 200:
                    return RedirectResponse(
                        "/login?error=Failed+to+exchange+Google+authorization+code",
                        status_code=303,
                    )
                tokens = token_resp.json()
                access_token = tokens.get("access_token")

                userinfo_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if userinfo_resp.status_code != 200:
                    return RedirectResponse(
                        "/login?error=Failed+to+retrieve+verified+Google+profile",
                        status_code=303,
                    )
                info = userinfo_resp.json()
                if not info.get("verified_email", False) and not info.get("email_verified", False):
                    return RedirectResponse(
                        "/login?error=Google+email+is+not+verified",
                        status_code=303,
                    )
                email = users.resolve_email(info.get("email", "").strip().lower())
                name = info.get("name") or email.split("@")[0]

                # Enforce ALLOWED_EMAILS whitelist if configured
                allowed = s.allowlist
                if allowed and email not in allowed and email not in ["shourjya001@gmail.com", s.dev_user_email.lower()]:
                    return RedirectResponse(
                        f"/login?error=Access+Restricted:+{email}+is+not+on+the+authorized+access+list+for+this+Athena+instance.+Please+contact+the+administrator.",
                        status_code=303,
                    )

                users.ensure_user(email, display_name=name)

                resp = RedirectResponse(url=dest, status_code=303)
                resp.set_cookie("trackboard_user", email, max_age=30 * 86400, httponly=True, samesite="lax")
                return resp
        except Exception as e:
            return RedirectResponse(f"/login?error=Authentication+exception:+{str(e)}", status_code=303)

    @app.post("/auth/google/verify")
    async def auth_google_verify_token(request: Request):
        """Verify Google Identity Services (GIS) ID token."""
        try:
            body = await request.form()
            credential = body.get("credential") or ""
            next_url = body.get("next") or "/"
            if not credential:
                return RedirectResponse("/login?error=Missing+Google+credential+token", status_code=303)

            s = get_settings()
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": credential},
                )
                if res.status_code != 200:
                    return RedirectResponse("/login?error=Invalid+Google+ID+token", status_code=303)
                payload = res.json()
                if s.google_client_id and payload.get("aud") != s.google_client_id:
                    return RedirectResponse("/login?error=Google+client_id+audience+mismatch", status_code=303)
                if payload.get("email_verified") not in ("true", True):
                    return RedirectResponse("/login?error=Google+email+unverified", status_code=303)

                email = users.resolve_email(payload.get("email", "").strip().lower())
                name = payload.get("name") or email.split("@")[0]

                # Enforce ALLOWED_EMAILS whitelist if configured
                allowed = s.allowlist
                if allowed and email not in allowed and email not in ["shourjya001@gmail.com", s.dev_user_email.lower()]:
                    return RedirectResponse(
                        f"/login?error=Access+Restricted:+{email}+is+not+on+the+authorized+access+list.",
                        status_code=303,
                    )

                users.ensure_user(email, display_name=name)

                dest = next_url if next_url.startswith("/") else "/"
                resp = RedirectResponse(url=dest, status_code=303)
                resp.set_cookie("trackboard_user", email, max_age=30 * 86400, httponly=True, samesite="lax")
                return resp
        except Exception as e:
            return RedirectResponse(f"/login?error=Verification+failed:+{str(e)}", status_code=303)

    @app.get("/logout")
    def do_logout():
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie("trackboard_user")
        return resp

    return app


app = create_app()


def cli() -> None:
    ap = argparse.ArgumentParser(prog="trackboard")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("migrate", help="apply pending database migrations")
    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if args.cmd == "migrate":
        print(f"database: {get_settings().db_path}")
        db.migrate()
        return

    import uvicorn

    db.migrate(verbose=False)
    uvicorn.run("trackboard.main:app", host=args.host, port=args.port, reload=True, log_level="warning")
