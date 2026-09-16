# Composio toolkit research (take-home)

Can these 100 apps be AI-agent toolkits? A Composio research agent filled one schema row per app (auth, access, API, MCP, verdict). A human sample of 20 is the accuracy check. The case study is generated from that JSON so the page cannot drift from the table.

**Case study (open this first):** [live page](https://composio-toolkit-research-six.vercel.app) · [source HTML](case_study/index.html)

**Accuracy:** stratified sample of 20 (2 per category), 120 fields: **74.2% → 95.8%** after prompt fixes and extract-only re-run. Auto-check on 100 rows: 0 schema/contradiction flags. Remaining misses: Mailchimp `api_type`, Gumroad `mcp`, Ahrefs `access`/`api_breadth`, Otter `api_breadth`.

## What the table says

- **90/100** toolkit-today; **72** already have self-serve creds plus official MCP.
- **OAuth2** on 78/100; universal in CRM and productivity. Scraping/SEO is the API-key pocket.
- **89/100** self-serve. Gating sits in ads (Google/Meta/LinkedIn/Threads) and finance (Plaid, PitchBook).
- Official MCP on **80/100**. MCP-missing cluster is consumer messaging (Discord, Telegram, WhatsApp), not meeting-note apps.
- Hard blockers are admin/app-review, paid data APIs, partnership (Salesforce Commerce Cloud), and no public API (Sherlock, NotebookLM).

## How the agent works

1. Composio `COMPOSIO_SEARCH_WEB` + `COMPOSIO_SEARCH_FETCH_URL_CONTENT` (skip paid logins).
2. Groq JSON extract against [`data/schema.json`](data/schema.json) (free tier; models sharded).
3. Resume from `cache/<id>/` and [`data/results.json`](data/results.json).

This repo already contains the finished 100-row table. **Do not run `--all` unless you intend to spend Composio/Groq quota.** Use `--ids` for a smoke test.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

On macOS/Linux: `python3 -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`.

Put keys in `.env` (never commit it):

- `COMPOSIO_API_KEY` — dashboard, **Write All**
- `GROQ_API_KEY` — [console.groq.com/keys](https://console.groq.com/keys)
- `LLM_PROVIDER=groq`
- `GROQ_MODELS=qwen/qwen3.8-27b,openai/gpt-oss-20b,openai/gpt-oss-safeguard-20b`

## Commands

```powershell
python src/research_agent.py --ids 1,11,21,31,41,51,61,71,81,91
python src/research_agent.py --compare-gold
python src/verify.py --auto
python src/verify.py --sample 20
python src/analyze.py
python src/build_page.py
```

`--force` re-researches an id. `--all` rebuilds every row. `python src/build_page.py` regenerates the HTML from `data/results.json`, `data/insights.json`, and `data/verification_summary.json`.

## Layout

- `data/apps.json` — 100 apps
- `data/results.json` — agent table
- `data/sample20.json` / `data/verification.json` — human sample
- `data/insights.json` — pattern headlines
- `src/research_agent.py` — Composio + Groq
- `case_study/index.html` — reviewer page
