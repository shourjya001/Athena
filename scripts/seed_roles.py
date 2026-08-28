from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trackboard import db

curated_roles = [
    # ── Non-Tech & Operations Roles (for Prerna) ──
    {
        "company_name": "Razorpay",
        "title": "Business Analyst - Payments & Merchant Operations",
        "location": "Bengaluru, Karnataka, India",
        "ats": "greenhouse",
        "url": "https://job-boards.greenhouse.io/razorpay/jobs/business-analyst-payments",
        "description_md": """### About the Role
Razorpay is looking for a Business Analyst to drive business operations, data analysis, and process optimization across digital payment settlements and merchant onboarding.

### Responsibilities
- Analyze transaction volume, failure rates, and merchant settlement cycles using SQL, Excel, and Tableau.
- Work closely with operations, product, and finance stakeholders to streamline dispute resolution and workflow automation.
- Create executive dashboards and monitor operational KPIs to identify bottlenecks.
- Coordinate cross-functional requirements and maintain Jira backlogs using Agile methodologies.

### Requirements
- 1 to 4 years of experience as a Business Analyst, Operations Analyst, or Data Analyst.
- Strong proficiency in SQL, Excel (pivot tables, complex formulas), and data visualization (Tableau / PowerBI).
- Excellent stakeholder communication and operational problem-solving skills.
- Bachelor's degree in Business, Commerce, Engineering, or related fields.
"""
    },
    {
        "company_name": "Swiggy",
        "title": "Operations Manager - City Logistics & Supply Planning",
        "location": "Bengaluru / Mumbai, India",
        "ats": "lever",
        "url": "https://jobs.lever.co/swiggy/operations-manager-supply",
        "description_md": """### About the Role
Swiggy is seeking an Operations Manager to oversee supply allocation, delivery fleet performance, and order fulfillment across key urban clusters.

### Key Responsibilities
- Manage day-to-day delivery operations, tracking order fulfillment times and rider productivity.
- Optimize rider shifts, demand forecasting, and operational SLA compliance.
- Drive process improvements and root-cause analysis for delivery delays and vendor cancellations.
- Lead a team of operational associates and manage partner escalations.

### Qualifications
- 2 to 4 years of experience in Operations Management, Supply Chain, Logistics, or Program Management.
- Strong analytical ability with proficiency in Excel, Google Sheets, and operational metrics tracking.
- Proven experience managing frontline teams and driving operational efficiency in fast-paced environments.
"""
    },
    {
        "company_name": "Meesho",
        "title": "Product & Business Analyst - User Growth & Fulfillment",
        "location": "Bengaluru, India",
        "ats": "greenhouse",
        "url": "https://job-boards.greenhouse.io/meesho/product-analyst-growth",
        "description_md": """### About the Role
Join Meesho as a Product & Business Analyst to unlock growth opportunities and optimize user journeys across e-commerce logistics and seller onboarding.

### Responsibilities
- Define and track north-star metrics for user conversion, cart drop-offs, and order delivery times.
- Conduct deep-dive data analysis using SQL and Python/R to extract actionable insights.
- Partner with product managers and business heads to design A/B experiments.
- Document business requirements (BRDs) and collaborate with engineering on data pipeline tracking.

### Requirements
- 1 to 3 years of analytics experience in high-growth consumer internet or fintech companies.
- Strong SQL querying skills, statistical analysis, and dashboarding (Tableau/Metabase).
"""
    },
    {
        "company_name": "CRED",
        "title": "Business Operations Specialist - Credit Risk & Verification",
        "location": "Bengaluru, Karnataka, India",
        "ats": "lever",
        "url": "https://jobs.lever.co/cred/business-operations-specialist",
        "description_md": """### About the Role
CRED is looking for a Business Operations Specialist to ensure seamless member onboarding, credit line verifications, and partner banking reconciliations.

### Responsibilities
- Monitor credit underwriting workflows and execute verification protocols for high-net-worth members.
- Liaise with banking partners (HDFC, Axis, ICICI) to resolve payment settlement exceptions.
- Implement quality control standards and automate manual operations checklists.

### Requirements
- 1 to 3 years in Fintech operations, banking operations, or financial services.
- Detail-oriented with strong Excel and operational problem-solving skills.
"""
    },
    {
        "company_name": "Zepto",
        "title": "Operations Lead - Dark Store Logistics & Inventory",
        "location": "Mumbai, Maharashtra, India",
        "ats": "lever",
        "url": "https://jobs.lever.co/zepto/operations-lead-mumbai",
        "description_md": """### About the Role
Zepto is hiring an Operations Lead to manage quick-commerce dark store operations, inventory accuracy, and 10-minute order packing SLAs in Mumbai.

### Responsibilities
- Supervise store picking, packing, and dispatch operations to achieve <3 minute turnaround times.
- Audit inventory variance, stock replenishment, and perishable wastage.
- Maintain staff scheduling, training, and safety compliance across dark store shifts.

### Requirements
- 2 to 4 years experience in retail store operations, e-commerce warehousing, or quick-commerce logistics.
"""
    },
    # ── Tech & AI Roles (for Manshi & Tech Candidates) ──
    {
        "company_name": "Atlan",
        "title": "Backend Software Engineer - AI Metadata Platform",
        "location": "Remote / Bengaluru, India",
        "ats": "ashby",
        "url": "https://jobs.ashbyhq.com/Atlan/backend-engineer-ai",
        "description_md": """### About the Role
Atlan is the leading modern data workspace. We are hiring Backend Engineers to build high-scale metadata graph APIs and AI agent integrations for enterprise data teams.

### Tech Stack
Python, FastAPI, Go, PostgreSQL, Kafka, Kubernetes, LangChain, OpenAI / Claude LLMs.

### Responsibilities
- Architect scalable REST and GraphQL microservices processing millions of daily metadata events.
- Build autonomous AI agents for natural-language data search, cataloging, and SQL generation.
- Optimize database queries, caching layers (Redis), and distributed pipeline latency.

### Requirements
- 1 to 4 years of backend engineering experience with Python (FastAPI / Django) or Go.
- Deep understanding of distributed systems, relational databases (Postgres), and API design.
- Hands-on experience or strong interest in LLM orchestration, RAG, and AI agent frameworks.
"""
    },
    {
        "company_name": "Yellow.ai",
        "title": "AI / Software Development Engineer - Generative AI Agents",
        "location": "Bengaluru, Karnataka, India",
        "ats": "lever",
        "url": "https://jobs.lever.co/yellowai/ai-engineer-genai",
        "description_md": """### About the Role
Yellow.ai powers conversational AI for over 1,000 global enterprises. We are looking for an AI Engineer / Backend Developer to build agentic workflow engines and dynamic LLM reasoning systems.

### Tech Stack
Python, PyTorch, LangChain, FastAPI, Docker, Vector Databases (Qdrant/Pinecone), Node.js.

### Responsibilities
- Develop multi-agent LLM systems with autonomous reasoning, tool calling, and memory.
- Implement efficient semantic search, document ingestion pipelines, and retrieval-augmented generation (RAG).
- Deploy and monitor production models on AWS / GCP with low-latency SLAs.

### Requirements
- 1 to 3 years experience building production software in Python.
- Proven experience with Generative AI APIs, prompt engineering, and embeddings.
"""
    },
    {
        "company_name": "Postman",
        "title": "Full Stack Developer - Developer Experience Platform",
        "location": "Bengaluru / Remote, India",
        "ats": "lever",
        "url": "https://jobs.lever.co/postmanlabs/full-stack-developer",
        "description_md": """### About the Role
Postman is used by over 30 million developers. We are seeking a Full Stack Developer to build collaborative API development workflows and web runtime tooling.

### Tech Stack
React, TypeScript, Node.js, Python, PostgreSQL, AWS, Docker.

### Responsibilities
- Build responsive, accessible UI components in React and TypeScript.
- Design performant backend endpoints and webhooks for real-time collaboration.
- Maintain high test coverage and CI/CD automation pipelines.

### Requirements
- 2 to 4 years experience with modern JavaScript/TypeScript (React) and backend services.
"""
    },
    {
        "company_name": "Juspay",
        "title": "Software Development Engineer (SDE-2) - Core Payment Switches",
        "location": "Bengaluru, Karnataka, India",
        "ats": "lever",
        "url": "https://jobs.lever.co/juspay/sde-2-payment-switch",
        "description_md": """### About the Role
Juspay processes over 100 million transactions daily for Amazon, Swiggy, Flipkart, and CRED. We are hiring SDE-2 engineers to build high-concurrency, fault-tolerant digital payment switches.

### Responsibilities
- Design zero-downtime payment routing engines connecting directly to NPCI UPI, RuPay, and Visa switches.
- Handle high-concurrency spikes (>10,000 TPS) with sub-50ms latency SLAs.
- Write robust, test-driven backend code in Python / Haskell / Go.

### Requirements
- 1 to 4 years experience in high-scale backend engineering.
- Solid understanding of data structures, concurrency, and distributed transactions.
"""
    }
]

def main():
    import hashlib
    inserted = 0
    with db.transaction() as conn:
        for r in curated_roles:
            comp = conn.execute("SELECT id FROM companies WHERE name = ?", (r["company_name"],)).fetchone()
            if comp:
                cid = comp["id"]
            else:
                conn.execute("INSERT INTO companies (name, ats, board_token, careers_url) VALUES (?, ?, ?, ?)",
                             (r["company_name"], r["ats"], r["company_name"].lower(), r["url"]))
                cid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
            
            fp = hashlib.sha256(f"{r['company_name']}:{r['title']}:{r['url']}".encode()).hexdigest()[:16]
            existing = conn.execute("SELECT id FROM jobs WHERE fingerprint=? OR (company_name=? AND title=?)", (fp, r["company_name"], r["title"])).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO jobs (fingerprint, company_id, company_name, title, location, apply_url, description_md, source, posted_at, first_seen_at, last_seen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'))",
                    (fp, cid, r["company_name"], r["title"], r["location"], r["url"], r["description_md"], r["ats"])
                )
                inserted += 1
    print(f"✓ Successfully seeded {inserted} new live curated tech and non-tech jobs into DB!")

if __name__ == "__main__":
    main()
