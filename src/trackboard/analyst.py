"""Resume parse simulator (BUILD_SPEC §8.3.1, §9.2): what an ATS actually
extracts. Deterministic — no LLM, no score. The LLM stages live in
prompts/analyst.py and run through llm.Chain at the caller's choice."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from io import StringIO
from pathlib import Path

from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

SECTION_HINTS = {
    "experience": r"\b(work experience|professional experience|experience|employment)\b",
    "education": r"\b(education|academics|qualifications)\b",
    "skills": r"\b(skills|technical skills|technologies|tech stack)\b",
    "projects": r"\b(projects|personal projects|selected projects)\b",
    "summary": r"\b(summary|objective|profile|about)\b",
}


@dataclass
class ParseReport:
    extracted_text: str = ""
    page_count: int = 0
    sections_found: dict = field(default_factory=dict)
    contact_fields: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @property
    def high_warnings(self) -> list:
        return [w for w in self.warnings if w["severity"] == "high"]


def extract_pdf(path: Path) -> tuple[str, int]:
    out = StringIO()
    with open(path, "rb") as fh:
        extract_text_to_fp(fh, out, laparams=LAParams())
    text = out.getvalue()
    pages = max(1, text.count("\x0c")) if "\x0c" in text else 1
    return text, pages


def analyse_text(text: str, page_count: int = 1) -> ParseReport:
    rep = ParseReport(extracted_text=text, page_count=page_count)
    low = text.lower()

    for name, rx in SECTION_HINTS.items():
        rep.sections_found[name] = bool(re.search(rx, low))

    rep.contact_fields = {
        "email": "found" if re.search(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", text) else "missing",
        "phone": "found" if re.search(r"(\+?\d[\d\s().-]{8,}\d)", text) else "missing",
        "linkedin": "found" if "linkedin.com/" in low else "missing",
    }

    def warn(code, detail, severity):
        rep.warnings.append({"code": code, "detail": detail, "severity": severity})

    lines = [ln for ln in text.splitlines() if ln.strip()]
    gappy = sum(1 for ln in lines if re.search(r"\S\s{4,}\S", ln))
    if lines and gappy / len(lines) > 0.25:
        warn("multi_column", "Many lines contain wide internal gaps — a multi-column "
             "layout is likely interleaving during extraction.", "high")
    if page_count > 2:
        warn("over_two_pages", f"{page_count} pages extracted.", "medium")
    for fld, status in rep.contact_fields.items():
        if status == "missing":
            warn("contact_missing", f"{fld} did not survive extraction.", "high")
    if not rep.sections_found.get("experience"):
        warn("section_missing", "No recognisable experience section heading.", "high")
    if not rep.sections_found.get("skills"):
        warn("section_missing", "No recognisable skills section heading.", "medium")
    if len(text.strip()) < 400:
        warn("thin_extraction", "Very little text extracted — the PDF may be image-based.", "high")
    return rep


def analyse_pdf(path: Path) -> ParseReport:
    text, pages = extract_pdf(path)
    return analyse_text(text, pages)


def report_regression(master: ParseReport, generated: ParseReport) -> list[str]:
    """The §8.4.3 gate: reasons the generated resume is WORSE than the master.
    Empty list == safe to save."""
    reasons = []
    for name, found in master.sections_found.items():
        if found and not generated.sections_found.get(name):
            reasons.append(f"section lost: {name}")
    for fld, status in master.contact_fields.items():
        if status == "found" and generated.contact_fields.get(fld) != "found":
            reasons.append(f"contact field lost: {fld}")
    if generated.high_warnings and not master.high_warnings:
        reasons.extend(f"new high warning: {w['code']}" for w in generated.high_warnings)
    return reasons
