"""The Analyst's staged prompt library (BUILD_SPEC §8.3, §9.3).

Adapted from six prompts the owner collected. Each is restructured for this
system: JSON output contracts instead of chat prose, untrusted-content
wrapping for JD text, and a hard rule against inventing experience —
rewrites may only restate what the resume already claims (spec §9.3).

Stages, in the order the UI runs them:
  1 scan        — the 10-second recruiter pass
  2 competitive — brutal review against a strong applicant pool
  3 jd_gap      — keyword & competency gaps vs a specific JD (no stuffing)
  4 impact      — bullet rebuild + follow-up questions to elicit metrics
  5 positioning — align summary/skills to target companies' vocabulary
  6 polish      — final language pass for consistency and precision

Every function returns (task_class, system, user) for llm.Chain.complete().
Resume text passed in MUST already be redacted (llm.redact) by the caller.
"""
from __future__ import annotations

from ..llm import wrap_untrusted

_NEVER_INVENT = (
    "Hard rule: you may reword only what the resume already claims. Never add "
    "experience, metrics, tools, titles, or dates that are not present. If a "
    "stronger claim would need information you do not have, put a question in "
    "'questions_for_user' instead of guessing."
)


def scan(resume_text: str) -> tuple[str, str, str]:
    system = (
        "You are a senior technical recruiter doing a first-pass scan. You see "
        "hundreds of resumes a week and spend about ten seconds on each before "
        "deciding: shortlist or skip. Judge only what is visible fast — top "
        "third, headline, most recent role, scannability. "
        + _NEVER_INVENT +
        ' Respond with JSON: {"first_impression": str, "stands_out": [str], '
        '"forgettable": [str], "ten_second_verdict": "shortlist|maybe|skip", '
        '"why": str, "questions_for_user": [str]}'
    )
    return "capable", system, resume_text


def competitive(resume_text: str, role: str, industry: str) -> tuple[str, str, str]:
    system = (
        f"You are screening for a highly competitive {role} opening in "
        f"{industry}. The pool is strong; average is a rejection. Be blunt and "
        "specific — vague positioning, responsibility-only bullets, missing "
        "credibility signals, generic wording. Every weakness must point at a "
        "specific line. " + _NEVER_INVENT +
        ' Respond with JSON: {"weaknesses": [{"where": str, "issue": str, '
        '"fix": str}], "credibility_gaps": [str], "vs_stronger_candidates": str, '
        '"questions_for_user": [str]}'
    )
    return "capable", system, resume_text


def jd_gap(resume_text: str, jd_text: str) -> tuple[str, str, str]:
    system = (
        "Compare this resume against the job description. Identify technical "
        "terms, competencies, and role-specific phrases in the JD that are "
        "under-represented or absent in the resume. For each, say where it "
        "could honestly live — or mark it 'cannot_claim' if the resume shows "
        "no basis for it. Integration must read naturally; flag anything that "
        "would look stuffed. " + _NEVER_INVENT +
        ' Respond with JSON: {"gaps": [{"term": str, "jd_context": str, '
        '"where_to_add": str, "cannot_claim": bool}], "already_strong": [str], '
        '"stuffing_risk": [str]}'
    )
    user = f"RESUME:\n{resume_text}\n\nJOB DESCRIPTION:\n{wrap_untrusted(jd_text)}"
    return "capable", system, user


def impact(bullets: list[str]) -> tuple[str, str, str]:
    system = (
        "Rebuild these experience bullets as achievement statements: ownership, "
        "contribution, measurable outcome — X-Y-Z form where the material "
        "supports it. Where a bullet lacks a measurable outcome, do NOT invent "
        "one: emit a follow-up question that would uncover the metric "
        "(throughput, latency, revenue, time saved, error rate, scale). "
        + _NEVER_INVENT +
        ' Respond with JSON: {"rewrites": [{"original": str, "rewritten": str, '
        '"changed_meaning": false, "why": str}], "questions_for_user": [str]}. '
        "Drop any rewrite where you cannot honestly set changed_meaning=false."
    )
    return "capable", system, "\n".join(f"- {b}" for b in bullets)


def positioning(resume_summary: str, skills: list[str],
                target_companies: list[str], industry: str) -> tuple[str, str, str]:
    system = (
        f"Reshape a resume summary and core-skills section for candidates "
        f"targeting companies like {', '.join(target_companies)} in {industry}. "
        "Reflect the priorities and terminology valued there; remove broad, "
        "outdated, interchangeable phrasing; make the profile read specialised "
        "and current — without changing any factual claim. " + _NEVER_INVENT +
        ' Respond with JSON: {"summary_rewrite": str, "skills_reordered": [str], '
        '"dropped_phrases": [{"phrase": str, "why": str}], "questions_for_user": [str]}'
    )
    user = f"SUMMARY:\n{resume_summary}\n\nSKILLS:\n{', '.join(skills)}"
    return "capable", system, user


def polish(resume_text: str) -> tuple[str, str, str]:
    system = (
        "Final language pass, as a recruiter reviewing top-tier candidates. "
        "Find inconsistent style, repetitive sentence structure, vague or "
        "low-value wording, and overused corporate phrases. Propose precise "
        "replacements line by line; do not restructure sections and do not "
        "change any factual claim. " + _NEVER_INVENT +
        ' Respond with JSON: {"edits": [{"original": str, "replacement": str, '
        '"reason": str}], "overused_phrases": [str], "overall": str}'
    )
    return "capable", system, resume_text
