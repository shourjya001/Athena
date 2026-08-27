# Athena (Trackboard) — Friend's Guide & Onboarding

Welcome to **Athena** (Trackboard)! This platform is your personal, private career departure board and pattern-first Data Structures & Algorithms (DSA) training engine. It replaces scattered job spreadsheets, unorganized LeetCode grinding, and generic resume tailoring with an integrated, intelligent workflow.

---

## 1. Access & Logging In

1. Open the app link provided by Shourjya.
2. If you are not signed in, go to `/login` (or click your profile icon in the top right corner).
3. **Select or enter your email address**:
   - Your email address must be included in the authorized allowlist (`ALLOWED_EMAILS`). If you see an access error, reach out to Shourjya so he can add your email.
4. Once selected, your session is saved in a secure 30-day cookie. All your applications, resume tailoring, and practice data are strictly isolated to your own user account.

---

## 2. Setting Up Your Profile (First 5 Minutes)

To get targeted job recommendations matched against your experience:
- **Target Titles**: e.g., `Backend Engineer`, `Software Engineer`, `Senior Software Engineer`, `Full Stack Developer`.
- **Target Locations**: e.g., `Bengaluru`, `Mumbai`, `Remote`, `India`.
- **Minimum CTC / Experience Level**: Set your target compensation and years of experience.
- **Skills & Frameworks**: Add your primary languages (Python, Go, Java, TypeScript, etc.) and systems (FastAPI, Docker, Kafka, AWS, Postgres, Redis).

---

## 3. Resume Tailoring with the 5-Pillar Lead Recruiter Audit

Applying with a generic resume leads to automatic ATS rejections. Athena includes a **Lead Recruiter Tailor Engine** modeled after top tech recruiters:

1. Go to `/jobs` to view jobs curated specifically for your profile with BM25 keyword matching and fit scoring.
2. Click **Tailor** on any job to launch the deep audit (`/jobs/{id}/tailor`).
3. The engine simulates a 10-second hiring manager review across 5 critical pillars:
   - **10-Second Attention Test**: Identifies your standout proof points and flags forgettable filler.
   - **Recruiter Mindset Breakdown**: Reveals how a recruiter at that specific company views your candidacy and what signals credibility.
   - **ATS Visibility Engine**: Extracts must-have keywords from the job description and recommends natural placements (no keyword stuffing).
   - **Impact Statement Rebuilder**: Transforms passive bullets into high-impact `[Action Verb] + [Context] + [Measurable Metric]` statements.
   - **Market Positioning Rewrite**: Customizes your professional summary and headline for the company's culture (e.g. High-concurrency Fintech vs. Fast-paced AI Tech).
4. Select the best bullets from your bullet bank and export an ATS-compliant, single-page tailored PDF.

---

## 4. Pattern-First DSA Mastery with Interactive Dry-Run Canvases

Instead of memorizing hundreds of disconnected LeetCode solutions, Athena teaches **26 universal coding patterns** that cover 95%+ of tech interview problems.

Visit `/patterns` to explore the catalog, or open any pattern page (e.g., `/patterns/linked-list-reversal`, `/patterns/dp-knapsack`, `/patterns/two-pointers`, `/patterns/union-find`):

### The Interactive Execution Workbench
- **Line-by-Line Stepper**: Use `Next ▶` and `◀ Prev` to step through Python implementations line by line.
- **Active Frame Variables**: Watch local variables, pointers, and calculation states update dynamically in real time.
- **Custom Visual Canvases**:
  - **Linked Lists**: Watch nodes flip pointers (`🠔`) in memory with `prev`, `curr`, and `nxt` tracking.
  - **Dynamic Programming (DP)**: Interactive 2D/1D memoization tables displaying exact cell formulas (`max(skip, take + val) = 12`) and dependencies.
  - **Backtracking**: Live state path buffers showing `CHOOSE` and `UNDO (BACKTRACK: path.pop())` decision tree branches.
  - **Graphs & Trees**: Visual networks showing FIFO Queue state, Visited sets, and in-order recursion traversal.
  - **Topological Sort**: Kahn's algorithm with real-time in-degree updates and sequencing.
  - **Shortest Path (Dijkstra)**: Min-Heap priority queue ordering and edge relaxation.
  - **Bit Manipulation**: 8-bit registers highlighting cleared bits and single-cycle power-of-two tests.
- **Whiteboard Mentor (Claude)**: Plain-English, conversational explanations that explain *why* each line of code exists.

---

## 5. Spaced Repetition Practice & LeetCode Sync

1. **Daily Practice Queue (`/practice`)**:
   - When you solve or review a problem, record your outcome (`Solved`, `Attempted`, `Blocked`) and your confidence level (1 to 5).
   - Athena uses the SuperMemo-2 (SM-2) spaced repetition algorithm to schedule future reviews right before you are likely to forget the pattern.
2. **Rapid Drill (`/drill`)**:
   - Practice pattern recognition in under 10 seconds. You are presented with a problem prompt and 4 possible patterns to test your instant intuition.
3. **LeetCode Sync**:
   - Provide your public LeetCode username in your profile settings.
   - The automated sync agent checks your recent accepted submissions and automatically checks off completed problems in your queue.

---

## 6. Daily 9:00 PM Digest Email

Every evening at 9:00 PM IST, you will receive a clean, rich HTML briefing in your inbox containing:
- Top 3 fresh job recommendations matching your profile.
- Practice problems scheduled for review tomorrow.
- Updates on applications currently in your pipeline.

---

## Need Help or Want to Add a Feature?
Ping **Shourjya** to update your allowed email, refresh ATS job sources, or suggest new problem patterns!
