from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi import Form, File, UploadFile
from fastapi.responses import RedirectResponse

from . import content, db, drill, practice, users
from .settings import get_settings

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
_RUNNING_AGENT: dict[str, any] = {}


def create_app() -> FastAPI:
    app = FastAPI(title="Trackboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def today(request: Request):
        user = users.current_user(request)
        return templates.TemplateResponse(
            request,
            "pages/today.html",
            {
                "user": user,
                "health": content.content_health(),
                "patterns": content.list_patterns(user["id"])[:6],
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
            request,
            "pages/patterns.html",
            {"user": user, "families": families, "total": len(pats)},
        )

    @app.get("/patterns/{slug}", response_class=HTMLResponse)
    def pattern_detail(request: Request, slug: str):
        user = users.current_user(request)
        pat = content.get_pattern(slug)
        if not pat:
            return templates.TemplateResponse(
                request, "pages/missing.html", {"user": user, "what": slug},
                status_code=404,
            )
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

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(request: Request):
        user = users.current_user(request)
        rows = db.query(
            "SELECT m.bm25_score, m.fit_score, m.verdict, m.reasoning, m.gaps_json, "
            "j.* , m.id AS match_id FROM matches m JOIN jobs j ON j.id = m.job_id "
            "WHERE m.user_id=? AND m.dismissed_at IS NULL AND j.closed_at IS NULL "
            "ORDER BY m.fit_score IS NULL, m.fit_score DESC, m.bm25_score DESC LIMIT 40",
            (user["id"],))
        import json as _json
        items = []
        for r in rows:
            d = dict(r)
            d["gaps"] = _json.loads(d.get("gaps_json") or "[]")
            items.append(d)
        total_open = db.query_one("SELECT COUNT(*) n FROM jobs WHERE closed_at IS NULL")["n"]
        applied = request.query_params.get("applied") == "1"

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
                "applied": applied, "agent_running": agent_running,
                "agent_name": agent_name, "agent_started": agent_started,
                "agent_stopped": agent_stopped, "agent_busy": agent_busy,
                "digest_sent": digest_sent,
            })

    @app.post("/a/agent/run")
    def run_agent(agent: str = Form("matcher")):
        import subprocess, sys
        proc = _RUNNING_AGENT.get("proc")
        if proc is not None and proc.poll() is None:
            return RedirectResponse("/jobs?agent_busy=1", status_code=303)

        target = "trackboard.agents.matcher" if agent == "matcher" else "trackboard.agents.scout"
        new_proc = subprocess.Popen([sys.executable, "-m", target])
        _RUNNING_AGENT["name"] = agent
        _RUNNING_AGENT["proc"] = new_proc
        _RUNNING_AGENT["pid"] = new_proc.pid
        return RedirectResponse(f"/jobs?agent_started={agent}", status_code=303)

    @app.post("/a/agent/stop")
    def stop_agent():
        proc = _RUNNING_AGENT.get("proc")
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        _RUNNING_AGENT.clear()
        return RedirectResponse("/jobs?agent_stopped=1", status_code=303)

    @app.get("/jobs/{job_id}/tailor", response_class=HTMLResponse)
    def tailor_page(request: Request, job_id: int):
        user = users.current_user(request)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            return RedirectResponse("/jobs", status_code=303)
        job = dict(job)

        bank_path = Path("config/resume.yaml")
        if not bank_path.exists():
            return RedirectResponse("/jobs", status_code=303)

        import yaml
        from . import llm, tailor
        bank = yaml.safe_load(bank_path.read_text()) or {}

        tailored_resume = db.query_one(
            "SELECT * FROM resumes WHERE user_id=? AND label LIKE ? ORDER BY id DESC LIMIT 1",
            (user["id"], f"%Job {job_id}%")
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
            request, "pages/tailor.html",
            {
                "user": user,
                "job": job,
                "data": data,
                "bank": bank,
                "tailored_resume": tailored_resume,
                "saved": saved,
                "applied": applied,
            }
        )

    @app.post("/jobs/{job_id}/tailor/approve")
    async def approve_tailor(request: Request, job_id: int):
        user = users.current_user(request)
        job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            return RedirectResponse("/jobs", status_code=303)
        job = dict(job)

        bank_path = Path("config/resume.yaml")
        import yaml
        from . import tailor
        bank = yaml.safe_load(bank_path.read_text()) or {}

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

        skills = tailor.reorder_skills(bank, job.get("description_md") or "")
        out_dir = Path.home() / ".trackboard" / "resumes"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_pdf = out_dir / f"tailored_{user['id']}_{job_id}.pdf"

        tailor.render_pdf(bank, chosen_bullets or tailor.select_bullets(bank, job.get("description_md") or ""), skills, out_pdf)

        label = f"Tailored: {job['title']} @ {job['company_name']} (Job {job_id})"
        res_cur = db.execute(
            "INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) "
            "VALUES (?, ?, ?, ?, 0, datetime('now'))",
            (user["id"], label, str(out_pdf), str(chosen_bullets))
        )
        res_id = res_cur.lastrowid
        db.execute(
            "INSERT INTO applications (user_id, job_id, resume_id, status, status_source, last_event_at) "
            "VALUES (?, ?, ?, 'prepared', 'user', datetime('now')) "
            "ON CONFLICT(user_id, job_id) DO UPDATE SET "
            "resume_id=excluded.resume_id, last_event_at=datetime('now')",
            (user["id"], job_id, res_id)
        )
        return RedirectResponse(f"/jobs/{job_id}/tailor?saved=1", status_code=303)

    @app.post("/a/jobs/{job_id}/apply")
    def launch_applier(request: Request, job_id: int):
        user = users.current_user(request)
        # Record application as submitted in pipeline
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
                "VALUES (?, 'submitted', datetime('now'), 'applier', 'Playwright auto-applier executed', datetime('now'))",
                (app_row["id"],)
            )

        import subprocess, sys
        subprocess.Popen([
            sys.executable, "-m", "trackboard.agents.applier",
            str(job_id), "--user", user["email"]
        ])
        return RedirectResponse("/jobs?applied=1", status_code=303)

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
        rows = db.query(
            "SELECT a.*, j.company_name, j.title FROM applications a "
            "JOIN jobs j ON j.id = a.job_id WHERE a.user_id=? "
            "ORDER BY a.last_event_at DESC NULLS LAST", (user["id"],))
        cols: dict[str, list] = {}
        for r in rows:
            cols.setdefault(r["status"], []).append(dict(r))
        return templates.TemplateResponse(
            request, "pages/pipeline.html", {"user": user, "cols": cols})

    @app.get("/practice", response_class=HTMLResponse)
    def practice_page(request: Request):
        user = users.current_user(request)
        return templates.TemplateResponse(
            request, "pages/practice.html",
            {"user": user, "q": practice.build_queue(user["id"])},
        )

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
        return templates.TemplateResponse(
            request, "pages/drill.html",
            {"user": user, "item": drill.next_drill(user["id"]),
             "choices": drill.choices(), "result": None,
             "general_resources": content.general_resources()},
        )

    @app.post("/drill", response_class=HTMLResponse)
    def drill_answer(
        request: Request,
        problem_id: int = Form(...),
        chosen_pattern_id: int = Form(...),
        seconds: int = Form(0),
    ):
        user = users.current_user(request)
        result = drill.answer(user["id"], problem_id, chosen_pattern_id, seconds or None)
        return templates.TemplateResponse(
            request, "pages/drill.html",
            {"user": user, "item": None, "choices": drill.choices(), "result": result,
             "general_resources": content.general_resources()},
        )

    @app.get("/system", response_class=HTMLResponse)
    def system(request: Request):
        user = users.current_user(request)
        runs = db.query("SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT 50")
        return templates.TemplateResponse(
            request,
            "pages/system.html",
            {
                "user": user,
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
        if s.allowlist and clean not in s.allowlist and clean != s.dev_user_email.lower():
            return RedirectResponse(
                url="/login?error=" + f"{clean}+is+not+in+the+allowlist.+Contact+the+owner.",
                status_code=303,
            )
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie("trackboard_user", clean, max_age=30 * 86400, httponly=True, samesite="lax")
        return resp

    @app.get("/profile", response_class=HTMLResponse)
    def profile_page(request: Request, saved: int = 0, resume_saved: int = 0, matched: int = 0):
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
        total_jobs = db.query_one("SELECT COUNT(*) as c FROM jobs")["c"]
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
            },
        )

    @app.post("/profile/targets")
    def save_targets(
        request: Request,
        display_name: str = Form(""),
        titles: str = Form(""),
        keywords: str = Form(""),
        locations: str = Form(""),
        min_ctc: str = Form(""),
        experience_years: str = Form(""),
        leetcode_user: str = Form(""),
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
            "keywords": keywords.strip(),
            "locations": locations.strip(),
            "min_ctc": min_ctc.strip(),
            "experience_years": experience_years.strip(),
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
        extracted_text = resume_text.strip()
        label = "Uploaded Master Resume"

        if resume_file and resume_file.filename:
            content_bytes = await resume_file.read()
            label = resume_file.filename
            if resume_file.filename.lower().endswith(".pdf"):
                try:
                    import io
                    from pdfminer.high_level import extract_text as pdf_extract
                    extracted_text = pdf_extract(io.BytesIO(content_bytes)).strip()
                except Exception as e:
                    extracted_text = f"Error extracting PDF: {e}\n\n" + extracted_text
            else:
                try:
                    extracted_text = content_bytes.decode("utf-8", errors="ignore").strip()
                except Exception:
                    pass

        if extracted_text:
            db.execute("UPDATE resumes SET is_master=0 WHERE user_id=?", (uid,))
            db.execute(
                "INSERT INTO resumes (user_id, label, file_path, parsed_text, is_master, created_at) "
                "VALUES (?, ?, ?, ?, 1, datetime('now'))",
                (uid, label, f"upload/{label}", extracted_text),
            )

        return RedirectResponse("/profile?resume_saved=1", status_code=303)

    @app.post("/a/matcher/run")
    def run_matcher_on_demand(request: Request):
        user = users.current_user(request)
        from .agents.matcher import run_matcher_for_user
        run_matcher_for_user(user, force_bm25=False)
        return RedirectResponse("/profile?matched=1", status_code=303)

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
