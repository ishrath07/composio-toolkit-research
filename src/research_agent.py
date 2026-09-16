"""Research 100 apps with Composio search/fetch + Gemini JSON extract."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "cache"
APPS_PATH = DATA / "apps.json"
SCHEMA_PATH = DATA / "schema.json"
RESULTS_PATH = DATA / "results.json"
GOLD_PATH = DATA / "gold10.json"
USER_ID = "takeaway-researcher"
COMPARE_FIELDS = (
    "auth_methods",
    "access",
    "api_type",
    "api_breadth",
    "mcp",
    "verdict",
)

load_dotenv(ROOT / ".env")

SYSTEM_RULES = """
You research whether THIS named app can be an AI-agent toolkit.
Use ONLY the provided search snippets and page text. Prefer unknown over a guess.
Do not mix in a sibling product (Gemini is not NotebookLM; Salesforce MCP docs are not Zendesk).
Skip paid logins. Gated credentials are a finding, not a failure.

Field rules:
- auth_methods: JSON array only, e.g. ["oauth2"] never the string "oauth2".
  Values: oauth2, api_key, basic, token, other, unknown.
  token = personal/API tokens that are not OAuth.
- access:
  self_serve = a developer can create API creds by signing up, no sales call.
  trial = free trial creds.
  paid = signup is open but you must pay or buy credits before useful API use.
  admin = extra approval after signup (e.g. Google Ads developer token).
  partner_gated = partnership, contact-sales, or invite-only to get any API.
  Shopify Partner / custom-app signup is self_serve, not partner_gated.
- api_type: rest, graphql, rest_and_graphql, none, unknown.
  Use rest_and_graphql if both are documented.
- api_breadth: broad = large public API (CRM, ads, GitHub, Stripe-like).
  narrow = a handful of endpoints. Salesforce, Google Ads, GitHub, Stripe are broad.
- mcp: official only if THIS vendor documents an MCP server for THIS product.
  community = third-party. none = no MCP found. Do not count Gemini CLI as NotebookLM MCP.
- verdict: toolkit_today = documented API AND creds a dev can obtain without partnership wait.
  possible_with_work = API exists but approval/token review is required.
  blocked = no usable public API for this product.
