"""Run every retail query THREE ways and measure tokens through context.

DIRECT (raw MCP tool call):
  Server returns whole lists. Every row of each needed list enters context.

GRAPH (Microsoft Graph / OData):
  Push `column op literal` $filter to the server where possible; everything
  needing a join, a column-vs-column test, or aggregation is pulled whole and
  computed client-side — so those rows still land in context.

CODE EXECUTION (MCP-as-code):
  Model sees a compact API index, writes a script, the sandbox runs it, only
  the printed answer returns to context.

All three execute for real; answers verified identical. Tokens via tiktoken.
"""
import io
import json
import contextlib
import tiktoken

from manifest import API_INDEX
from queries import QUERIES, direct_payload, graph_payload

ENC = tiktoken.get_encoding("cl100k_base")
def toks(s): return len(ENC.encode(s))

TOOL_DEF_BLURB = (
    "Tool: sharepoint_get_list(list_name) -> rows. Returns the full contents "
    "of a SharePoint list as JSON. Lists: Stores, Suppliers, Products, "
    "Inventory, Sales.\n"
)
GRAPH_BLURB = (
    "Tool: graph_list_items(site, list, $filter?, $select?, $top?) -> items. "
    "OData over a SharePoint list. $filter compares a column to a literal; no "
    "joins, no GROUP BY/aggregation.\n"
)


def run_code(code):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<query>", "exec"), {})
    return buf.getvalue().strip()


def measure_query(q):
    # ---- CODE EXECUTION ----
    answer = run_code(q["code"])
    code_tokens = toks(API_INDEX + "\n" + q["code"].strip() + "\n" + answer)

    # ---- DIRECT ----
    dpay = direct_payload(q["needs"])
    direct_tokens = toks(TOOL_DEF_BLURB + json.dumps(dpay, default=str))
    direct_rows = sum(len(v) for v in dpay.values())

    # ---- GRAPH ----
    gpay, greport = graph_payload(q["graph"])
    graph_tokens = toks(GRAPH_BLURB + json.dumps(gpay, default=str))
    graph_rows = sum(len(v) for v in gpay.values())
    any_pushed = any(r["pushed"] for r in greport.values())

    return {
        "id": q["id"],
        "question": q["question"],
        "answer": answer,
        "lists_pulled": q["needs"],
        "direct_rows": direct_rows,
        "graph_rows": graph_rows,
        "direct_tokens": direct_tokens,
        "graph_tokens": graph_tokens,
        "code_tokens": code_tokens,
        "graph_pushdown": greport,
        "graph_helps": any_pushed and graph_rows < direct_rows,
        "savings_vs_direct": round(100 * (1 - code_tokens / direct_tokens), 1),
        "graph_savings_vs_direct": round(100 * (1 - graph_tokens / direct_tokens), 1),
    }


def main():
    results = [measure_query(q) for q in QUERIES]
    dt = sum(r["direct_tokens"] for r in results)
    gt = sum(r["graph_tokens"] for r in results)
    ct = sum(r["code_tokens"] for r in results)

    print(f"{'ID':<4}{'Direct':>11}{'Graph':>11}{'Code':>9}{'Graph↓':>9}{'Code↓':>8}  Question")
    print("-" * 104)
    for r in results:
        print(f"{r['id']:<4}{r['direct_tokens']:>11,}{r['graph_tokens']:>11,}"
              f"{r['code_tokens']:>9,}{r['graph_savings_vs_direct']:>8}%"
              f"{r['savings_vs_direct']:>7}%  {r['question']}")
    print("-" * 104)
    print(f"{'ALL':<4}{dt:>11,}{gt:>11,}{ct:>9,}"
          f"{round(100*(1-gt/dt),1):>8}%{round(100*(1-ct/dt),1):>7}%")

    print("\nGraph pushdown detail:")
    for r in results:
        verdict = "GRAPH HELPS" if r["graph_helps"] else "no server-side reduction"
        print(f"  [{r['id']}] {verdict}  ({r['direct_rows']}→{r['graph_rows']} rows)")
        for lst, d in r["graph_pushdown"].items():
            mark = "push" if d["pushed"] else "pull"
            print(f"       {mark} {lst}: {d['returned']}/{d['of']} — {d['reason']}")

    with open("results.json", "w") as f:
        json.dump({"results": results,
                   "totals": {"direct_tokens": dt, "graph_tokens": gt,
                              "code_tokens": ct,
                              "code_savings_pct": round(100*(1-ct/dt), 1),
                              "graph_savings_pct": round(100*(1-gt/dt), 1)}},
                  f, indent=2)
    print("\nWrote results.json")


if __name__ == "__main__":
    main()
