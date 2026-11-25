# mcp-poc — Direct vs Graph vs Code-Execution on SharePoint data

Tests the approach in Anthropic's [Code Execution with MCP](https://www.anthropic.com/research/code-execution-with-mcp)
against retail data that mimics SharePoint lists. The question: for a set of
real retail questions, how many tokens flow through the model's context under
three ways of reaching the data?

- **DIRECT** — the raw MCP tool returns whole lists; every row enters context.
- **GRAPH** — Microsoft Graph / OData: push a `column op literal` `$filter`
  (or `$orderby`+`$top`) to the server where possible; anything needing a join,
  a column-vs-column test, or aggregation is still pulled whole and computed
  client-side.
- **CODE EXECUTION** — the model sees a compact API index, writes a short Python
  script, the sandbox runs it, and only the printed answer returns to context.

All three execute for real; the answers are verified identical and tokens are
counted with `tiktoken`.

## Two benchmarks

| | `harness.py` (generated) | `real_benchmark.py` (live) |
|---|---|---|
| Data | 5 synthetic lists written by `generate_data.py` into `sharepoint_lists/` | 7 real Excel files in `haiintel.sharepoint.com/sites/Test_Team/Mock_Data`, fetched via Graph |
| Access layer | `sharepoint_api/` (reads local `.xlsx`) | `graph_client.py` + `retail_api.py` (live Graph) |
| Needs credentials | no | yes (`.env`) |
| Output | `results.json` | `real_results.json` |

## Run it

### Generated benchmark (no credentials)
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python generate_data.py   # writes sharepoint_lists/*.xlsx
.venv/bin/python harness.py         # writes results.json
```

### Live benchmark (needs a tenant)
```
cp .env.example .env                # fill in Azure app credentials
.venv/bin/python inspect_data.py    # sanity-check: schema + sample rows
.venv/bin/python real_benchmark.py  # writes real_results.json
```
The Azure app needs Graph `Sites.Read.All` (application permission). The seven
`*.xlsx` files must live in the `Mock_Data` library of a site matching
`Test_Team`. These files are not in the repo — they lived in SharePoint.

## Results

### Generated data (tiny API index vs full lists)
```
ID      Direct       Graph     Code   Graph↓   Code↓
Q1     263,040     263,051      328    -0.0%   99.9%   Top 5 products by revenue
Q2      22,989      23,000      236    -0.0%   99.0%   Positions below reorder point
Q3     260,005     260,016      313    -0.0%   99.9%   Revenue by region
Q4     263,041     259,613      341     1.3%   99.9%   Clearance products still selling
Q5     263,372     263,383      356    -0.0%   99.9%   Avg supplier on-time, top category
Q6     259,193       1,082      538    99.6%   99.8%   March sales for one store
ALL  1,331,640   1,070,145    2,112    19.6%   99.8%
```

### Live tenant (measured)
```
ID      Direct       Graph*    Code   Graph↓   Code↓
Q1      14,586       4,824      462    66.9%   96.8%   Avg revenue-attainment by store
Q2      14,586       5,759      517    60.5%   96.5%   Employees under 80% target, per store
Q3      17,944      17,968      439    -0.1%   97.6%   Hours booked vs contracted per district
Q4       5,623       2,014      407    64.2%   92.8%   Top 5 earners + manager
Q5       6,744       6,768      387    -0.4%   94.3%   Avg store-KPI attainment by district
Q6      16,311         440      357    97.3%   97.8%   Shift lines, one store one day
ALL     75,794      37,773    2,569    50.2%   96.6%
```
\* The Graph column is the best-case "if this data were SharePoint **Lists**."

## What it shows

- **Code execution wins everywhere.** ~97% token cut on live data, ~99.8% on
  the generated set. The gap is only because the live tables are small
  (16–240 rows); the mechanism is the same, there's just less to save.
- **Graph splits cleanly by question type.** It helps a lot on filters and
  top-N (Q6 −97%, Q1/Q2/Q4 around −60 to −67%) — those are `$filter` /
  `$orderby`+`$top`, pushed server-side. It helps **zero** on aggregate-and-join
  questions (Q3, Q5) because OData has no server-side GROUP BY and no cross-list
  JOIN. This matches the article's stated limits.
- **The honest catch:** the live tenant stores this data as **Excel files in a
  document library**, not as Lists. Graph's Workbook API can't return only the
  matching rows, so real Graph-on-Excel ties DIRECT on all six questions. The
  50% Graph number is the optimistic "if they'd used Lists" case.

## Files

| File | Role |
|---|---|
| `generate_data.py` | writes the 5 synthetic lists into `sharepoint_lists/` |
| `sharepoint_api/__init__.py` | code-execution API over the local lists |
| `manifest.py` | compact API index the model sees (progressive disclosure) |
| `queries.py` | the 6 generated-data questions, three ways each |
| `harness.py` | runs + measures the generated benchmark → `results.json` |
| `graph_client.py` | Graph auth + fetch `.xlsx` from the live library |
| `retail_api.py` | typed API over the live retail files |
| `inspect_data.py` | prints live schema + sample rows |
| `real_benchmark.py` | runs + measures the live benchmark → `real_results.json` |
| `article.md` | write-up of the experiment |
| `report.html` | visual report (published as a Claude Artifact) |

## Reconstruction note

This project was deleted and rebuilt from the Claude Code session transcript.
Fully recovered: all source files, the generated data (regenerated), and the
measured live results. Not recovered: the original `.env` secret values (masked
in the transcript — use `.env.example`), the live `*.xlsx` source files (they
lived in SharePoint), and `sharepoint_test.py` (a pre-existing credential-test
script, never captured in full). `article.pdf` was generated from `article.md`.
