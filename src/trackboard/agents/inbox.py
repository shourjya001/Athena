"""Inbox agent (BUILD_SPEC §8.6): the pre-filter, batched classification, the
append-only status engine, and the ghosting pass. Gmail I/O is isolated in
sources/gmail.py and only touched in main(); everything else is pure enough
to test without credentials."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from pydantic import BaseModel

from .. import db
from ..llm import Chain, parse_json_reply, wrap_untrusted
from .base import AgentRun

ATS_RELAYS = ("greenhouse.io", "hire.lever.co", "lever.co", "ashbyhq.com", "myworkday.com",
              "smartrecruiters.com", "naukri.com", "linkedin.com", "indeed.com",
              "instahyre.com", "recruitee.com", "workablemail.com")
SUBJECT_RX = re.compile(r"applicat|interview|assessment|screening|candidat|opportunit|"
                        r"role at|position at|next steps|offer", re.I)
ORDER = ["prepared", "submitted", "acknowledged", "screening", "assessment",
         "interview", "offer"]
TERMINAL = {"rejected", "withdrawn"}
GHOST_DAYS = 21


def prefilter(sender: str, subject: str, company_domains: set[str]) -> bool:
    s = (sender or "").lower()
    domain = s.split("@")[-1].strip(">")
    if any(domain.endswith(r) for r in ATS_RELAYS):
        return True
    if any(domain.endswith(d) for d in company_domains if d):
        return True
    return bool(SUBJECT_RX.search(subject or ""))


class Classified(BaseModel):
    message_ref: str
    is_job_related: bool
    company: str | None = None
    role_hint: str | None = None
    status: str = "not_applicable"
    evidence: str = ""
    confidence: str = "low"


SYSTEM = (
    "Classify each email as a job-application event for the candidate. "
    "status: acknowledged|screening|assessment|interview|offer|rejected|not_applicable. "
    "evidence: a paraphrase under 200 chars, NEVER a verbatim quote. "
    "confidence high only when company and status are unambiguous. "
    'Respond with JSON: {"results": [{"message_ref": str, "is_job_related": bool, '
    '"company": str|null, "role_hint": str|null, "status": str, "evidence": str, '
    '"confidence": "high"|"medium"|"low"}]} — one entry per message_ref.'
)


def classify_batch(chain: Chain, messages: list[dict]) -> list[Classified]:
    parts = []
    for m in messages:
        parts.append(f"message_ref={m['id']} | from: {m['sender_domain']} | "
                     f"subject: {m['subject'][:150]}\n"
                     + wrap_untrusted(m.get("snippet", "")[:300]))
    reply, _ = chain.complete("fast", SYSTEM, "\n\n".join(parts))
    data = parse_json_reply(reply)
    return [Classified.model_validate(r) for r in data.get("results", [])]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def find_application(user_id: int, company: str) -> dict | None:
    best, best_score = None, 0.0
    for row in db.query(
        "SELECT a.id, a.status, j.company_name FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE a.user_id=?", (user_id,)):
        score = SequenceMatcher(None, company.lower(), row["company_name"].lower()).ratio()
        if score > best_score:
            best, best_score = dict(row), score
    return best if best_score >= 0.75 else None


def advance(application_id: int, new_status: str, source: str, evidence: str) -> bool:
    """Append an event and recompute status. Forward-only within ORDER;
    terminal statuses land from anywhere; regressions are ignored."""
    app = db.query_one("SELECT status FROM applications WHERE id=?", (application_id,))
    if app is None:
        return False
    cur = app["status"]
    if new_status not in TERMINAL:
        if cur in TERMINAL or cur == "ghosted":
            return False
        if new_status in ORDER and cur in ORDER and ORDER.index(new_status) <= ORDER.index(cur):
            return False
    db.execute(
        "INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
        "VALUES (?,?,?,?,?,?)", (application_id, new_status, _now(), source, evidence[:200], _now()))
    db.execute("UPDATE applications SET status=?, status_source='inbox_agent', last_event_at=? WHERE id=?",
               (new_status, _now(), application_id))
    return True


def ghost_pass() -> int:
    rows = db.query(
        "SELECT id FROM applications WHERE status IN ('submitted','acknowledged') "
        "AND last_event_at IS NOT NULL AND last_event_at < datetime('now', ?)",
        (f"-{GHOST_DAYS} days",))
    n = 0
    for r in rows:
        db.execute("UPDATE applications SET status='ghosted' WHERE id=?", (r["id"],))
        db.execute("INSERT INTO application_events (application_id, status, occurred_at, source, evidence, created_at) "
                   "VALUES (?,?,?,?,?,?)",
                   (r["id"], "ghosted", _now(), "system", f"no reply in {GHOST_DAYS} days", _now()))
        n += 1
    return n


def process_messages(user_id: int, messages: list[dict], chain: Chain, run: AgentRun) -> None:
    """messages: [{id, sender_domain, subject, snippet}] already pre-filtered
    and not in gmail_seen. Writes events for high confidence; medium becomes a
    note on gmail_seen for user review; low is discarded (§8.6.4)."""
    for i in range(0, len(messages), 10):
        batch = messages[i:i + 10]
        try:
            results = classify_batch(chain, batch)
            run.llm_calls += 1
        except Exception as e:
            run.error("classify", str(e))
            continue
        for c in results:
            mark = "discarded"
            if c.is_job_related and c.status != "not_applicable" and c.company:
                if c.confidence == "high":
                    app = find_application(user_id, c.company)
                    if app and advance(app["id"], c.status, f"gmail:{c.message_ref}", c.evidence):
                        run.items_out += 1
                        mark = c.status
                    elif app is None:
                        mark = f"review:{c.status}:{c.company}"   # unmatched — user review
                elif c.confidence == "medium":
                    mark = f"review:{c.status}:{c.company}"
            db.execute("INSERT OR IGNORE INTO gmail_seen (user_id, message_id, classified_as) VALUES (?,?,?)",
                       (user_id, c.message_ref, json.dumps(mark)))
