"""Email delivery service for Daily Digest and job recommendations (BUILD_SPEC §8.9).

Supports standard SMTP (Gmail App Passwords, AWS SES, Resend, etc.).
When SMTP is not configured, saves the HTML digest to ~/.trackboard/digests/
for local inspection.
"""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from .settings import get_settings


def render_digest_html(digest: dict, user_email: str) -> str:
    """Render a responsive HTML email matching Trackboard's design system."""
    top_matches = digest.get("top_matches", [])
    failures = digest.get("source_failures", [])
    pipeline_moves = digest.get("pipeline_moves", [])
    practiced = digest.get("problems_practiced", 0)

    # 1. Source failures block (must be top per §8.9)
    failure_html = ""
    if failures:
        rows = "".join(
            f'<li style="color:#f85149;margin-bottom:6px;"><strong>{f.get("agent","Source")}</strong> ({f.get("status","failed")}): {f.get("error","Unknown error")}</li>'
            for f in failures
        )
        failure_html = f"""
        <div style="background:#2a1215;border:1px solid rgba(248,81,73,0.4);border-radius:8px;padding:14px;margin-bottom:20px;">
          <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#f85149;margin-bottom:8px;">⚠️ Source Failures (Action Required)</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;">{rows}</ul>
        </div>
        """

    # 2. Top Matches block
    matches_html = ""
    if top_matches:
        items = ""
        for m in top_matches:
            score = m.get("fit_score", 0)
            score_color = "#3fb950" if score >= 85 else "#e3b341"
            apply_url = m.get("apply_url") or "http://localhost:8000/jobs"
            items += f"""
            <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px;margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                <div>
                  <span style="font-size:15px;font-weight:600;color:#f0f6fc;">{m.get('title','Software Engineer')}</span>
                  <span style="color:#8b949e;"> · </span>
                  <span style="font-size:14px;color:#e3b341;font-weight:600;">{m.get('company_name','Company')}</span>
                </div>
                <span style="font-family:monospace;font-size:13px;font-weight:700;color:{score_color};background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:4px;">
                  {score}% {m.get('verdict','MATCH').upper()}
                </span>
              </div>
              <div style="font-size:12px;color:#8b949e;margin-bottom:10px;">
                {m.get('reasoning','Matched against your digital payment switch and backend architecture experience.')}
              </div>
              <div>
                <a href="{apply_url}" style="display:inline-block;background:#238636;color:#ffffff;font-size:12px;font-weight:600;text-decoration:none;padding:6px 14px;border-radius:6px;">
                  View &amp; Apply ↗
                </a>
              </div>
            </div>
            """
        matches_html = f"""
        <div style="margin-bottom:24px;">
          <div style="font-size:13px;font-weight:700;text-transform:uppercase;color:#8b949e;letter-spacing:0.04em;margin-bottom:12px;">
            🎯 Recommended High-Fit Jobs Today
          </div>
          {items}
        </div>
        """
    else:
        matches_html = """
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:20px;color:#8b949e;font-size:13px;">
          No new matches scored today. Matcher agent runs continuously over open pipelines.
        </div>
        """

    # 3. Pipeline moves
    pipeline_html = ""
    if pipeline_moves:
        moves = "".join(
            f'<li style="margin-bottom:4px;"><strong style="color:#f0f6fc;">{p.get("company_name")}</strong> - {p.get("title")}: <span style="color:#58a6ff;">{p.get("status")}</span></li>'
            for p in pipeline_moves
        )
        pipeline_html = f"""
        <div style="margin-bottom:20px;">
          <div style="font-size:13px;font-weight:700;text-transform:uppercase;color:#8b949e;letter-spacing:0.04em;margin-bottom:8px;">
            📋 Pipeline Activity
          </div>
          <ul style="margin:0;padding-left:18px;font-size:13px;color:#c9d1d9;">{moves}</ul>
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:24px;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#c9d1d9;line-height:1.5;">
  <div style="max-width:640px;margin:0 auto;background:#0d1117;border:1px solid #30363d;border-radius:12px;overflow:hidden;padding:24px;">
    <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #30363d;padding-bottom:16px;margin-bottom:20px;">
      <div>
        <span style="font-family:monospace;font-size:11px;color:#e3b341;text-transform:uppercase;letter-spacing:0.06em;font-weight:700;">TRACKBOARD DIGEST</span>
        <h1 style="font-size:20px;font-weight:700;color:#f0f6fc;margin:4px 0 0 0;">Daily Job Matches &amp; Status</h1>
      </div>
      <div style="font-size:12px;color:#8b949e;">{datetime.now().strftime('%d %b %Y')}</div>
    </div>

    {failure_html}
    {matches_html}
    {pipeline_html}

    <div style="background:#161b22;border-radius:8px;padding:12px 16px;font-size:12px;color:#8b949e;display:flex;justify-content:space-between;">
      <span>DSA Practice today: <strong style="color:#f0f6fc;">{practiced} problems</strong></span>
      <a href="http://localhost:8000" style="color:#58a6ff;text-decoration:none;">Open Trackboard Web ↗</a>
    </div>
  </div>
</body>
</html>
"""


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via Resend API or SMTP, or save to disk if unconfigured."""
    settings = get_settings()
    from_email = settings.email_from or settings.smtp_user or "digest@trackboard.dev"

    # 1. First priority: Resend HTTP API (works seamlessly in serverless without SMTP port blocks)
    resend_api_key = os.getenv("RESEND_API_KEY", "").strip()
    if resend_api_key:
        try:
            import httpx
            sender = from_email if ("@" in from_email and "trackboard.dev" not in from_email) else "Trackboard <onboarding@resend.dev>"
            res = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {resend_api_key}", "Content-Type": "application/json"},
                json={
                    "from": sender,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                },
                timeout=12.0
            )
            if res.status_code in (200, 201):
                print(f"✓ Digest email successfully delivered to {to_email} via Resend API")
                return True
            else:
                print(f"Resend API returned status {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Resend API dispatch failed: {e}")

    # 2. Second priority: Standard SMTP
    if settings.smtp_host and settings.smtp_user:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to_email
            msg.attach(MIMEText(html_body, "html"))

            if settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
                server.starttls()

            clean_user = settings.smtp_user.strip()
            clean_pass = settings.smtp_password.strip().replace(" ", "")
            if clean_pass:
                server.login(clean_user, clean_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
            server.quit()
            print(f"✓ Digest email successfully delivered to {to_email} via SMTP")
            return True
        except Exception as e:
            print(f"SMTP send failed: {e}. Falling back to disk digest archive.")

    # Local fallback: Save to ~/.trackboard/digests/
    out_dir = Path(os.path.expanduser("~/.trackboard/digests"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"digest_{stamp}.html"
    out_file.write_text(html_body, encoding="utf-8")
    if settings.smtp_host and settings.smtp_user:
        print(f"ℹ Digest HTML saved locally to {out_file} (SMTP delivery failed; check credentials).")
    else:
        print(f"ℹ Digest HTML saved locally to {out_file} (SMTP / RESEND_API_KEY not configured in .env).")
    return False
