"""AgentRun lifecycle (BUILD_SPEC §8, §6.7): every agent records a row, never
raises out of run(), and reports ok / partial / failed."""
from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone

from .. import db


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class AgentRun:
    def __init__(self, agent: str, user_id: int | None = None):
        self.agent, self.user_id = agent, user_id
        self.items_in = self.items_out = self.llm_calls = 0
        self.detail: dict = {}
        self._errors: list[str] = []
        self.run_id: int | None = None

    def error(self, source: str, message: str) -> None:
        self._errors.append(f"{source}: {message[:200]}")
        self.detail.setdefault("errors", []).append({"source": source, "message": message[:500]})

    def __enter__(self) -> "AgentRun":
        self.run_id = db.execute(
            "INSERT INTO agent_runs (agent, user_id, started_at, status) VALUES (?,?,?,'running')",
            (self.agent, self.user_id, _now()),
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None and isinstance(exc, (KeyboardInterrupt, SystemExit)):
            db.execute("UPDATE agent_runs SET finished_at=datetime('now'), status='failed', "
                       "error='interrupted' WHERE id=?", (self.run_id,))
            return False
        if exc is not None:
            self.error("agent", f"{exc_type.__name__}: {exc}")
            self.detail["traceback"] = traceback.format_exc()[-1500:]
            status = "failed"
        elif self._errors:
            status = "partial"
        else:
            status = "ok"
        db.execute(
            "UPDATE agent_runs SET finished_at=?, status=?, items_in=?, items_out=?, "
            "llm_calls=?, error=?, detail_json=? WHERE id=?",
            (_now(), status, self.items_in, self.items_out, self.llm_calls,
             "; ".join(self._errors) or None, json.dumps(self.detail), self.run_id),
        )
        return True  # never raise out of an agent
