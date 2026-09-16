"""Generate case_study/index.html from the JSON artifacts."""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "case_study" / "index.html"


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def json_script(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def slim_rows(rows: list[dict]) -> list[dict]:
    slim = []
    for row in rows:
        slim.append(
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "one_liner": row.get("one_liner") or "",
                "auth_methods": row.get("auth_methods") or [],
                "access": row.get("access"),
                "api_type": row.get("api_type"),
                "api_breadth": row.get("api_breadth"),
                "mcp": row.get("mcp"),
                "verdict": row.get("verdict"),
                "blocker": row.get("blocker"),
                "evidence_urls": row.get("evidence_urls") or [],
                "confidence": row.get("confidence"),
                "needs_human": bool(row.get("needs_human")),
            }
        )
    return slim


def lis(items: list[str]) -> str:
    return "\n".join(f"<li>{esc(x)}</li>" for x in items)


def field_bars(by_field: dict) -> str:
    chunks = []
    for field, stats in by_field.items():
        pct = stats.get("pct", 0)
        chunks.append(
            f"""<div class="bar-row"><span>{esc(field)}</span>
            <div class="bar"><i style="width:{pct}%"></i></div>
            <b>{stats.get("hits")}/{stats.get("total")} ({pct}%)</b></div>"""
        )
    return "\n".join(chunks)


def miss_cards(misses: list[dict]) -> str:
    cards = []
    for item in misses:
        bits = "; ".join(
            f"{m['field']}: expected {m['expected']}, got {m['actual']}" for m in item.get("misses") or []
        )
        cards.append(
            f"<li><strong>{esc(item['name'])}</strong> (id {item['id']}) — {esc(bits)}</li>"
        )
    return "\n".join(cards) if cards else "<li>None.</li>"


def unique(values: list[str]) -> list[str]:
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def options(values: list[str], extra: str = "all") -> str:
    bits = [f'<option value="{esc(extra)}">All {esc(extra) if extra != "all" else "values"}</option>']
    if extra == "all":
        bits = ['<option value="all">All</option>']
    for value in values:
        bits.append(f'<option value="{esc(value)}">{esc(value)}</option>')
    return "\n".join(bits)


