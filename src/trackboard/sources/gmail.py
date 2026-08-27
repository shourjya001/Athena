"""Thin Gmail wrapper (BUILD_SPEC §7.3). Requires the [full] extra and a
per-user OAuth token at ~/.trackboard/tokens/{user_id}.json (scope
gmail.readonly). Everything here is I/O; logic lives in agents/inbox.py.

First-time auth (run on the user's machine, once per user):
    python -m trackboard.sources.gmail --user you@example.com --auth client_secret.json
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

TOKENS = Path.home() / ".trackboard" / "tokens"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _service(user_id: int):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = TOKENS / f"{user_id}.json"
    if not token_path.exists():
        raise RuntimeError(f"no gmail token for user {user_id}; run the --auth flow first")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_recent(user_id: int, query: str = "newer_than:7d", max_results: int = 200) -> list[dict]:
    """Returns [{id, sender_domain, subject, snippet}] — metadata only, never bodies."""
    svc = _service(user_id)
    resp = svc.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    out = []
    for ref in resp.get("messages", []) or []:
        msg = svc.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
            metadataHeaders=["From", "Subject"]).execute()
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        sender = headers.get("from", "")
        out.append({
            "id": ref["id"],
            "sender_domain": sender.split("@")[-1].strip("> ").lower() if "@" in sender else "",
            "subject": headers.get("subject", ""),
            "snippet": msg.get("snippet", ""),
        })
    return out


def fetch_alert_html(user_id: int, message_id: int) -> str:
    """Full body ONLY for Trackboard/Alerts messages (job cards, §7.7)."""
    svc = _service(user_id)
    msg = svc.users().messages().get(userId="me", id=message_id, format="full").execute()

    def walk(part) -> str:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode(errors="ignore")
        return "".join(walk(p) for p in part.get("parts", []) or [])
    return walk(msg["payload"])


def auth_flow(user_id: int, client_secret_path: str) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    creds = flow.run_local_server(port=0)
    TOKENS.mkdir(parents=True, exist_ok=True)
    path = TOKENS / f"{user_id}.json"
    path.write_text(creds.to_json())
    path.chmod(0o600)
    print(f"token saved: {path}")


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from trackboard import db
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--auth", help="path to Google client_secret.json")
    args = ap.parse_args()
    row = db.query_one("SELECT id FROM users WHERE email=?", (args.user.lower(),))
    if not row:
        raise SystemExit(f"unknown user {args.user}")
    if args.auth:
        auth_flow(row["id"], args.auth)
