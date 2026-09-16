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

- `COMPOSIO_API_KEY` — from the Composio dashboard
- `GEMINI_API_KEY` — from Google AI Studio (this project uses Gemini, not OpenAI)

## Commands

```powershell
python src/research_agent.py --ids 1,11,21,31,41,51,61,71,81,91
python src/research_agent.py --compare-gold
python src/research_agent.py --all
python src/verify.py --auto
python src/verify.py --sample 20
python src/analyze.py
python src/build_page.py
```

`--ids` / `--all` resume from `cache/<id>/` and `data/results.json`. Use `--force` to research again.

Phase 2 agent: Composio `COMPOSIO_SEARCH_WEB` + `COMPOSIO_SEARCH_FETCH_URL_CONTENT`, then Gemini fills `data/schema.json`.

## Layout

- `data/apps.json` — 100 apps (source of truth for the run)
- `data/schema.json` — one research row
- `data/results.json` — agent output (Phase 2)
- `data/verification.json` — accuracy sample (Phase 3)
- `data/insights.json` — pattern headlines (Phase 4)
- `case_study/index.html` — reviewer page (Phase 5)
