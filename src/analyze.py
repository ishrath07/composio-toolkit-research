"""Cluster 100 research rows into reviewer headlines."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = DATA / "results.json"
OUT = DATA / "insights.json"

GATED = {"paid", "admin", "partner_gated"}
SELF = {"self_serve", "trial"}


def load_rows() -> list[dict]:
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def pct(n: int, d: int) -> float:
    return 0.0 if not d else round(100 * n / d, 1)


def names(rows: list[dict], limit: int = 8) -> list[str]:
    return [r["name"] for r in rows[:limit]]


def dominant_auth(rows: list[dict]) -> dict:
    counts = Counter()
    for row in rows:
        for method in row.get("auth_methods") or []:
            counts[method] += 1
    total_apps = len(rows)
    oauth = sum(1 for r in rows if "oauth2" in (r.get("auth_methods") or []))
    api_key = sum(1 for r in rows if "api_key" in (r.get("auth_methods") or []))
    by_cat = {}
    for cat, group in by_category(rows).items():
        methods = Counter()
        for row in group:
            for method in row.get("auth_methods") or []:
                methods[method] += 1
        top, top_n = methods.most_common(1)[0] if methods else ("unknown", 0)
        by_cat[cat] = {
            "top": top,
            "top_n": top_n,
            "n": len(group),
            "oauth2_apps": sum(1 for r in group if "oauth2" in (r.get("auth_methods") or [])),
            "api_key_apps": sum(1 for r in group if "api_key" in (r.get("auth_methods") or [])),
        }
    return {
        "method_mentions": dict(counts),
        "oauth2_apps": oauth,
        "api_key_apps": api_key,
        "oauth2_pct": pct(oauth, total_apps),
        "api_key_pct": pct(api_key, total_apps),
        "by_category": by_cat,
    }


def by_category(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["category"]].append(row)
    return dict(groups)


def access_split(rows: list[dict]) -> dict:
    overall = Counter(r["access"] for r in rows)
    self_n = sum(1 for r in rows if r["access"] in SELF)
    gated_n = sum(1 for r in rows if r["access"] in GATED)
    by_cat = {}
    for cat, group in by_category(rows).items():
        self_c = [r for r in group if r["access"] in SELF]
        gated_c = [r for r in group if r["access"] in GATED]
        by_cat[cat] = {
            "n": len(group),
            "self_serve_or_trial": len(self_c),
            "gated": len(gated_c),
            "self_pct": pct(len(self_c), len(group)),
            "gated_names": names(gated_c),
            "access": dict(Counter(r["access"] for r in group)),
        }
    return {
        "counts": dict(overall),
        "self_serve_or_trial": self_n,
        "gated": gated_n,
        "self_pct": pct(self_n, len(rows)),
        "gated_pct": pct(gated_n, len(rows)),
        "by_category": by_cat,
    }


def mcp_split(rows: list[dict]) -> dict:
    counts = Counter(r["mcp"] for r in rows)
    official = [r for r in rows if r["mcp"] == "official"]
    community = [r for r in rows if r["mcp"] == "community"]
    missing = [r for r in rows if r["mcp"] in {"none", "unknown"}]
    by_cat = {}
    for cat, group in by_category(rows).items():
        off = [r for r in group if r["mcp"] == "official"]
        miss = [r for r in group if r["mcp"] in {"none", "unknown"}]
        by_cat[cat] = {
            "n": len(group),
            "official": len(off),
            "community": sum(1 for r in group if r["mcp"] == "community"),
            "missing": len(miss),
            "official_pct": pct(len(off), len(group)),
            "missing_names": names(miss),
        }
    return {
        "counts": dict(counts),
        "official": len(official),
        "community": len(community),
        "missing": len(missing),
        "official_pct": pct(len(official), len(rows)),
        "missing_pct": pct(len(missing), len(rows)),
        "by_category": by_cat,
        "missing_but_toolkit": names(
            [r for r in missing if r["verdict"] == "toolkit_today"], 12
        ),
    }


def blocker_label(row: dict) -> str:
    text = (row.get("blocker") or "").strip()
    if text:
        low = text.lower()
        if "partner" in low or "sales" in low:
            return "partnership / contact-sales"
        if "review" in low or "admin" in low or "approv" in low or "developer token" in low:
            return "admin / app review"
        if "paid" in low or "credit" in low or "plan" in low or "enterprise" in low or "lite" in low:
            return "paid plan / credits"
        if "no " in low and "api" in low:
            return "no public API"
        return text[:80]
    if row["verdict"] == "blocked":
        return "no public API"
    if row["access"] == "partner_gated":
        return "partnership / contact-sales"
    if row["access"] == "admin":
        return "admin / app review"
    if row["access"] == "paid":
        return "paid plan / credits"
    if row["mcp"] in {"none", "unknown"} and row["verdict"] == "toolkit_today":
        return "REST/API today, no vendor MCP"
    return "none"


def top_blockers(rows: list[dict]) -> dict:
    hard = [r for r in rows if r["verdict"] in {"blocked", "possible_with_work"} or r["access"] in GATED]
    labels = Counter(blocker_label(r) for r in hard)
    clusters = defaultdict(list)
    for row in hard:
        clusters[blocker_label(row)].append(row["name"])
    mcp_gap = [r for r in rows if r["mcp"] in {"none", "unknown"} and r["verdict"] == "toolkit_today"]
    return {
        "hard_rows": len(hard),
        "counts": dict(labels.most_common()),
        "examples": {k: v[:6] for k, v in clusters.items()},
        "mcp_gap_with_api": {
            "n": len(mcp_gap),
            "examples": names(mcp_gap, 10),
        },
    }


def clusters(rows: list[dict]) -> dict:
    easy = [
        r
        for r in rows
        if r["verdict"] == "toolkit_today" and r["access"] in SELF and r["mcp"] == "official"
    ]
    rest_only = [
        r
        for r in rows
        if r["verdict"] == "toolkit_today" and r["access"] in SELF and r["mcp"] != "official"
    ]
    outreach = [
        r
        for r in rows
        if r["verdict"] in {"possible_with_work", "blocked"} or r["access"] in GATED
    ]
    by_cat_easy = Counter(r["category"] for r in easy)
    by_cat_out = Counter(r["category"] for r in outreach)
    return {
        "easy_toolkit_wins": {
            "n": len(easy),
            "pct": pct(len(easy), len(rows)),
            "by_category": dict(by_cat_easy),
            "examples": names(easy, 12),
        },
        "api_ready_mcp_missing": {
            "n": len(rest_only),
            "pct": pct(len(rest_only), len(rows)),
            "examples": names(rest_only, 12),
        },
        "outreach_needed": {
            "n": len(outreach),
            "pct": pct(len(outreach), len(rows)),
            "by_category": dict(by_cat_out),
            "examples": names(sorted(outreach, key=lambda r: r["access"]), 12),
        },
    }


def verdicts(rows: list[dict]) -> dict:
    counts = Counter(r["verdict"] for r in rows)
    by_cat = {
        cat: dict(Counter(r["verdict"] for r in group))
        for cat, group in by_category(rows).items()
    }
    return {"counts": dict(counts), "by_category": by_cat, "n": len(rows)}


def headlines(rows: list[dict], auth: dict, access: dict, mcp: dict, blockers: dict, clus: dict) -> list[str]:
    n = len(rows)
    toolkit = sum(1 for r in rows if r["verdict"] == "toolkit_today")
    crm = auth["by_category"]["CRM and Sales"]
    scrape = auth["by_category"]["Data, SEO and Scraping"]
    prod = auth["by_category"]["Productivity and Project Management"]
    ads = access["by_category"]["Marketing, Ads, Email and Social"]
    fin = access["by_category"]["Finance and Fintech"]
    comms = mcp["by_category"]["Communications and Messaging"]
    dev = mcp["by_category"]["Developer, Infra and Data platforms"]
    admin_n = blockers["counts"].get("admin / app review", 0)
    mcp_gap = blockers["mcp_gap_with_api"]
    easy = clus["easy_toolkit_wins"]
    out = clus["outreach_needed"]
    return [
        f"{toolkit} of {n} apps are buildable as a toolkit today; {easy['n']} already combine self-serve creds with an official MCP.",
        f"OAuth2 dominates overall ({auth['oauth2_apps']}/{n}) and is universal in CRM ({crm['oauth2_apps']}/10) and productivity ({prod['oauth2_apps']}/10). Scraping/SEO is the API-key pocket ({scrape['api_key_apps']}/10 apps).",
        f"{access['self_serve_or_trial']}/{n} apps are self-serve. Gating clusters in ads ({', '.join(ads['gated_names'])}) and finance ({', '.join(fin['gated_names'])}), not in support, comms, or developer platforms.",
        f"Official MCP already exists on {mcp['official']}/{n} apps, including all {dev['n']} developer/infra tools. The MCP-missing cluster is consumer messaging ({', '.join(comms['missing_names'])}), plus a few email APIs -- not meeting-note apps.",
        f"Top blockers are admin/app-review ({admin_n}: Google Ads, Meta Ads, LinkedIn Ads, Threads, Amazon SP, DealCloud, Plaid), then paid data (SE Ranking, PitchBook), partnership (Salesforce Commerce Cloud), and no public API (Sherlock, NotebookLM).",
        f"Easy toolkit wins: ship CRM, support, and infra first ({easy['by_category'].get('Developer, Infra and Data platforms', 0)}/10 infra already official MCP). Outreach-needed is {out['n']} apps. {mcp_gap['n']} more have a usable REST API today but no vendor MCP (Discord, Telegram, WhatsApp, Mailchimp, SendGrid).",
    ]


def main() -> None:
    rows = load_rows()
    if len(rows) != 100:
        raise SystemExit(f"expected 100 rows, got {len(rows)}")
    auth = dominant_auth(rows)
    access = access_split(rows)
    mcp = mcp_split(rows)
    blockers = top_blockers(rows)
    clus = clusters(rows)
    verd = verdicts(rows)
    payload = {
        "n": len(rows),
        "verdicts": verd,
        "auth": auth,
        "access": access,
        "mcp": mcp,
        "blockers": blockers,
        "clusters": clus,
        "headlines": headlines(rows, auth, access, mcp, blockers, clus),
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} from {len(rows)} rows")
    for i, line in enumerate(payload["headlines"], 1):
        print(f"{i}. {line}")


if __name__ == "__main__":
    main()
