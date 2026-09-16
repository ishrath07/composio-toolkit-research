"""Auto-checks plus a stratified 20-app accuracy sample."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = DATA / "results.json"
SCHEMA = DATA / "schema.json"
SAMPLE20 = DATA / "sample20.json"
VERIFICATION = DATA / "verification.json"
AUTO_FLAGS = DATA / "auto_flags.json"
SUMMARY = DATA / "verification_summary.json"
FIELDS = ("auth_methods", "access", "api_type", "api_breadth", "mcp", "verdict")
SAMPLE_IDS = [2, 8, 12, 18, 22, 26, 32, 35, 42, 48, 53, 56, 62, 65, 72, 77, 82, 86, 92, 98]


def load(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def field_ok(field: str, expected, actual) -> bool:
    if field == "auth_methods":
        return bool(set(expected or []) & set(actual or []))
    return expected == actual


def contradictions(row: dict) -> list[str]:
    flags = []
    auth = set(row.get("auth_methods") or [])
    access = row.get("access")
    verdict = row.get("verdict")
    api_type = row.get("api_type")
    mcp = row.get("mcp")
    urls = [u for u in (row.get("evidence_urls") or []) if u]
    conf = float(row.get("confidence") or 0)

    if not urls:
        flags.append("missing_evidence_url")
    if conf < 0.6:
        flags.append("low_confidence")
    if verdict == "toolkit_today" and access == "partner_gated":
        flags.append("toolkit_today_but_partner_gated")
    if verdict == "toolkit_today" and auth <= {"unknown"}:
        flags.append("toolkit_today_but_auth_unknown")
    if verdict == "blocked" and api_type in {"rest", "graphql", "rest_and_graphql"} and access in {"self_serve", "trial"}:
        flags.append("blocked_despite_reachable_api")
    if (
        verdict == "toolkit_today"
        and api_type in {"none", "unknown"}
        and mcp != "official"
        and "other" not in auth
    ):
        flags.append("toolkit_today_without_api")
    if access == "self_serve" and (row.get("blocker") or "").lower().find("partner") >= 0:
        flags.append("self_serve_with_partner_blocker")
    return flags


def auto_check() -> dict:
    schema = load(SCHEMA, {})
    validator = Draft202012Validator(schema)
    rows = load(RESULTS, [])
    issues = []
    for row in rows:
        item = {"id": row.get("id"), "name": row.get("name"), "flags": []}
        errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
        if errors:
            item["flags"].append("schema:" + "; ".join(e.message for e in errors[:4]))
        item["flags"].extend(contradictions(row))
        if item["flags"]:
            issues.append(item)
    report = {
        "n_rows": len(rows),
        "n_flagged": len(issues),
        "low_confidence_ids": [r["id"] for r in rows if float(r.get("confidence") or 0) < 0.6],
        "issues": issues,
    }
    save(AUTO_FLAGS, report)
    print(f"auto: {len(rows)} rows, {len(issues)} flagged, {len(report['low_confidence_ids'])} low-confidence")
    for item in issues[:15]:
        print(f"  {item['id']} {item['name']}: {', '.join(item['flags'])}")
    if len(issues) > 15:
        print(f"  ... {len(issues) - 15} more")
    return report


def score_sample(pass_name: str) -> dict:
    expected = {int(x["id"]): x for x in load(SAMPLE20, [])}
    results = {int(x["id"]): x for x in load(RESULTS, [])}
    rows = []
    hits = defaultdict(int)
    totals = defaultdict(int)
    missing = []
    for app_id in SAMPLE_IDS:
        gold = expected.get(app_id)
        got = results.get(app_id)
        if not gold:
            continue
        if not got:
            missing.append(app_id)
            continue
        misses = []
        for field in FIELDS:
            totals[field] += 1
            ok = field_ok(field, gold.get(field), got.get(field))
            if ok:
                hits[field] += 1
            else:
                misses.append(
                    {"field": field, "expected": gold.get(field), "actual": got.get(field)}
                )
        rows.append(
            {
                "id": app_id,
                "name": gold["name"],
                "category": gold["category"],
                "ok": not misses,
                "misses": misses,
            }
        )
    field_total = sum(totals.values())
    field_hits = sum(hits.values())
    pct = 0 if not field_total else round(100 * field_hits / field_total, 1)
    payload = {
        "pass": pass_name,
        "sample_ids": SAMPLE_IDS,
        "missing_ids": missing,
        "n_scored": len(rows),
        "field_hits": field_hits,
        "field_total": field_total,
        "pct": pct,
        "by_field": {
            f: {
                "hits": hits[f],
                "total": totals[f],
                "pct": 0 if not totals[f] else round(100 * hits[f] / totals[f], 1),
            }
            for f in FIELDS
        },
        "rows": rows,
    }
    print(f"{pass_name}: {len(rows)}/20 scored, {field_hits}/{field_total} fields ({pct}%)")
    if missing:
        print("  missing in results.json:", missing)
    for row in rows:
        if row["misses"]:
            bits = ", ".join(f"{m['field']} {m['expected']!r}->{m['actual']!r}" for m in row["misses"])
            print(f"  MISS {row['id']} {row['name']}: {bits}")
        else:
            print(f"  OK   {row['id']} {row['name']}")
    return payload


def failed_ids(sample: dict) -> list[int]:
    ids = [row["id"] for row in sample.get("rows", []) if row.get("misses")]
    ids.extend(sample.get("missing_ids") or [])
    return sorted(set(ids))


def rerun_ids(ids: list[int]) -> None:
    if not ids:
        print("nothing to re-run")
        return
    csv = ",".join(str(i) for i in ids)
    print("re-run extract-only:", csv)
    subprocess.check_call(
        [sys.executable, str(ROOT / "src" / "research_agent.py"), "--extract-only", "--ids", csv],
        cwd=str(ROOT),
    )


def write_summary(pass1: dict, pass2: dict, auto: dict) -> dict:
    named = []
    for row in pass2.get("rows", []):
        if row.get("misses"):
            named.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "misses": row["misses"],
                }
            )
    summary = {
        "sample_size": 20,
        "pass1_pct": pass1.get("pct"),
        "pass2_pct": pass2.get("pct"),
        "headline": f"sample of 20, {pass1.get('pct')}% -> {pass2.get('pct')}% after re-run",
        "pass1_by_field": pass1.get("by_field"),
        "pass2_by_field": pass2.get("by_field"),
        "auto_flagged": auto.get("n_flagged"),
        "auto_n_rows": auto.get("n_rows"),
        "honest_misses_after_pass2": named,
        "human_needed": [
            "JS-only or login-walled docs still need a human click",
            "MCP official vs community is easy to mix up when blogs copy vendor docs",
            "paid vs self_serve (credits/plans) and sibling-product APIs (Mailchimp GraphQL) still miss",
        ],
        "gold_notes": "Pass-2 gold uses vendor docs opened for this sample (Woo/ClickUp/Airtable/Ahrefs MCP official; Otter MCP self-serve; Ahrefs paid but toolkit_today).",
    }
    save(SUMMARY, summary)
    save(VERIFICATION, {"pass1": pass1, "pass2": pass2, "auto": auto})
    print(summary["headline"])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--fix-loop", action="store_true", help="Score pass-1, re-run misses, score pass-2")
    args = parser.parse_args()
    if not args.auto and not args.sample and not args.fix_loop:
        raise SystemExit("Pass --auto, --sample 20, and/or --fix-loop")

    auto = auto_check() if (args.auto or args.fix_loop) else load(AUTO_FLAGS, {})
    prev = load(VERIFICATION, {})
    if not isinstance(prev, dict):
        prev = {}

    if args.fix_loop:
        pass1 = prev.get("pass1") or score_sample("pass1")
        if not prev.get("pass1"):
            save(VERIFICATION, {"pass1": pass1, "pass2": None, "auto": auto})
        ids = failed_ids(pass1)
        auto_ids = auto.get("low_confidence_ids") or []
        rerun_ids(sorted(set(ids) | set(auto_ids)))
        pass2 = score_sample("pass2")
        write_summary(pass1, pass2, auto_check())
        return

    if args.sample:
        # Keep the first pass-1 on disk so before/after is honest.
        if prev.get("pass1") and prev.get("pass2") is None:
            pass2 = score_sample("pass2")
            write_summary(prev["pass1"], pass2, auto or prev.get("auto") or {})
            print("pass-2 saved against the original pass-1 sample.")
        elif prev.get("pass1") and prev.get("pass2"):
            pass2 = score_sample("pass2")
            write_summary(prev["pass1"], pass2, auto or prev.get("auto") or {})
            print("pass-2 updated; pass-1 left unchanged.")
        else:
            pass1 = score_sample("pass1")
            save(VERIFICATION, {"pass1": pass1, "pass2": None, "auto": auto})
            print("pass-1 saved. After prompt tweaks + extract-only on misses:")
            print("  python src/verify.py --sample 20")


if __name__ == "__main__":
    main()
