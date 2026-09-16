# Composio toolkit research (take-home)

Research agent for 100 apps: auth, self-serve vs gated, API/MCP surface, and buildability. Output is a single HTML case study.

## Setup

```powershell
cd C:\Users\ASUS\OneDrive\Desktop\takeaway_assgnmt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Put real keys in `.env` (never commit it):

- `COMPOSIO_API_KEY`
- `OPENAI_API_KEY` (or another LLM key listed in `.env.example`)

## Commands (later phases)

```powershell
python src/research_agent.py --limit 10 --ids 1,11,21,31,41,51,61,71,81,91
python src/research_agent.py --all
python src/verify.py --auto
python src/verify.py --sample 20
python src/analyze.py
python src/build_page.py
```

Phase 1 only seeded `data/apps.json` and `data/schema.json`. Scripts print `not implemented` until their phase.

## Layout

- `data/apps.json` — 100 apps (source of truth for the run)
- `data/schema.json` — one research row
- `data/results.json` — agent output (Phase 2)
- `data/verification.json` — accuracy sample (Phase 3)
- `data/insights.json` — pattern headlines (Phase 4)
- `case_study/index.html` — reviewer page (Phase 5)