def main() -> None:
    rows = load("results.json")
    insights = load("insights.json")
    summary = load("verification_summary.json")
    if len(rows) != 100:
        raise SystemExit(f"expected 100 rows, got {len(rows)}")

    categories = unique([r["category"] for r in rows])
    auths = unique(
        [m for r in rows for m in (r.get("auth_methods") or [])]
    )
    accesses = unique([r["access"] for r in rows])
    verdicts = unique([r["verdict"] for r in rows])
    blocked = [r for r in rows if r["verdict"] == "blocked"]
    possible = [r for r in rows if r["verdict"] == "possible_with_work"]
    human = [r for r in rows if r.get("needs_human")]
    verd = insights["verdicts"]["counts"]
    mcp = insights["mcp"]
    access = insights["access"]
    headlines = insights["headlines"]

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>100 apps as agent toolkits — Composio research</title>
<style>
:root {{
  --ink: #1c1917;
  --muted: #57534e;
  --line: #e7e5e4;
  --paper: #faf7f2;
  --card: #ffffff;
  --accent: #0f766e;
  --warn: #b45309;
  --bad: #b91c1c;
  --ok: #047857;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  font: 16px/1.5 "Iowan Old Style", Palatino, "Palatino Linotype", Georgia, serif;
  color: var(--ink);
  background: var(--paper);
}}
header, main, footer {{ max-width: 1120px; margin: 0 auto; padding: 0 20px; }}
header {{ padding-top: 36px; padding-bottom: 12px; }}
h1 {{ font-size: 2rem; line-height: 1.2; margin: 0 0 8px; }}
.lede {{ color: var(--muted); max-width: 62ch; }}
nav {{
  position: sticky; top: 0; z-index: 5;
  background: var(--paper);
  border-bottom: 1px solid var(--line);
}}
nav .wrap {{ max-width: 1120px; margin: 0 auto; padding: 10px 20px; display: flex; gap: 14px; flex-wrap: wrap; }}
nav a {{ color: var(--muted); text-decoration: none; font: 13px/1.2 ui-sans-serif, system-ui, sans-serif; }}
nav a:hover {{ color: var(--ink); }}
section {{ padding: 36px 0 12px; scroll-margin-top: 56px; }}
h2 {{ font-size: 1.25rem; margin: 0 0 12px; }}
h3 {{ font-size: 1rem; margin: 18px 0 8px; }}
ol.findings {{ padding-left: 1.2em; }}
ol.findings li {{ margin: 0 0 10px; max-width: 78ch; }}
p {{ max-width: 72ch; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }}
.stat {{ background: var(--card); border: 1px solid var(--line); padding: 14px 16px; border-radius: 10px; }}
.stat b {{ display: block; font-size: 1.6rem; font-family: ui-sans-serif, system-ui, sans-serif; }}
.stat span {{ color: var(--muted); font: 12px/1.3 ui-sans-serif, system-ui, sans-serif; }}
.filters {{
  display: flex; flex-wrap: wrap; gap: 10px; align-items: end;
  font-family: ui-sans-serif, system-ui, sans-serif; font-size: 13px;
  margin: 12px 0;
}}
.filters label {{ display: flex; flex-direction: column; gap: 4px; color: var(--muted); }}
select, input[type="search"] {{
  font: 13px/1.2 ui-sans-serif, system-ui, sans-serif;
  padding: 6px 8px; border: 1px solid var(--line); border-radius: 8px; background: #fff;
}}
.table-wrap {{ overflow: auto; border: 1px solid var(--line); border-radius: 10px; background: #fff; }}
table {{ border-collapse: collapse; width: 100%; font: 13px/1.35 ui-sans-serif, system-ui, sans-serif; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; white-space: nowrap; }}
th {{ position: sticky; top: 0; background: #f5f5f4; z-index: 1; }}
td.name, td.one {{ white-space: normal; min-width: 140px; }}
.pill {{
  display: inline-block; padding: 1px 7px; border-radius: 999px;
  background: #f5f5f4; font-size: 11px; margin: 0 2px 2px 0;
}}
.v-toolkit_today {{ background: #d1fae5; color: #065f46; }}
.v-possible_with_work {{ background: #fef3c7; color: #92400e; }}
.v-blocked {{ background: #fee2e2; color: #991b1b; }}
a {{ color: var(--accent); }}
pre {{
  background: #1c1917; color: #f5f5f4; padding: 14px 16px; border-radius: 10px;
  overflow: auto; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
.bar-row {{ display: grid; grid-template-columns: 140px 1fr auto; gap: 8px; align-items: center; font: 13px ui-sans-serif, system-ui, sans-serif; margin: 6px 0; }}
.bar {{ height: 8px; background: #e7e5e4; border-radius: 99px; overflow: hidden; }}
.bar i {{ display: block; height: 100%; background: var(--accent); }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
@media (max-width: 800px) {{ .two {{ grid-template-columns: 1fr; }} h1 {{ font-size: 1.55rem; }} }}
ul.plain {{ padding-left: 1.2em; }}
footer {{ color: var(--muted); font-size: 13px; padding: 28px 20px 48px; }}
.note {{ color: var(--muted); font-size: 14px; }}
</style>
</head>
<body>
<header>
  <h1>Most of these 100 apps can be an agent toolkit today. The rest fail on review, paywalls, or no API.</h1>
  <p class="lede">Composio web search + fetch, then a Groq JSON extract against a fixed schema. The matrix below is generated from <code>data/results.json</code> — it cannot drift from the agent table.</p>
</header>
<nav><div class="wrap">
  <a href="#findings">Findings</a>
  <a href="#read">How to read</a>
  <a href="#matrix">Matrix</a>
  <a href="#agent">Agent</a>
  <a href="#proof">Proof</a>
  <a href="#verification">Verification</a>
  <a href="#limits">Limits</a>
</div></nav>
<main>
<section id="findings">
  <h2>Headline findings</h2>
  <div class="grid">
    <div class="stat"><b>{verd.get("toolkit_today", 0)}</b><span>toolkit today</span></div>
    <div class="stat"><b>{verd.get("possible_with_work", 0)}</b><span>possible with work</span></div>
    <div class="stat"><b>{verd.get("blocked", 0)}</b><span>blocked</span></div>
    <div class="stat"><b>{mcp.get("official", 0)}</b><span>official MCP</span></div>
    <div class="stat"><b>{access.get("self_serve_or_trial", 0)}</b><span>self-serve or trial</span></div>
    <div class="stat"><b>{summary.get("pass2_pct")}%</b><span>sample accuracy after re-run</span></div>
  </div>
  <ol class="findings">
    {lis(headlines)}
  </ol>
</section>

<section id="read">
  <h2>How to read this</h2>
  <p>An agent searched public docs with Composio (<code>COMPOSIO_SEARCH_WEB</code>, <code>COMPOSIO_SEARCH_FETCH_URL_CONTENT</code>), then filled one JSON row per app. A human scored a stratified sample of 20 (two per category) against vendor pages, then re-ran extract-only on misses. Treat <span class="pill v-toolkit_today">toolkit_today</span> as “a developer can get creds and call an API or official MCP without a partnership wait.” <span class="pill v-possible_with_work">possible_with_work</span> means an API exists but review or a paid plan sits in front. <span class="pill v-blocked">blocked</span> means no usable public API for this product. Paid logins were skipped on purpose.</p>
</section>

<section id="matrix">
  <h2>Skimmable matrix of 100</h2>
  <p class="note" id="shown">Showing 100 of 100</p>
  <div class="filters">
    <label>Search <input id="q" type="search" placeholder="name…"></label>
    <label>Category <select id="f-cat">{options(categories)}</select></label>
    <label>Auth <select id="f-auth">{options(auths)}</select></label>
    <label>Access <select id="f-access">{options(accesses)}</select></label>
    <label>Verdict <select id="f-verdict">{options(verdicts)}</select></label>
  </div>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th><th>App</th><th>Category</th><th>Auth</th><th>Access</th>
          <th>API</th><th>MCP</th><th>Verdict</th><th>Evidence</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</section>

<section id="agent">
  <h2>Agent</h2>
  <p>Composio ran a web search per app, fetched the top vendor/doc URLs, packed snippets, and a Groq model (Qwen 3.8 27B / gpt-oss-20b, sharded to stay under free-tier caps) returned one schema row. Cache lives in <code>cache/&lt;id&gt;/</code> so research is not repeated. A second pass was extract-only on failed sample rows after prompt rules for vendor-domain MCP, paid vs self-serve, and sibling-product APIs.</p>
  <h3>Where a human was required</h3>
  <ul class="plain">
    {lis(summary.get("human_needed") or [])}
    <li>Rows the agent marked needs_human: {esc(", ".join(r["name"] for r in human) or "none")}.</li>
  </ul>
</section>

<section id="proof">
  <h2>Proof</h2>
  <p>Reproduce from a clone with <code>COMPOSIO_API_KEY</code> (Write All) and <code>GROQ_API_KEY</code> in <code>.env</code>. Do not re-run <code>--all</code> unless you intend to spend the daily token budget again.</p>
<pre>python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python src/research_agent.py --ids 1,11,21,31,41,51,61,71,81,91
python src/research_agent.py --compare-gold
python src/verify.py --auto
python src/verify.py --sample 20
python src/analyze.py
python src/build_page.py</pre>
  <p class="note">Live page: <a href="https://composio-toolkit-research-six.vercel.app">https://composio-toolkit-research-six.vercel.app</a>. Source: <a href="https://github.com/ishrath07/composio-toolkit-research">github.com/ishrath07/composio-toolkit-research</a>.</p>
</section>

<section id="verification">
  <h2>Verification</h2>
  <p><strong>{esc(summary.get("headline"))}</strong> Auto-check: {summary.get("auto_n_rows")} rows, {summary.get("auto_flagged")} flagged, schema + contradiction rules.</p>
  <div class="two">
    <div>
      <h3>Pass-1 field hit rate</h3>
      {field_bars(summary.get("pass1_by_field") or {{}})}
    </div>
    <div>
      <h3>Pass-2 field hit rate</h3>
      {field_bars(summary.get("pass2_by_field") or {{}})}
    </div>
  </div>
  <h3>Named misses after re-run</h3>
  <ul class="plain">
    {miss_cards(summary.get("honest_misses_after_pass2") or [])}
  </ul>
</section>

<section id="limits">
  <h2>Limits — said plainly</h2>
  <p>The agent can still confuse sibling products (Mailchimp Marketing REST vs Open Commerce GraphQL) and over-call MCP (Gumroad). It labeled Ahrefs self-serve/broad instead of paid/medium. Breadth (Otter) is judgment, not a hard fact.</p>
  <h3>Blocked ({len(blocked)})</h3>
  <ul class="plain">
    {lis([f"{r['name']}: {r.get('blocker') or r['access'] + ' / ' + r['api_type']}" for r in blocked])}
  </ul>
  <h3>Outreach / possible with work ({len(possible)})</h3>
  <ul class="plain">
    {lis([f"{r['name']}: {r.get('blocker') or r['access']}" for r in possible])}
  </ul>
  <p class="note">JS-only or login-walled docs were not opened as a user. Confidence is the model’s, not a measured probability. MCP “official” means vendor-domain docs in the fetch pack, which can lag a product launch by days.</p>
</section>
</main>
<footer>Generated by <code>python src/build_page.py</code> from data/results.json, data/insights.json, and data/verification_summary.json.</footer>
<script>
const ROWS = {json_script(slim_rows(rows))};
const tbody = document.getElementById("tbody");
const shown = document.getElementById("shown");
const filters = {{
  q: document.getElementById("q"),
  cat: document.getElementById("f-cat"),
  auth: document.getElementById("f-auth"),
  access: document.getElementById("f-access"),
  verdict: document.getElementById("f-verdict"),
}};

function pills(list) {{
  return (list || []).map(x => `<span class="pill">${{x}}</span>`).join("");
}}

function render() {{
  const q = filters.q.value.trim().toLowerCase();
  const cat = filters.cat.value;
  const auth = filters.auth.value;
  const access = filters.access.value;
  const verdict = filters.verdict.value;
  const out = ROWS.filter(r => {{
    if (q && !(`${{r.name}} ${{r.id}}`).toLowerCase().includes(q)) return false;
    if (cat !== "all" && r.category !== cat) return false;
    if (auth !== "all" && !(r.auth_methods || []).includes(auth)) return false;
    if (access !== "all" && r.access !== access) return false;
    if (verdict !== "all" && r.verdict !== verdict) return false;
    return true;
  }});
  shown.textContent = `Showing ${{out.length}} of ${{ROWS.length}}`;
  tbody.innerHTML = out.map(r => {{
    const ev = (r.evidence_urls || [])[0];
    const title = [r.one_liner, r.blocker ? ("Blocker: " + r.blocker) : ""].filter(Boolean).join(" ");
    return `<tr title="${{String(title).replaceAll('"', "&quot;")}}">
      <td>${{r.id}}</td>
      <td class="name"><strong>${{r.name}}</strong></td>
      <td class="one">${{r.category}}</td>
      <td>${{pills(r.auth_methods)}}</td>
      <td>${{r.access}}</td>
      <td>${{r.api_type}} / ${{r.api_breadth}}</td>
      <td>${{r.mcp}}</td>
      <td><span class="pill v-${{r.verdict}}">${{r.verdict}}</span></td>
      <td>${{ev ? `<a href="${{ev}}" target="_blank" rel="noopener">docs</a>` : "—"}}</td>
    </tr>`;
  }}).join("");
}}
Object.values(filters).forEach(el => el.addEventListener("input", render));
render();
</script>
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
