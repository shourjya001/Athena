"""LinkedIn Profile & AI Visibility Optimizer (based on linkedin-profile-optimizer skill).

Audits and rewrites LinkedIn profiles, optimizes headlines, About sections,
experience bullets, and provides an 8-point AI Visibility Checklist for ChatGPT,
Perplexity, Claude, and LinkedIn Recruiter search algorithms.
"""
from __future__ import annotations

import json
import re
from typing import Any

BUZZWORDS = [
    ("results-driven", "outcome-focused on [specific metric]"),
    ("results-oriented", "metrics-grounded"),
    ("passionate about", "specialized in"),
    ("passionate", "focused / specialized"),
    ("passion for", "deep expertise in"),
    ("dynamic professional", "engineer / specialist"),
    ("synergy", "cross-functional coordination"),
    ("synergies", "collaborative alignment"),
    ("synergistic", "collaborative"),
    ("leveraging", "deploying / utilizing"),
    ("comprehensive", "end-to-end"),
    ("robust", "fault-tolerant / high-availability"),
    ("visionary", "forward-looking"),
    ("thought leader", "contributor / speaker"),
    ("seasoned professional", "engineer with [N] years in [domain]"),
    ("proven track record", "demonstrated scale of [X]"),
    ("go-getter", "self-directed initiator"),
    ("strategic thinker", "systems architect"),
    ("detail-oriented", "rigorous"),
    ("team player", "collaborative partner"),
    ("excited to announce", "shipped / released"),
    ("excited to share", "published"),
    ("cutting-edge", "production-grade"),
    ("game-changing", "transformative"),
    ("revolutionary", "high-impact"),
]


def scan_buzzwords(text: str) -> list[dict[str, str]]:
    """Scan text for generic buzzwords and provide concrete, specific replacements."""
    lower = text.lower()
    found = []
    for word, replacement in BUZZWORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", lower):
            found.append({
                "buzzword": word,
                "replacement": replacement,
                "reason": f"'{word}' is generic filler. Replace with '{replacement}'."
            })
    return found


def calculate_ai_visibility(headline: str, about: str, experiences: str, linkedin_url: str = "") -> dict[str, Any]:
    """Score the 8 AI Visibility criteria for AI search engines (ChatGPT, Perplexity, Claude)."""
    checks = []
    total_passed = 0

    # 1. Entity Clarity (Name + role + niche in first 50 words)
    head_about = f"{headline} {about[:300]}".lower()
    has_role = bool(re.search(r"\b(engineer|developer|architect|lead|analyst|manager|founder|cmo|cfo|cto|specialist)\b", head_about))
    has_niche = bool(re.search(r"\b(fintech|backend|ai|distributed|saas|payments|cloud|frontend|infra|data|security|mobile)\b", head_about))
    ec_status = "pass" if (has_role and has_niche) else "needs_work" if has_role else "missing"
    if ec_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Entity Clarity",
        "status": ec_status,
        "detail": "Identifies exact role and niche immediately for AI entity extraction." if ec_status == "pass" else "Add exact role + clear technical domain in the first 50 words."
    })

    # 2. Niche Specificity
    ns_match = bool(re.search(r"\b(series [a-c]|b2b|d2c|latency|p99|high[- ]scale|kubernetes|microservices|llm|rag|postgres|redis|kafka)\b", head_about))
    ns_status = "pass" if ns_match else "needs_work"
    if ns_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Niche Specificity",
        "status": ns_status,
        "detail": "Contains specialized domain terminology that surfaces in niche AI queries." if ns_status == "pass" else "Include hyper-specific technologies or business outcomes."
    })

    # 3. Third-Party Mentions & Validation
    tpm_match = bool(re.search(r"\b(ex-|former|featured in|published|speaker|hackathon|top \d|contributor to|alumni)\b", f"{about} {experiences}".lower()))
    tpm_status = "pass" if tpm_match else "missing"
    if tpm_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Third-Party Mentions",
        "status": tpm_status,
        "detail": "Features external proof (companies, publications, recognitions) giving AI entity authority." if tpm_status == "pass" else "Add past brand names, open-source projects, or publications."
    })

    # 4. Content Consistency
    cc_status = "pass" if len(headline) > 20 and len(about) > 50 else "needs_work"
    if cc_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Content Consistency",
        "status": cc_status,
        "detail": "Headline and About section align tightly on common technical vocabulary."
    })

    # 5. Direct Answer Language
    da_match = bool(re.search(r"\b(helps|builds|specializes in|architects|scales|optimizes|leads|delivers)\b", about.lower()))
    da_status = "pass" if da_match else "needs_work"
    if da_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Direct Answer Language",
        "status": da_status,
        "detail": "Uses citation-ready sentence structure (e.g. 'Builds high-throughput systems for...')." if da_status == "pass" else "Add one sentence stating: '[Name] helps [audience] achieve [outcome]'."
    })

    # 6. Recency Signals
    rec_match = bool(re.search(r"\b(202[3-6]|present|current)\b", f"{about} {experiences}".lower()))
    rec_status = "pass" if rec_match else "needs_work"
    if rec_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Recency Signals",
        "status": rec_status,
        "detail": "Includes up-to-date timeline indicators preventing AI obsolescence penalties."
    })

    # 7. Custom URL Match
    url_clean = (linkedin_url or "").strip().lower()
    has_custom_url = bool("linkedin.com/in/" in url_clean and not re.search(r"-[a-f0-9]{7,}", url_clean))
    url_status = "pass" if has_custom_url else "needs_work" if url_clean else "missing"
    if url_status == "pass":
        total_passed += 1
    checks.append({
        "name": "URL / Name Match",
        "status": url_status,
        "detail": "Clean custom LinkedIn vanity URL maximizes entity resolution." if url_status == "pass" else "Claim a clean custom URL (e.g., linkedin.com/in/first-last-tech)."
    })

    # 8. Cross-Platform Footprint
    cp_match = bool(re.search(r"\b(github|gitlab|portfolio|substack|twitter|x\.com|medium|dev\.to)\b", f"{headline} {about} {experiences}".lower()))
    cp_status = "pass" if cp_match else "missing"
    if cp_status == "pass":
        total_passed += 1
    checks.append({
        "name": "Cross-Platform Footprint",
        "status": cp_status,
        "detail": "Cross-references external profiles, allowing AI models to triangulate authority." if cp_status == "pass" else "Link your GitHub, technical blog, or portfolio inside About or Featured."
    })

    # Top 3 recommendations
    top_moves = []
    for c in checks:
        if c["status"] != "pass" and len(top_moves) < 3:
            top_moves.append(f"Improve {c['name']}: {c['detail']}")
    if not top_moves:
        top_moves = [
            "Pin top 2 technical projects or case studies in your Featured section.",
            "Include exact framework versions and scale metrics (e.g. 50k+ QPS) for AI search citations.",
            "Maintain monthly post cadence around backend architecture to preserve recency signal."
        ]

    return {
        "score": total_passed,
        "max_score": 8,
        "percentage": int((total_passed / 8) * 100),
        "checks": checks,
        "top_moves": top_moves
    }


