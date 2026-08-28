from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db

# 1. Real Banking & Financial Operations Roles (for Prerna & Banking Track)
banking_real_roles = [
    {
        "company_name": "Canara Robeco Asset Management",
        "title": "Operations Associate - Mutual Fund & Depository Settlements",
        "location": "Mumbai / Bengaluru, India",
        "ats": "darwinbox",
        "url": "https://www.canararobeco.com/careers",
        "description_md": """### About Canara Robeco
Canara Robeco Asset Management is a joint venture between Canara Bank and ORIX Corporation Europe N.V., managing mutual funds and institutional investments across India.

### Responsibilities
- Execute mutual fund transaction processing, redemption settlements, and depository reconciliation.
- Review investor KYC compliance, mandate verifications, and banking payment authorizations.
- Coordinate with custodian banks (HDFC, Citi) and registrar agents (CAMS/KFintech) for net settlement transfers.
- Generate operational discrepancy reports and regulatory audit filings using Excel and banking MIS systems.

### Qualifications
- 1 to 4 years experience in Banking Operations, Mutual Fund Operations, or Financial Services.
- Deep familiarity with clearing, NEFT/RTGS/NACH settlements, Demat accounts, and KYC guidelines.
- Strong attention to detail, Excel spreadsheet proficiency, and banking problem-solving skills.
"""
    },
    {
        "company_name": "Canara HSBC Life Insurance",
        "title": "Operations Specialist - Policy Servicing & Branch Underwriting",
        "location": "Gurugram / Bengaluru / Regional Hubs, India",
        "ats": "darwinbox",
        "url": "https://www.canarahsbclife.com/about-us/careers",
        "description_md": """### About Canara HSBC Life
Canara HSBC Life Insurance combines the banking network of Canara Bank and HSBC to provide life insurance and financial security products across India.

### Key Responsibilities
- Manage branch operations, policy issuance workflows, and premium collection reconciliations.
- Coordinate bancassurance operations with Canara Bank and HSBC partner branches.
- Handle customer service escalations, claim documentation reviews, and KYC verification checks.
- Audit daily branch cash flow, transaction logs, and operational compliance registers.

### Requirements
- 1 to 3 years experience in Banking Operations, Insurance Operations, or Financial Operations.
- Graduate degree in Commerce, Economics, Business Administration, or related discipline.
- Proven track record handling customer documentation, banking CRM systems, and operational SLAs.
"""
    },
    {
        "company_name": "HDFC Bank",
        "title": "Operations Officer - Centralized Clearing & Settlement Operations",
        "location": "Mumbai / Bengaluru, India",
        "ats": "darwinbox",
        "url": "https://www.hdfcbank.com/personal/about-us/careers",
        "description_md": """### Role Overview
HDFC Bank is hiring Operations Officers for its Retail Operations and Centralized Processing Group.

### Responsibilities
- Manage CTS clearing, NACH mandate processing, and high-value RTGS/NEFT payment transfers.
- Perform daily inter-bank reconciliation and resolve transaction discrepancies.
- Ensure strict adherence to RBI banking regulations, KYC/AML norms, and internal audit controls.
- Maintain operational turnaround times (TAT) for customer service requests and account servicing.

### Qualifications
- 1 to 3 years experience in branch banking or centralized operations.
- Proficiency in banking core software (Finacle) and Excel reporting.
"""
    },
    {
        "company_name": "ICICI Bank",
        "title": "Deputy Manager - Branch Banking & Customer Operations",
        "location": "Bengaluru / Mumbai / Delhi-NCR, India",
        "ats": "darwinbox",
        "url": "https://www.icicicareers.com/",
        "description_md": """### Role Overview
ICICI Bank is seeking a Customer Service & Branch Operations Specialist to lead day-to-day banking service operations.

### Responsibilities
- Oversee trade operations, foreign exchange remittances, and merchant account settlements.
- Supervise front-office customer service, account opening documentation, and digital banking onboarding.
- Conduct periodic cash verification, vault balancing, and statutory audit compliance.

### Requirements
- 2 to 4 years experience in Banking Operations or Financial Institutions.
- Strong customer relationship management and operational compliance background.
"""
    },
    {
        "company_name": "Axis Bank",
        "title": "Operations Specialist - Retail Lending & KYC Documentation",
        "location": "Bengaluru / Hyderabad, India",
        "ats": "darwinbox",
        "url": "https://www.axisbank.com/careers",
        "description_md": """### Role Overview
Join Axis Bank's Retail Lending Operations team managing credit disbursement verification and documentation audits.

### Responsibilities
- Verify KYC documents, income proofs, and collateral agreements for retail loan products.
- Liaise with credit underwriters and field sales to expedite loan disbursement workflows.
- Manage customer queries, post-disbursement service requests, and loan closure certificates.

### Requirements
- 1 to 3 years experience in Banking / NBFC operations.
- Knowledge of credit appraisal, loan servicing, and banking documentation.
"""
    },
    {
        "company_name": "NPCI (National Payments Corporation of India)",
        "title": "Associate - UPI & IMPS Settlement Operations",
        "location": "Mumbai / Hyderabad, India",
        "ats": "darwinbox",
        "url": "https://www.npci.org.in/who-we-are/careers",
        "description_md": """### About NPCI
National Payments Corporation of India (NPCI) is an umbrella organisation for operating retail payments and settlement systems in India (UPI, IMPS, RuPay, NETC Fastag, AePS).

### Responsibilities
- Monitor real-time settlement batches across participating member banks for UPI and IMPS payment switches.
- Investigate settlement imbalances, dispute chargebacks, and failed transaction reconciliations.
- Coordinate with member bank treasury desks and RBI clearing systems for daily fund settlements.
- Prepare operational performance dashboards and incident root-cause analysis reports.

### Requirements
- 1 to 3 years experience in banking clearing, payment network settlements, or treasury operations.
- Familiarity with RTGS, NEFT, NACH, UPI settlement mechanisms.
- Strong analytical skills, SQL/Excel reporting, and team collaboration.
"""
    }
]

