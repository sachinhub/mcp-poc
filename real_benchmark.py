"""Three-way benchmark on LIVE SharePoint data (Test_Team > Mock_Data).

Data is fetched through Microsoft Graph from the real tenant. Each question is
answered three ways and we count the tokens that would flow through the model's
context:

  DIRECT          - the whole needed files come back; every row enters context.
  GRAPH (as List) - best case if this data lived in SharePoint Lists: push a
                    column-vs-literal $filter, or $orderby+$top, to the server;
                    anything needing a join or aggregation is pulled whole.
  CODE EXECUTION  - fetch once, compute in a sandbox, return only the answer.

Important caveat printed at the end: on THIS tenant the data is Excel files in a
document library, where Graph's Workbook API cannot return only the matching
rows. So the GRAPH column is an optimistic "if it were Lists" number; the real
Graph-on-Excel cost equals DIRECT.

All three really run against live data; code answers are computed, not mocked.
"""
import io
import json
import contextlib
import tiktoken

import retail_api as rapi

ENC = tiktoken.get_encoding("cl100k_base")
def toks(s): return len(ENC.encode(s))

DIRECT_BLURB = ("Tool: get_file_rows(name) -> rows. Returns every row of a "
                "SharePoint Excel file as JSON.\n")
GRAPH_BLURB = ("Tool: graph_list_items(list, $filter?, $orderby?, $top?) -> items. "
               "OData over a SharePoint list: filter a column against a literal, "
               "or order+top. No joins, no GROUP BY.\n")
API_INDEX = (
    "# Live retail API (import retail_api as r)\n"
    "# r.stores()     -> [{Store ID, Name, City, 'Metro / District', Banner, Status, 'District Manager', ...}]\n"
    "# r.employees()  -> [{Employee ID, Full Name, Department, Banner, 'Reports To', ...}]\n"
    "# r.shifts()     -> [{Employee ID, Full Name, Store, Date, 'Hours Booked', 'Hours Contracted', Role}]\n"
    "# r.scorecards() -> [{Employee ID, Period, KPI, Value, '% of Target'}]\n"
    "# r.incentives() -> [{Employee ID, Period, 'MTD (USD)', Tier, 'Streak (weeks)'}]\n"
    "# r.store_kpis() -> [{Store ID, Store, Period, KPI, '% of Target', '8-Point Trend'}]\n"
    "# r.store_of(id) -> 'TX-0218' from 'TX-0218-E1' or 'TX-0218 Plano...'\n"
    "# Write a short script; print only the answer."
)


# Each question: files it needs (direct), a graph reducer per file, and code.
def topn(rows, key, n):
    return sorted(rows, key=lambda x: -(_num(x.get(key))), reverse=False)[:n]


def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except Exception:
        return 0.0