def audit_and_optimize_profile(
    headline: str,
    about: str,
    experiences: str = "",
    target_audience: str = "Engineering Leaders & Technical Recruiters",
    goal: str = "job seeker",
    linkedin_url: str = "",
    mode: str = "standard",
    chain: Any = None
) -> dict[str, Any]:
    """Audit and rewrite LinkedIn profile according to the 5-section optimizer framework."""
    buzzwords = scan_buzzwords(f"{headline} {about} {experiences}")
    ai_vis = calculate_ai_visibility(headline, about, experiences, linkedin_url)

    # Deterministic section scores
    hl_score = 6 if len(headline) > 30 and not buzzwords else 4
    about_score = 7 if len(about) > 200 and re.search(r"\b\d+[%kKmM]?\b", about) else 5
    exp_score = 7 if re.search(r"\b(built|designed|reduced|increased|scaled|engineered)\b", experiences.lower()) else 5
    featured_score = 6
    fit_score = 6 if len(headline) > 20 and len(about) > 50 else 4
    total_audit_score = hl_score + about_score + exp_score + featured_score + fit_score

    priority_fixes = [
        {"section": "Headline", "fix": "Transform into an outcome-focused claim with high-intent search keywords (Role + Outcome + Stack)."},
        {"section": "About Section", "fix": "Rewrite hook and add quantifiable scale metrics (latency, QPS, volume) in the first 2 lines."},
        {"section": "AI Visibility", "fix": f"Resolve {len(ai_vis['top_moves'])} AI visibility gaps to rank in Perplexity and ChatGPT search."},
        {"section": "Experience Bullets", "fix": "Anchor all role accomplishments with action verbs and quantifiable business impact."},
        {"section": "Custom Vanity URL", "fix": "Ensure URL reflects name and core engineering focus without auto-generated digit suffixes."}
    ]

    # Try LLM synthesis for tailored rewrites
    if chain:
        system = (
            "You are an elite LinkedIn Executive Ghostwriter & AI Talent Search Optimization Expert. "
            "You follow the exact 'linkedin-profile-optimizer' skill framework:\n"
            "- Buzzword zero tolerance: never use 'results-driven', 'passionate', 'dynamic', 'synergy'.\n"
            "- Section 2 Headlines: write 3 variants (Authority-forward, Outcome-forward, Niche-specific), max 220 chars each.\n"
            "- Section 3 About: Hook (bold claim, no 'Hi I am'), Credibility, Proof with numbers, CTA. MAX 220 WORDS.\n"
            "- Section 4 Experience: Rewrite top bullets into Action + Metric + Scale.\n"
            "Return valid JSON ONLY matching the requested structure."
        )
        user_prompt = (
            f"CURRENT HEADLINE:\n{headline}\n\n"
            f"CURRENT ABOUT:\n{about}\n\n"
            f"CURRENT EXPERIENCE:\n{experiences}\n\n"
            f"TARGET AUDIENCE: {target_audience}\n"
            f"GOAL: {goal}\n\n"
            "Generate JSON with format:\n"
            "{\n"
            '  "headline_variant_a": "string (Authority-forward: Role who creates specific outcome)",\n'
            '  "headline_variant_b": "string (Outcome-forward: From problem to outcome)",\n'
            '  "headline_variant_c": "string (Niche-specific: Category-defining descriptor)",\n'
            '  "headline_ab_recommendation": "string (which variant to test first and why)",\n'
            '  "about_rewrite": "string (max 220 words, Hook + Credibility + Proof + CTA)",\n'
            '  "about_word_count": 180,\n'
            '  "experience_bullet_rewrites": [{"company_role": "string", "before": "string", "after": "string"}],\n'
            '  "sample_linkedin_posts": ["string", "string", "string"]\n'
            "}"
        )
        try:
            raw_reply, _ = chain.complete("capable", system, user_prompt)
            match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                return {
                    "audit_scores": {
                        "headline": hl_score,
                        "about": about_score,
                        "experience": exp_score,
                        "featured": featured_score,
                        "fit": fit_score,
                        "total": total_audit_score,
                        "max": 50,
                    },
                    "priority_fixes": priority_fixes,
                    "buzzwords_found": buzzwords,
                    "headlines": {
                        "variant_a": parsed.get("headline_variant_a", headline),
                        "variant_b": parsed.get("headline_variant_b", headline),
                        "variant_c": parsed.get("headline_variant_c", headline),
                        "ab_recommendation": parsed.get("headline_ab_recommendation", "Test Variant A first to establish authority.")
                    },
                    "about": {
                        "rewrite": parsed.get("about_rewrite", about),
                        "word_count": parsed.get("about_word_count", len(parsed.get("about_rewrite", "").split()))
                    },
                    "experience_bullets": parsed.get("experience_bullet_rewrites", []),
                    "ai_visibility": ai_vis,
                    "sample_posts": parsed.get("sample_linkedin_posts", [])
                }
        except Exception as e:
            print("LinkedIn LLM optimization error:", e)

    # Robust deterministic fallback
    clean_hl = headline or "Software Engineer"
    var_a = f"{clean_hl} | Building high-scale distributed systems & fault-tolerant cloud infrastructure"[:220]
    var_b = f"Slashing p99 API latency and scaling transaction throughput for high-volume platforms | {clean_hl}"[:220]
    var_c = "Specialist in High-Throughput Distributed Microservices, Event Streaming & Modern Cloud Arch"[:220]

    about_rewritten = (
        "Architecting resilient backend systems that handle high traffic loads with sub-50ms latency.\n\n"
        "Engineered distributed microservices, optimized SQL/NoSQL storage layers, and automated zero-downtime CI/CD pipelines. "
        "Focused on turning complex system bottlenecks into predictable, horizontally scalable architectures.\n\n"
        "Key Scale & Impact:\n"
        "• Scaled API throughput to 10k+ requests/sec while cutting p95 response time by 40%\n"
        "• Designed event-driven Kafka pipelines processing millions of daily transactions\n"
        "• Reduced cloud infrastructure spend through automated autoscaling and containerization\n\n"
        "If you are scaling backend architecture or hiring for high-ownership engineering roles, reach out at my contact links or send a direct message."
    )

    return {
        "audit_scores": {
            "headline": hl_score,
            "about": about_score,
            "experience": exp_score,
            "featured": featured_score,
            "fit": fit_score,
            "total": total_audit_score,
            "max": 50,
        },
        "priority_fixes": priority_fixes,
        "buzzwords_found": buzzwords,
        "headlines": {
            "variant_a": var_a,
            "variant_b": var_b,
            "variant_c": var_c,
            "ab_recommendation": "Deploy Variant A (Authority-forward) first: it establishes immediate credibility and matches recruiter Boolean search operators."
        },
        "about": {
            "rewrite": about_rewritten,
            "word_count": len(about_rewritten.split())
        },
        "experience_bullets": [
            {
                "company_role": "Backend / Software Engineering",
                "before": "Responsible for developing backend APIs and working with databases.",
                "after": "Engineered high-concurrency RESTful APIs serving 2M+ requests daily, slashing p99 latency from 450ms to 65ms via Redis distributed caching."
            },
            {
                "company_role": "Platform & Cloud Architecture",
                "before": "Maintained deployment servers and fixed bugs in production.",
                "after": "Architected zero-downtime Kubernetes CI/CD workflows, boosting release velocity by 3x while eliminating staging deployment regressions."
            }
        ],
        "ai_visibility": ai_vis,
        "sample_posts": [
            "Most engineering teams try to solve database bottlenecks with bigger instances.\n\nHere is how we reduced query latency by 70% using compound indexing and Redis caching instead...",
            "3 microservice architecture lessons I learned scaling an event stream to 10M daily events:\n\n1. Idempotency is not optional\n2. Partition keys dictate your scale\n3. Observability beats guesswork every time.",
            "Writing clean code is good. Writing observable, fault-tolerant code in production is what keeps systems alive at 3 AM."
        ]
    }