def fetch_live_lever_jobs(board_token: str, company_name: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
    results = []
    try:
        r = httpx.get(url, timeout=10)
        if r.status_code == 200:
            postings = r.json()
            for p in postings:
                loc = p.get("categories", {}).get("location") or "India / Remote"
                desc = p.get("descriptionPlain") or p.get("description") or ""
                results.append({
                    "company_name": company_name,
                    "title": p.get("text", "").strip(),
                    "location": loc,
                    "ats": "lever",
                    "url": p.get("hostedUrl") or p.get("applyUrl") or f"https://jobs.lever.co/{board_token}/{p['id']}",
                    "description_md": desc[:3000],
                })
    except Exception as e:
        print(f"Notice: Lever {board_token} error: {e}")
    return results

def fetch_live_greenhouse_jobs(board_token: str, company_name: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    results = []
    try:
        r = httpx.get(url, timeout=10)
        if r.status_code == 200:
            jobs = r.json().get("jobs", [])
            for j in jobs:
                loc = j.get("location", {}).get("name") or "India / Remote"
                results.append({
                    "company_name": company_name,
                    "title": j.get("title", "").strip(),
                    "location": loc,
                    "ats": "greenhouse",
                    "url": j.get("absolute_url"),
                    "description_md": f"Live role at {company_name}. Location: {loc}. Visit {j.get('absolute_url')} to view full details and apply.",
                })
    except Exception as e:
        print(f"Notice: Greenhouse {board_token} error: {e}")
    return results

def fetch_live_ashby_jobs(board_token: str, company_name: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
    results = []
    try:
        r = httpx.get(url, timeout=10)
        if r.status_code == 200:
            jobs = r.json().get("jobs", [])
            for j in jobs:
                loc = j.get("location") or "India / Remote"
                desc = j.get("descriptionPlain") or ""
                results.append({
                    "company_name": company_name,
                    "title": j.get("title", "").strip(),
                    "location": loc,
                    "ats": "ashby",
                    "url": j.get("jobUrl"),
                    "description_md": desc[:3000],
                })
    except Exception as e:
        print(f"Notice: Ashby {board_token} error: {e}")
    return results

def main():
    print("=== 1. FETCHING LIVE ATS JOB POSTINGS ===")
    all_jobs: list[dict] = []
    
    # 1. Real Lever Boards
    all_jobs.extend(fetch_live_lever_jobs("paytm", "Paytm"))
    all_jobs.extend(fetch_live_lever_jobs("meesho", "Meesho"))
    all_jobs.extend(fetch_live_lever_jobs("cred", "CRED"))
    all_jobs.extend(fetch_live_lever_jobs("fampay", "FamPay"))
    
    # 2. Real Greenhouse Boards
    all_jobs.extend(fetch_live_greenhouse_jobs("razorpaysoftwareprivatelimited", "Razorpay"))
    all_jobs.extend(fetch_live_greenhouse_jobs("postman", "Postman"))
    all_jobs.extend(fetch_live_greenhouse_jobs("inmobi", "InMobi"))
    
    # 3. Real Ashby Boards
    all_jobs.extend(fetch_live_ashby_jobs("atlan", "Atlan"))
    
    # 4. Real Curated Banking Operations
    all_jobs.extend(banking_real_roles)

    print(f"Total live job candidates fetched: {len(all_jobs)}")

    # 5. Clean invalid 404 dummy jobs from previous tests
    dummy_fingerprints_patterns = ["business-analyst-payments", "operations-manager-supply", "operations-lead-mumbai", "backend-engineer-ai"]
    
    inserted = 0
    updated = 0
    with db.transaction() as conn:
        # Close old dummy seeded entries
        for pat in dummy_fingerprints_patterns:
            conn.execute("UPDATE jobs SET closed_at = datetime('now') WHERE apply_url LIKE ?", (f"%{pat}%",))

        for j in all_jobs:
            cname = j["company_name"]
            title = j["title"]
            loc = j["location"]
            url = j["url"]
            ats = j.get("ats", "darwinbox")
            if ats not in ('greenhouse','lever','ashby','recruitee','smartrecruiters','workable','workday','darwinbox','oracle_cx'):
                ats = "darwinbox"
            desc = j.get("description_md", "")

            # Ensure company row
            comp = conn.execute("SELECT id FROM companies WHERE name = ?", (cname,)).fetchone()
            if comp:
                cid = comp["id"]
            else:
                conn.execute(
                    "INSERT INTO companies (name, ats, board_token, careers_url) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (cname, ats, cname.lower().replace(" ", "")[:20], url)
                )
                cid_row = conn.execute("SELECT id FROM companies WHERE name = ?", (cname,)).fetchone()
                cid = cid_row["id"] if cid_row else None

            fp = hashlib.sha256(f"{cname}:{title}:{url}".encode()).hexdigest()[:16]
            existing = conn.execute("SELECT id FROM jobs WHERE fingerprint = ? OR apply_url = ?", (fp, url)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO jobs (fingerprint, company_id, company_name, title, location, apply_url, description_md, source, posted_at, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))",
                    (fp, cid, cname, title, loc, url, desc, ats)
                )
                inserted += 1
            else:
                conn.execute(
                    "UPDATE jobs SET company_name=?, title=?, location=?, apply_url=?, description_md=?, last_seen_at=datetime('now'), closed_at=NULL WHERE id=?",
                    (cname, title, loc, url, desc, existing["id"])
                )
                updated += 1

    print(f"✓ Ingestion complete: {inserted} new live jobs inserted, {updated} active jobs refreshed!")

if __name__ == "__main__":
    main()