- blocker: short string or null.
- evidence_urls: URLs from the pack. At least one.
- one_liner: one sentence on what the app does.
- confidence: 0 to 1. needs_human: true if thin/contradictory docs.
Return a JSON object only. No markdown.
""".strip()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cache_dir(app_id: int) -> Path:
    path = CACHE / str(app_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_ids(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def select_apps(apps: list[dict], ids: list[int] | None, limit: int, run_all: bool) -> list[dict]:
    if ids:
        wanted = set(ids)
        selected = [app for app in apps if app["id"] in wanted]
        missing = wanted - {app["id"] for app in selected}
        if missing:
            raise SystemExit(f"Unknown app ids: {sorted(missing)}")
        return selected
    if run_all:
        return apps
    if limit:
        return apps[:limit]
    raise SystemExit("Pass --all, --ids, --limit, or --compare-gold")


def provider_name() -> str:
    return (os.getenv("LLM_PROVIDER") or "gemini").strip().lower()


def default_model() -> str:
    return {
        "groq": "openai/gpt-oss-120b",
        "gemini": "gemini-2.5-flash-lite",
    }.get(provider_name(), "llama-3.3-70b-versatile")


def require_llm_keys() -> None:
    name = provider_name()
    if name == "groq":
        if not (os.getenv("GROQ_API_KEY") or "").strip():
            raise SystemExit("GROQ_API_KEY is missing in .env")
        return
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip():
        raise SystemExit("GEMINI_API_KEY is missing in .env")


def composio_client():
    from composio import Composio

    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        raise SystemExit("COMPOSIO_API_KEY is missing in .env")
    return Composio(api_key=api_key)


def generate_json(prompt: str) -> str:
    name = provider_name()
    model = os.getenv("LLM_MODEL") or default_model()
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            if name == "groq":
                from openai import OpenAI

                response = OpenAI(
                    api_key=os.environ["GROQ_API_KEY"],
                    base_url="https://api.groq.com/openai/v1",
                ).chat.completions.create(
                    model=model,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content or ""
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            return getattr(response, "text", None) or stringify(response)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            text = str(exc)
            if any(code in text for code in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "overloaded")):
                wait = 20 * (attempt + 1)
                print(f"  llm busy, wait {wait}s")
                time.sleep(wait)
                continue
            raise
    raise last_exc or RuntimeError("llm failed")


def execute_tool(composio, slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = composio.tools.execute(
        slug,
        arguments=arguments,
        user_id=USER_ID,
        dangerously_skip_version_check=True,
    )
    time.sleep(0.8)
    if isinstance(result, dict):
        return result
    return {"data": result}


def clip(text: str, limit: int = 18000) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]..."


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def citation_urls(search_payload: Any, limit: int = 3) -> list[str]:
    urls: list[str] = []
    blob = stringify(search_payload)

    def add(url: str) -> None:
        url = url.strip()
        if url.startswith("http") and url not in urls:
            urls.append(url)

    if isinstance(search_payload, dict):
        data = search_payload.get("data", search_payload)
        if isinstance(data, dict):
            results = data.get("results", data)
            if isinstance(results, dict):
                for item in results.get("citations") or []:
                    if isinstance(item, dict):
                        add(str(item.get("url") or item.get("link") or ""))
                    elif isinstance(item, str):
                        add(item)
                for item in results.get("organic_results") or []:
                    if isinstance(item, dict):
                        add(str(item.get("url") or item.get("link") or ""))
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        add(str(item.get("url") or item.get("link") or ""))
    for match in re.findall(r"https?://[^\s\"'\\<>]+", blob):
        add(match.rstrip(").,]}"))
        if len(urls) >= 12:
            break
    return urls[:limit]


def research_pack(composio, app: dict[str, Any], force: bool) -> dict[str, Any]:
    folder = cache_dir(app["id"])
    pack_path = folder / "research_pack.json"
    if pack_path.exists() and not force:
        return load_json(pack_path, {})

    query = (
        f"{app['name']} developer API authentication OAuth API key "
        f"MCP server documentation {app.get('hint_url', '')}"
    )
    search = execute_tool(composio, "COMPOSIO_SEARCH_WEB", {"query": query})
    urls = [app.get("hint_url")] + citation_urls(search, limit=3)
    urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
    # unique, keep order
    seen: set[str] = set()
    uniq: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            uniq.append(url)
    fetch = execute_tool(
        composio,
        "COMPOSIO_SEARCH_FETCH_URL_CONTENT",
        {"urls": uniq[:4], "text": True, "max_characters": 12000},
    )
    pack = {"query": query, "urls": uniq[:4], "search": search, "fetch": fetch}
    save_json(pack_path, pack)
    return pack


def extract_json_text(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def empty_row(app: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "id": app["id"],
        "name": app["name"],
        "category": app["category"],
        "one_liner": "",
        "auth_methods": ["unknown"],
        "access": "unknown",
        "api_type": "unknown",
        "api_breadth": "unknown",
        "mcp": "unknown",
        "verdict": "unknown",
        "blocker": reason,
        "evidence_urls": [app.get("hint_url") or ""],
        "confidence": 0.1,
        "notes": reason,
        "needs_human": True,
    }


def coerce_row(app: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    row["id"] = app["id"]
    row["name"] = app["name"]
    row["category"] = app["category"]
    auth = row.get("auth_methods", ["unknown"])
    if isinstance(auth, str):
        auth = [auth]
    row["auth_methods"] = auth or ["unknown"]
    urls = row.get("evidence_urls") or [app.get("hint_url") or ""]
    if isinstance(urls, str):
        urls = [urls]
    row["evidence_urls"] = [u for u in urls if u]
    row.setdefault("one_liner", "")
    row.setdefault("blocker", None)
    row.setdefault("notes", "")
    row.setdefault("needs_human", True)
    row.setdefault("confidence", 0.3)
    return row


def extract_row(validator, app: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        f"{SYSTEM_RULES}\n\n"
        f"App id: {app['id']}\nName: {app['name']}\nCategory: {app['category']}\n"
        f"Hint URL: {app.get('hint_url')}\n\n"
        f"Search results:\n{clip(stringify(pack.get('search')), 9000)}\n\n"
        f"Fetched pages:\n{clip(stringify(pack.get('fetch')), 18000)}\n\n"
        "Fill every schema field. id, name, category must match the app above."
    )
    last_error = ""
    for _ in range(2):
        raw = generate_json(prompt)
        try:
            row = extract_json_text(raw)
        except json.JSONDecodeError as exc:
            last_error = f"invalid json: {exc}"
            prompt += f"\nPrevious output was not valid JSON ({exc}). Return JSON only."
            continue
        row = coerce_row(app, row)
        extras = set(row) - set(validator.schema.get("properties", {}))
        for key in extras:
            row.pop(key, None)
        errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
        if not errors:
            save_json(cache_dir(app["id"]) / "extract.json", row)
            return row
        last_error = "; ".join(e.message for e in errors[:6])
        prompt += f"\nSchema errors: {last_error}. Fix the JSON."
    row = empty_row(app, last_error or "extract failed")
    save_json(cache_dir(app["id"]) / "extract.json", row)
    return row


def upsert_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = load_json(RESULTS_PATH, [])
    by_id = {int(item["id"]): item for item in existing if "id" in item}
    for row in rows:
        by_id[int(row["id"])] = row
    merged = [by_id[key] for key in sorted(by_id)]
    save_json(RESULTS_PATH, merged)
    return merged


def compare_gold() -> int:
    gold = {int(item["id"]): item for item in load_json(GOLD_PATH, [])}
    results = {int(item["id"]): item for item in load_json(RESULTS_PATH, [])}
    if not gold:
        print("data/gold10.json is empty")
        return 1
    field_hits = 0
    field_total = 0
    print("Gold vs agent (enum fields only)")
    for app_id, expected in sorted(gold.items()):
        got = results.get(app_id)
        if not got:
            print(f"  {app_id} {expected['name']}: MISSING in results.json")
            field_total += len(COMPARE_FIELDS)
            continue
        misses: list[str] = []
        for field in COMPARE_FIELDS:
            field_total += 1
            exp = expected.get(field)
            actual = got.get(field)
            if field == "auth_methods":
                ok = set(exp or []) == set(actual or []) or bool(set(exp or []) & set(actual or []))
            else:
                ok = exp == actual
            if ok:
                field_hits += 1
            else:
                misses.append(f"{field}: gold={exp!r} agent={actual!r}")
        status = "OK" if not misses else "DIFF"
        print(f"  {app_id} {expected['name']}: {status}")
        for miss in misses:
            print(f"    {miss}")
    pct = 0 if not field_total else round(100 * field_hits / field_total, 1)
    print(f"Match rate: {field_hits}/{field_total} ({pct}%)")
    return 0 if pct >= 70 else 2


def run_research(apps: list[dict[str, Any]], force: bool, extract_only: bool) -> None:
    schema = load_json(SCHEMA_PATH, {})
    validator = Draft202012Validator(schema)
    existing = {int(item["id"]) for item in load_json(RESULTS_PATH, []) if "id" in item}
    composio = composio_client()
    require_llm_keys()
    done = []
    for index, app in enumerate(apps, start=1):
        app_id = int(app["id"])
        extract_path = cache_dir(app_id) / "extract.json"
        if not force and not extract_only and extract_path.exists():
            row = load_json(extract_path, {})
            if row.get("verdict") != "unknown":
                print(f"[{index}/{len(apps)}] {app['name']}: cache")
                done.append(row)
                upsert_results(done)
                continue
        if not force and not extract_only and app_id in existing:
            print(f"[{index}/{len(apps)}] {app['name']}: already in results.json")
            continue
        print(f"[{index}/{len(apps)}] {app['name']}: {'extract' if extract_only else 'research'}")
        try:
            pack = research_pack(composio, app, force=force and not extract_only)
            row = extract_row(validator, app, pack)
        except Exception as exc:  # noqa: BLE001 — keep the batch running
            row = empty_row(app, str(exc))
            save_json(cache_dir(app_id) / "extract.json", row)
            print(f"  error: {exc}")
        done.append(row)
        upsert_results(done)
    upsert_results(done)
    print(f"Wrote {len(load_json(RESULTS_PATH, []))} rows to {RESULTS_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Composio + Gemini app research agent")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--ids", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true", help="Ignore cache and research again")
    parser.add_argument("--extract-only", action="store_true", help="Reuse cached pages; only re-run Gemini")
    parser.add_argument("--compare-gold", action="store_true")
    args = parser.parse_args()

    if args.compare_gold and not (args.all or args.ids or args.limit):
        raise SystemExit(compare_gold())

    apps = load_json(APPS_PATH, [])
    selected = select_apps(apps, parse_ids(args.ids) if args.ids else None, args.limit, args.all)
    run_research(selected, force=args.force, extract_only=args.extract_only)
    if args.compare_gold or set(app["id"] for app in selected) <= {1, 11, 21, 31, 41, 51, 61, 71, 81, 91}:
        if GOLD_PATH.exists() and set(app["id"] for app in selected) == {1, 11, 21, 31, 41, 51, 61, 71, 81, 91}:
            raise SystemExit(compare_gold())


if __name__ == "__main__":
    main()