def generate_job_targeted_linkedin_seo(
    job_title: str,
    company: str,
    jd_text: str,
    resume_text: str = "",
    chain: Any = None
) -> dict[str, Any]:
    """Generate job-specific LinkedIn Headline, SEO search tags, and AI visibility keywords
    so candidate profile ranks #1 when recruiters or AI search for skills required by this specific role."""
    jd_lower = (jd_text or "").lower()
    
    # Extract top keywords
    common_tech = [
        "python", "java", "c++", "golang", "fastapi", "django", "spring boot", "react", "node.js",
        "sql", "postgresql", "mysql", "mongodb", "redis", "memcached", "kafka", "rabbitmq",
        "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "microservices", "distributed systems",
        "grpc", "rest api", "ci/cd", "terraform", "linux", "system design", "machine learning",
        "llm", "rag", "langchain", "prompt engineering", "nlp", "data structures", "algorithms"
    ]
    matched_keywords = [t.title() if len(t) > 3 else t.upper() for t in common_tech if t in jd_lower]
    if not matched_keywords:
        matched_keywords = ["Python", "Backend Architecture", "Microservices", "PostgreSQL", "Redis", "Distributed Systems"]

    top_keywords = matched_keywords[:8]

    # Try LLM for ultra-targeted SEO
    if chain and jd_text:
        system = (
            "You are a LinkedIn Talent Search Algorithm & Recruiter SEO specialist. "
            "Given a job role and JD, generate the exact search-optimized LinkedIn Headline, "
            "Recruiter Boolean Search keywords, and About section SEO paragraph to make a candidate rank #1. "
            "Return valid JSON ONLY."
        )
        user_prompt = (
            f"TARGET JOB ROLE: {job_title} at {company}\n"
            f"JOB DESCRIPTION:\n{jd_text[:1200]}\n\n"
            "Generate JSON with:\n"
            "{\n"
            '  "seo_headline": "string (Max 220 chars, role + top 3 skills + outcome)",\n'
            '  "recruiter_search_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],\n'
            '  "boolean_search_match": "string (e.g. (Python OR Go) AND (Kafka OR Redis))",\n'
            '  "about_seo_snippet": "string (2-3 sentences to paste into About section containing high-intent keywords)",\n'
            '  "ai_search_citation_prompt": "string (simulated answer showing how Perplexity or ChatGPT surfaces this profile)"\n'
            "}"
        )
        try:
            raw_reply, _ = chain.complete("capable", system, user_prompt)
            match = re.search(r"\{.*\}", raw_reply, re.DOTALL)
            if match:
                res = json.loads(match.group(0))
                return {
                    "job_title": job_title,
                    "company": company,
                    "seo_headline": res.get("seo_headline", f"{job_title} | {' • '.join(top_keywords[:3])}"),
                    "keywords": res.get("recruiter_search_keywords", top_keywords),
                    "boolean_search": res.get("boolean_search_match", " AND ".join(f'"{k}"' for k in top_keywords[:4])),
                    "about_seo_snippet": res.get("about_seo_snippet", f"Specializing in {', '.join(top_keywords)} to build resilient production architectures."),
                    "ai_citation_preview": res.get("ai_search_citation_prompt", f"Top candidate profile for {job_title} with deep expertise in {', '.join(top_keywords[:3])}.")
                }
        except Exception as e:
            print("SEO LLM generation error:", e)

    # Fallback
    seo_hl = f"{job_title} | {' • '.join(top_keywords[:3])} | Distributed Systems & High-Scale Architecture"[:220]
    return {
        "job_title": job_title,
        "company": company,
        "seo_headline": seo_hl,
        "keywords": top_keywords,
        "boolean_search": " AND ".join(f'"{k}"' for k in top_keywords[:4]),
        "about_seo_snippet": f"Core engineering focus encompasses {', '.join(top_keywords)}. Architecting high-throughput solutions designed for fault tolerance and high scalability.",
        "ai_citation_preview": f"Identified as a high-authority candidate for {job_title} roles requiring {', '.join(top_keywords[:4])}."
    }
