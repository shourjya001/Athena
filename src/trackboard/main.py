from __future__ import annotations

import argparse
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi import Form, File, UploadFile
from fastapi.responses import RedirectResponse

from . import content, db, drill, llm, practice, users
from .settings import get_settings

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
_RUNNING_AGENT: dict[str, any] = {}


def format_ist(val: any) -> str:
    if not val:
        return ""
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        s = str(val).strip()
        dt = datetime.fromisoformat(s.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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
        return templates.TemplateResponse(
            request,
            "pages/today.html",
            {
                "user": user,
                "answers": answers,
                "health": content.content_health(),
                "patterns": content.list_patterns(user["id"])[:6],
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

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(request: Request):
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
                "ORDER BY m.fit_score IS NULL, m.fit_score DESC, m.bm25_score DESC LIMIT 40",
                (user["id"], user["id"]))
            import json as _json
            for r in rows:
                d = dict(r)
                d["gaps"] = _json.loads(d.get("gaps_json") or "[]")
                d["strengths"] = _json.loads(d.get("strengths_json") or "[]")
                items.append(d)

        if not items:
            # Fallback: display freshest open jobs so candidate always sees the real live catalog
            rows = db.query(
                "SELECT 0.0 as bm25_score, NULL as fit_score, NULL as verdict, NULL as reasoning, '[]' as gaps_json, '[]' as strengths_json, "
                "j.*, 0 as match_id FROM jobs j WHERE j.closed_at IS NULL "
                "AND j.id NOT IN (SELECT job_id FROM applications WHERE user_id=?) "
                "ORDER BY j.first_seen_at DESC LIMIT 40",
                (user["id"],)
            )
            for r in rows:
                d = dict(r)
                d["gaps"] = []
                d["strengths"] = []
                items.append(d)

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

        return templates.TemplateResponse(
            request, "pages/jobs.html",
            {
                "user": user, "items": items, "total_open": total_open,
                "matched_count": len(items), "answers": answers,
                "applied": applied, "matched": matched,
                "has_resume": has_resume,
                "agent_running": agent_running,
                "agent_name": agent_name, "agent_started": agent_started,
                "agent_stopped": agent_stopped, "agent_busy": agent_busy,
                "digest_sent": digest_sent,
            })

    @app.post("/a/agent/run")
    def run_agent(agent: str = Form("matcher")):
        import subprocess, sys
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
            job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
            if not job:
                return RedirectResponse("/jobs", status_code=303)
            job = dict(job)

            from . import tailor
            import yaml
            
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

        from . import tailor
        import yaml
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

    @app.post("/a/jobs/{job_id}/apply")
    def launch_applier(request: Request, job_id: int):
        user = users.current_user(request)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        
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
                import subprocess, sys
                subprocess.Popen([
                    sys.executable, "-m", "trackboard.agents.applier",
                    str(job_id), "--user", user["email"]
                ])
            except Exception as e:
                import sys
                print(f"Notice on applier process spawn: {e}", file=sys.stderr)

        # 4. Redirect directly to official apply URL or to pipeline
        if job and job["apply_url"] and job["apply_url"].startswith("http"):
            return RedirectResponse(job["apply_url"], status_code=303)
        return RedirectResponse("/pipeline", status_code=303)

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
        answers = {
            r["key"]: r["value"]
            for r in db.query("SELECT key, value FROM profile_answers WHERE user_id=?", (user["id"],))
        }
        runs = db.query("SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT 50")
        return templates.TemplateResponse(
            request,
            "pages/system.html",
            {
                "user": user,
                "answers": answers,
                "runs": [dict(r) for r in runs],
                "health": content.content_health(),
                "db_path": str(get_settings().db_path),
                "db_kb": (
                    get_settings().db_path.stat().st_size // 1024
                    if get_settings().db_path.exists()
                    else 0
                ),
            },
        )

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, saved: int = 0, resume_saved: int = 0, matched: int = 0, error: str | None = None):
        user = users.current_user(request)
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
                                from pdfminer.pdfparser import PDFParser
                                from pdfminer.pdfdocument import PDFDocument
                                from pdfminer.pdfpage import PDFPage
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

    @app.post("/a/matcher/run")
    def run_matcher_on_demand(request: Request):
        user = users.current_user(request)
        from .agents.matcher import run_matcher_for_user
        run_matcher_for_user(user, force_bm25=False)
        return RedirectResponse("/jobs?matched=1", status_code=303)

    @app.get("/api/cron/sync-and-match")
    def cron_sync_and_match(request: Request):
        """Vercel cron endpoint for automated syncing, matching & digest dispatch."""
        import os
        cron_secret = os.getenv("CRON_SECRET", "")
        auth_header = request.headers.get("authorization", "")
        if cron_secret and auth_header != f"Bearer {cron_secret}":
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        from .agents.matcher import run_matcher_for_user
        from . import email
        results = []
        all_users = db.query("SELECT * FROM users ORDER BY id")
        for u in all_users:
            u = dict(u)
            user_res = {"user": u["email"]}
            try:
                m_res = run_matcher_for_user(u, force_bm25=False)
                user_res["matched"] = m_res
            except Exception as e:
                user_res["matcher_error"] = str(e)[:200]
            
            # Auto-dispatch daily HTML digest
            try:
                top_matches = db.query(
                    "SELECT j.title, j.company_name, j.location, j.apply_url, m.fit_score, m.verdict, m.reasoning "
                    "FROM matches m JOIN jobs j ON j.id=m.job_id "
                    "WHERE m.user_id=? AND m.dismissed_at IS NULL AND j.closed_at IS NULL "
                    "AND (m.fit_score IS NULL OR m.fit_score >= 50) "
                    "ORDER BY m.fit_score DESC LIMIT 6",
                    (u["id"],)
                )
                top_matches = [dict(r) for r in top_matches]
                if top_matches:
                    digest_payload = {
                        "top_matches": top_matches,
                        "pipeline_moves": [],
                        "problems_practiced": db.query_one("SELECT COUNT(*) n FROM practice_attempts WHERE user_id=? AND date(occurred_at)=date('now')", (u["id"],))["n"],
                        "source_failures": []
                    }
                    html = email.render_digest_html(digest_payload, u["email"])
                    sent = email.send_email(
                        to_email=u["email"],
                        subject=f"⚡ Trackboard Digest: {len(top_matches)} High-Fit Job Matches for {u.get('display_name') or 'You'}",
                        html_body=html
                    )
                    user_res["digest_dispatched"] = sent
            except Exception as e:
                user_res["digest_error"] = str(e)[:200]

            results.append(user_res)

        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": True, "users_processed": len(results), "results": results})

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str | None = None):
        s = get_settings()
        user = users.current_user(request)
        return templates.TemplateResponse(
            request,
            "pages/login.html",
            {
                "user": user,
                "allowlist": s.allowlist,
                "error": error,
            },
        )

    @app.post("/login")
    def do_login(email: str = Form(...)):
        s = get_settings()
        clean = email.strip().lower()
        if "@" not in clean:
            return RedirectResponse(
                url="/login?error=Please+enter+a+valid+email+address.",
                status_code=303,
            )
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie("trackboard_user", clean, max_age=30 * 86400, httponly=True, samesite="lax")
        return resp

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
