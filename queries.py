"""The retail questions, answerable three ways.

Each query carries:
  - question:   natural-language ask
  - needs:      lists the DIRECT approach must pull whole into context
  - code:       the script the CODE-EXECUTION model writes
  - graph:      per-list plan for the MICROSOFT GRAPH approach — what OData can
                legitimately push to the server vs. what it must still pull whole

Graph rules modeled (real limitations):
  * $filter only compares a column to a LITERAL (no column-vs-column).
  * No JOIN across lists, no GROUP BY / SUM — aggregation happens client-side,
    so every row needed for the math still lands in context.
  * A pure filtered retrieval (no join, no aggregation) is where Graph wins.
"""
import sharepoint_api as sp

QUERIES = [
    {
        "id": "Q1",
        "question": "Top 5 products by total revenue in 2025.",
        "needs": ["sales", "products"],
        "graph": {
            "sales": (None, "aggregation (SUM by product) — no server-side GROUP BY"),
            "products": (None, "needed to name products — full list"),
        },
        "code": '''
import sharepoint_api as sp
from collections import defaultdict
rev = defaultdict(float)
for s in sp.sales():
    rev[s["ProductID"]] += s["LineRevenue"]
names = {p["ProductID"]: p["ProductName"] for p in sp.products()}
top = sorted(rev.items(), key=lambda kv: -kv[1])[:5]
for pid, r in top:
    print(f"{names[pid]}: ${r:,.0f}")
''',
    },
    {
        "id": "Q2",
        "question": "How many store-product positions are below their reorder point?",
        "needs": ["inventory"],
        "graph": {
            "inventory": (None, "predicate is OnHand < ReorderPoint — column-vs-column, not expressible in OData"),
        },
        "code": '''
import sharepoint_api as sp
below = [i for i in sp.inventory() if i["OnHand"] < i["ReorderPoint"]]
print(f"{len(below)} positions below reorder point")
''',
    },
    {
        "id": "Q3",
        "question": "Total 2025 revenue by region.",
        "needs": ["sales", "stores"],
        "graph": {
            "sales": (None, "aggregation (SUM by region) — no server-side GROUP BY"),
            "stores": (None, "join key for region — full list"),
        },
        "code": '''
import sharepoint_api as sp
from collections import defaultdict
region = {s["StoreID"]: s["Region"] for s in sp.stores()}
rev = defaultdict(float)
for s in sp.sales():
    rev[region[s["StoreID"]]] += s["LineRevenue"]
for reg, r in sorted(rev.items(), key=lambda kv: -kv[1]):
    print(f"{reg}: ${r:,.0f}")
''',
    },
    {
        "id": "Q4",
        "question": "Which Clearance-status products are still selling? List names + units sold.",
        "needs": ["products", "sales"],
        "graph": {
            # Status eq 'Clearance' IS a valid literal filter → pushed server-side.
            "products": (lambda p: p["Status"] == "Clearance",
                         "$filter=fields/Status eq 'Clearance' — pushed server-side"),
            # but sales can't be filtered by "ProductID in (clearance ids)" reliably
            "sales": (None, "no server-side join to clearance ids — full list for the SUM"),
        },
        "code": '''
import sharepoint_api as sp
from collections import defaultdict
clearance = {p["ProductID"]: p["ProductName"] for p in sp.products() if p["Status"] == "Clearance"}
units = defaultdict(int)
for s in sp.sales():
    if s["ProductID"] in clearance:
        units[s["ProductID"]] += s["Qty"]
for pid, u in sorted(units.items(), key=lambda kv: -kv[1]):
    print(f"{clearance[pid]}: {u} units")
''',
    },
    {
        "id": "Q5",
        "question": "Average supplier on-time rate for suppliers of the top-revenue category.",
        "needs": ["sales", "products", "suppliers"],
        "graph": {
            "sales": (None, "aggregation (SUM by category) — no server-side GROUP BY"),
            "products": (None, "join key for category — full list"),
            "suppliers": (None, "small list, pulled whole"),
        },
        "code": '''
import sharepoint_api as sp
from collections import defaultdict
cat = {p["ProductID"]: p["Category"] for p in sp.products()}
catrev = defaultdict(float)
for s in sp.sales():
    catrev[cat[s["ProductID"]]] += s["LineRevenue"]
top_cat = max(catrev, key=catrev.get)
sups = {p["SupplierID"] for p in sp.products() if p["Category"] == top_cat}
rates = [s["OnTimeRate"] for s in sp.suppliers() if s["SupplierID"] in sups]
print(f"Top category: {top_cat}; avg supplier on-time rate: {sum(rates)/len(rates):.1%}")
''',
    },
    {
        # The case Graph is BUILT for: pure filtered retrieval, no join, no math.
        "id": "Q6",
        "question": "List the March-2025 sales lines for store 1004.",
        "needs": ["sales"],
        "graph": {
            "sales": (lambda s: s["StoreID"] == 1004 and s["Month"] == "2025-03",
                      "$filter=fields/StoreID eq 1004 and fields/Month eq '2025-03' — pushed server-side"),
        },
        "code": '''
import sharepoint_api as sp
rows = [s for s in sp.sales() if s["StoreID"] == 1004 and s["Month"] == "2025-03"]
for r in rows:
    print(f'{r["OrderLineID"]}  P{r["ProductID"]}  qty {r["Qty"]}  ${r["LineRevenue"]:.2f}')
print(f"({len(rows)} lines)")
''',
    },
]

_LOADERS = {"sales": sp.sales, "products": sp.products, "stores": sp.stores,
            "inventory": sp.inventory, "suppliers": sp.suppliers}


def direct_payload(needs):
    """Full list contents the DIRECT approach streams into context."""
    return {n: _LOADERS[n]() for n in needs}


def graph_payload(graph_plan):
    """What the GRAPH approach returns into context: each list filtered
    server-side where OData allows, otherwise pulled whole.

    Returns (payload_rows_by_list, pushdown_report).
    """
    payload, report = {}, {}
    for list_name, (pred, reason) in graph_plan.items():
        rows = _LOADERS[list_name]()
        if pred is None:
            payload[list_name] = rows
            report[list_name] = {"pushed": False, "returned": len(rows),
                                 "of": len(rows), "reason": reason}
        else:
            kept = [r for r in rows if pred(r)]
            payload[list_name] = kept
            report[list_name] = {"pushed": True, "returned": len(kept),
                                 "of": len(rows), "reason": reason}
    return payload, report
