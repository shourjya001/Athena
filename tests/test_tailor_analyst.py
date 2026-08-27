import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml

BANK = {
    "identity": {"name": "Test Person", "email": "t@x.com", "phone": "+91 9876543210",
                 "linkedin": "linkedin.com/in/test", "location": "Mumbai"},
    "roles": [
        {"company": "Acme", "title": "Senior Engineer", "start": "2023-01", "end": "present",
         "bullets": [
             {"id": "a1", "text": "Cut p99 latency from 1.8s to 300ms by batching queries",
              "skills": ["python", "postgresql", "performance"]},
             {"id": "a2", "text": "Led migration of payments service to Kafka event streams",
              "skills": ["kafka", "microservices"]},
             {"id": "a3", "text": "Mentored four junior engineers through onboarding",
              "skills": ["mentoring"]},
         ]},
        {"company": "OldCo", "title": "Engineer", "start": "2020-06", "end": "2022-12",
         "bullets": [
             {"id": "b1", "text": "Built REST APIs in FastAPI serving 2M requests daily",
              "skills": ["python", "fastapi"]},
             {"id": "b2", "text": "Wrote CI pipelines reducing deploy time by 60 percent",
              "skills": ["ci", "devops"]},
         ]},
    ],
    "skills": {"languages": ["Python", "SQL"], "infra": ["Kafka", "PostgreSQL", "Docker"]},
    "education": [{"degree": "B.Tech CSE", "school": "Some University", "year": "2020"}],
}


def _bank_path(tmp_path: Path) -> Path:
    p = tmp_path / "resume.yaml"
    p.write_text(yaml.safe_dump(BANK))
    return p


def test_selection_prefers_jd_relevant_bullets(tmp_path):
    from trackboard.tailor import load_bank, select_bullets
    bank = load_bank(_bank_path(tmp_path))
    chosen = select_bullets(bank, "We need Kafka streaming and PostgreSQL performance tuning")
    acme_ids = [b["id"] for b in chosen["Acme"]]
    assert acme_ids.index("a2") < acme_ids.index("a3")   # kafka bullet outranks mentoring


def test_tailor_roundtrip_pdf_passes_parse_gate(tmp_path):
    from trackboard.analyst import analyse_pdf
    from trackboard.tailor import tailor
    out = tmp_path / "tailored.pdf"
    res = tailor(_bank_path(tmp_path), "python fastapi postgresql", out)
    assert res.path is not None and out.exists()
    assert set(res.bullet_ids) <= {"a1", "a2", "a3", "b1", "b2"}   # §8.4: only bank bullets
    rep = analyse_pdf(out)
    assert rep.contact_fields["email"] == "found"
    assert rep.contact_fields["phone"] == "found"
    assert rep.sections_found["experience"] and rep.sections_found["skills"]
    assert not rep.high_warnings


def test_gate_refuses_regression(tmp_path):
    from trackboard.analyst import ParseReport, report_regression
    master = ParseReport(sections_found={"experience": True, "skills": True},
                         contact_fields={"email": "found", "phone": "found", "linkedin": "found"})
    worse = ParseReport(sections_found={"experience": True, "skills": False},
                        contact_fields={"email": "found", "phone": "missing", "linkedin": "found"})
    reasons = report_regression(master, worse)
    assert "section lost: skills" in reasons and "contact field lost: phone" in reasons


def test_multi_column_heuristic_flags_gappy_text():
    from trackboard.analyst import analyse_text
    gappy = "\n".join(f"left column text {'    '} right column text {i}" for i in range(20))
    rep = analyse_text(gappy + "\nexperience\nskills\nt@x.com +91 9876543210 linkedin.com/in/x")
    assert any(w["code"] == "multi_column" for w in rep.warnings)


def test_applier_field_matching():
    from trackboard.agents.applier import match_field
    assert match_field("Expected CTC (INR)") == "expected_ctc"
    assert match_field("Notice Period") == "notice_period_days"
    assert match_field("", autocomplete="email") == "email"
    assert match_field("Favourite colour") is None