QUESTIONS = [
    {
        "id": "Q1",
        "q": "Average revenue-attainment score by store.",
        "needs": ["scorecards", "stores"],
        "graph": {
            "scorecards": (lambda rs: [r for r in rs if r.get("KPI") == "Revenue attainment"],
                           "$filter=KPI eq 'Revenue attainment' — pushed"),
            "stores": (None, "join for store name — full list"),
        },
        "code": '''
import retail_api as r
from collections import defaultdict
names = {s["Store ID"]: s["Name"] for s in r.stores()}
agg = defaultdict(list)
for sc in r.scorecards():
    if sc["KPI"] == "Revenue attainment":
        agg[r.store_of(sc["Employee ID"])].append(float(sc["% of Target"]))
for sid, vals in sorted(agg.items()):
    print(f'{names.get(sid, sid)}: {sum(vals)/len(vals):.0f}%')
''',
    },
    {
        "id": "Q2",
        "q": "How many employees are below 80% of target on any KPI, per store?",
        "needs": ["scorecards", "stores"],
        "graph": {
            "scorecards": (lambda rs: [r for r in rs if _num(r.get("% of Target")) < 80],
                           "$filter=fields/TargetPct lt 80 — pushed"),
            "stores": (None, "join for store name — full list"),
        },
        "code": '''
import retail_api as r
from collections import defaultdict
names = {s["Store ID"]: s["Name"] for s in r.stores()}
cnt = defaultdict(int)
for sc in r.scorecards():
    if float(str(sc["% of Target"]).replace("%","")) < 80:
        cnt[r.store_of(sc["Employee ID"])] += 1
for sid, c in sorted(cnt.items(), key=lambda kv: -kv[1]):
    print(f'{names.get(sid, sid)}: {c} under-target scores')
''',
    },
    {
        "id": "Q3",
        "q": "Hours booked vs contracted per district.",
        "needs": ["shifts", "stores"],
        "graph": {
            "shifts": (None, "SUM by district — no server-side aggregation"),
            "stores": (None, "join for district — full list"),
        },
        "code": '''
import retail_api as r
from collections import defaultdict
district = {s["Store ID"]: s["Metro / District"] for s in r.stores()}
booked = defaultdict(float); contracted = defaultdict(float)
for sh in r.shifts():
    d = district.get(r.store_of(sh["Store"]), "?")
    if sh["Hours Booked"] not in (None, ""):
        booked[d] += float(sh["Hours Booked"])
    if sh["Hours Contracted"] not in (None, ""):
        contracted[d] += float(sh["Hours Contracted"])
for d in sorted(booked):
    print(f'{d}: {booked[d]:.0f} booked / {contracted[d]:.0f} contracted')
''',
    },
    {
        "id": "Q4",
        "q": "Top 5 earners by incentive MTD, with store and district manager.",
        "needs": ["incentives", "stores"],
        "graph": {
            "incentives": (lambda rs: sorted(rs, key=lambda x: -_num(x.get("MTD (USD)")))[:5],
                           "$orderby=MTD desc & $top=5 — pushed"),
            "stores": (None, "join for store + manager — full list"),
        },
        "code": '''
import retail_api as r
net = {s["Store ID"]: s for s in r.stores()}
top = sorted(r.incentives(), key=lambda x: -float(x["MTD (USD)"]))[:5]
for i in top:
    sid = r.store_of(i["Employee ID"])
    s = net.get(sid, {})
    print(f'{i["Full Name"]} (${i["MTD (USD)"]}) — {s.get("Name", sid)}, mgr {s.get("District Manager","?")}')
''',
    },
    {
        "id": "Q5",
        "q": "Average store-KPI attainment by district.",
        "needs": ["store_kpis", "stores"],
        "graph": {
            "store_kpis": (None, "AVG by district — no server-side aggregation"),
            "stores": (None, "join for district — full list"),
        },
        "code": '''
import retail_api as r
from collections import defaultdict
district = {s["Store ID"]: s["Metro / District"] for s in r.stores()}
vals = defaultdict(list)
for k in r.store_kpis():
    vals[district.get(k["Store ID"], "?")].append(float(str(k["% of Target"]).replace("%","")))
for d, v in sorted(vals.items(), key=lambda kv: -sum(kv[1])/len(kv[1])):
    print(f'{d}: {sum(v)/len(v):.0f}% avg attainment')
''',
    },
    {
        "id": "Q6",
        "q": "List the shift lines for store TX-0218 on 2026-09-10.",
        "needs": ["shifts"],
        "graph": {
            "shifts": (lambda rs: [r for r in rs if str(r.get("Store","")).startswith("TX-0218")
                                   and str(r.get("Date")) == "2026-09-10"],
                       "$filter=startswith(Store,'TX-0218') and Date eq '2026-09-10' — pushed"),
        },
        "code": '''
import retail_api as r
rows = [s for s in r.shifts() if str(s["Store"]).startswith("TX-0218") and str(s["Date"]) == "2026-09-10"]
for s in rows:
    print(f'{s["Full Name"]} {s["Role"]}: {s["Hours Booked"] or 0}h booked')
print(f'({len(rows)} lines)')
''',
    },
]

LOADERS = {"stores": rapi.stores, "employees": rapi.employees,
           "attendance": rapi.attendance, "shifts": rapi.shifts,
           "scorecards": rapi.scorecards, "incentives": rapi.incentives,
           "store_kpis": rapi.store_kpis}


def run_code(code):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<q>", "exec"), {})
    return buf.getvalue().strip()


def measure(qd):
    # code execution (runs for real against live data)
    answer = run_code(qd["code"])
    code_tokens = toks(API_INDEX + "\n" + qd["code"].strip() + "\n" + answer)

    # direct: full rows of each needed file
    direct = {n: LOADERS[n]() for n in qd["needs"]}
    direct_tokens = toks(DIRECT_BLURB + json.dumps(direct, default=str))
    direct_rows = sum(len(v) for v in direct.values())

    # graph: reduce each file where OData could
    gpay, pushed_any, graph_rows, detail = {}, False, 0, []
    for n in qd["needs"]:
        rows = LOADERS[n]()
        reducer, reason = qd["graph"][n]
        kept = reducer(rows) if reducer else rows
        gpay[n] = kept
        graph_rows += len(kept)
        pushed = reducer is not None and len(kept) < len(rows)
        pushed_any = pushed_any or pushed
        detail.append((n, len(kept), len(rows), pushed, reason))
    graph_tokens = toks(GRAPH_BLURB + json.dumps(gpay, default=str))

    return {
        "id": qd["id"], "q": qd["q"], "answer": answer,
        "needs": qd["needs"], "direct_rows": direct_rows, "graph_rows": graph_rows,
        "direct_tokens": direct_tokens, "graph_tokens": graph_tokens,
        "code_tokens": code_tokens, "graph_helps": pushed_any and graph_rows < direct_rows,
        "graph_detail": detail,
        "code_savings": round(100 * (1 - code_tokens / direct_tokens), 1),
        "graph_savings": round(100 * (1 - graph_tokens / direct_tokens), 1),
    }


def main():
    print("Fetching live data and running benchmark...\n")
    res = [measure(q) for q in QUESTIONS]
    dt = sum(r["direct_tokens"] for r in res)
    gt = sum(r["graph_tokens"] for r in res)
    ct = sum(r["code_tokens"] for r in res)

    print(f"{'ID':<4}{'Direct':>10}{'Graph':>10}{'Code':>8}{'Graph↓':>8}{'Code↓':>7}  Question")
    print("-" * 100)
    for r in res:
        print(f"{r['id']:<4}{r['direct_tokens']:>10,}{r['graph_tokens']:>10,}{r['code_tokens']:>8,}"
              f"{r['graph_savings']:>7}%{r['code_savings']:>6}%  {r['q']}")
    print("-" * 100)
    print(f"{'ALL':<4}{dt:>10,}{gt:>10,}{ct:>8,}{round(100*(1-gt/dt),1):>7}%{round(100*(1-ct/dt),1):>6}%")

    print("\nAnswers (computed live):")
    for r in res:
        first = r["answer"].splitlines()[0] if r["answer"] else "(no output)"
        more = f"  (+{len(r['answer'].splitlines())-1} more)" if r["answer"].count("\n") else ""
        print(f"  [{r['id']}] {first}{more}")

    print("\nGraph pushdown detail:")
    for r in res:
        tag = "HELPS" if r["graph_helps"] else "no reduction"
        print(f"  [{r['id']}] {tag}  {r['direct_rows']}->{r['graph_rows']} rows")
        for n, kept, tot, pushed, reason in r["graph_detail"]:
            print(f"       {'push' if pushed else 'pull'} {n}: {kept}/{tot} — {reason}")

    with open("real_results.json", "w") as f:
        json.dump({"results": res,
                   "totals": {"direct_tokens": dt, "graph_tokens": gt, "code_tokens": ct,
                              "graph_savings": round(100*(1-gt/dt), 1),
                              "code_savings": round(100*(1-ct/dt), 1)},
                   "source": "live:haiintel.sharepoint.com/sites/Test_Team/Mock_Data"},
                  f, indent=2)
    print("\nWrote real_results.json")
    print("\nNOTE: the Graph column assumes this data were SharePoint Lists. On this")
    print("tenant it is Excel files in a library, where Graph can't return only the")
    print("matching rows — so real Graph-on-Excel ties DIRECT on every question.")


if __name__ == "__main__":
    main()
