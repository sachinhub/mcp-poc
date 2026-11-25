# mcp-poc — Direct vs Graph vs Code-Execution on SharePoint data

This repo tests the approach in Anthropic's [Code Execution with MCP](https://www.anthropic.com/research/code-execution-with-mcp)
on retail data that mimics SharePoint lists. For a set of retail questions, it
measures how many tokens flow through the model's context under three ways of
reaching the data:

- **Direct**: the raw MCP tool returns whole lists. Every row enters context.
- **Graph**: Microsoft Graph / OData. Where possible it pushes a `column op literal`
  `$filter` (or `$orderby`+`$top`) to the server. Anything needing a join, a
  column-vs-column test, or aggregation is pulled whole and computed client-side.
- **Code execution**: the model sees a compact API index, writes a short Python
  script, the sandbox runs it, and only the printed answer returns to context.

All three run for real. The answers are verified identical and tokens are counted
with `tiktoken`.

## How the code approach works

The data sources are exposed as a small code API (`sharepoint_api` / `retail_api`)
rather than as a tool that dumps whole lists into context. The model writes a
short script against that API, a sandbox runs it, and only the printed answer
comes back.

What the model does:
1. Reads a compact API index (`manifest.py`): a few hundred tokens of function
   signatures and column names, no rows.
2. Writes a Python script that imports the API, calls the loaders, and filters,
   joins, or aggregates inside the sandbox.
3. Receives only the final printed answer.

The raw rows never reach the model. The 4,000 sales lines and 240 scorecards pass
through the sandbox's memory and stay out of the context window. That is where
the saving comes from.

| | What enters model context |
|---|---|
| Direct | Full JSON of every needed list |
| Graph | Server-filtered rows where OData allows, full lists otherwise |
| Code execution | API index, the script, the answer line |

Take Q6, "shift lines for one store on one day." Direct sends all 167 shift rows
(16,311 tokens). Code sends the index, a three-line filter script, and 4 answer
lines (357 tokens):

```python
import retail_api as r
rows = [s for s in r.shifts() if str(s["Store"]).startswith("TX-0218") and str(s["Date"]) == "2026-09-10"]
for s in rows: print(f'{s["Full Name"]} {s["Role"]}: {s["Hours Booked"] or 0}h booked')
```

The model wrote that. `r.shifts()` pulled 167 rows inside the sandbox and only
the 4 matching lines came back. The saving also holds on joins and aggregations
(Q1, Q3, Q5), where Graph cannot help: the math runs in code, so the inputs never
hit context.

### Not specific to SharePoint

SharePoint is just the source this repo tested. The same pattern fits anything an
MCP server fronts: wrap the source in a typed code API, let the model compute
against it in a sandbox, return only the answer.

| Source | Code API handles | Would otherwise land in context |
|---|---|---|
| Postgres / MySQL / BigQuery / Snowflake | query and aggregate in SQL or the sandbox | full result sets, wide `SELECT *` rows |
| Salesforce / HubSpot / other CRM | SOQL and object filters | every Account, Contact, Deal record |
| REST / GraphQL APIs | paginate and join across endpoints | whole paginated JSON payloads |
| Google Sheets / Drive / S3 files | load and filter files | entire spreadsheets, CSVs, documents |
| Jira / Linear / GitHub | issue and PR queries | full issue lists with descriptions |
| Elasticsearch / log stores | search and roll up | raw matching documents |

The mechanism is the same everywhere: the bytes move through sandbox memory
instead of the context window. Sources that push work server-side (a SQL
`GROUP BY`, a SOQL filter) save on both the pull and the local compute. Sources
that cannot (flat files, APIs without aggregation) still save on the return,
since only the answer comes back.

### Making it better: index the metadata

`manifest.py` currently hardcodes one flat API index covering every list. That is
fine for 5 to 7 lists. It breaks at scale, when a source has hundreds of tables,
objects, or endpoints with dozens of fields each, because the index itself grows
large enough to bloat the context. That is the problem the approach set out to
avoid.

The fix is progressive disclosure over a metadata catalog instead of one static
blob:

1. **Index metadata, not data.** Build a catalog of `{name, description, field
   names and types, row count}` for every table, object, or endpoint. Generate it
   once from the source's schema (SQL `information_schema`, a CRM describe call,
   an OpenAPI spec, a sheet header scan) rather than writing it by hand. This is
   the searchable surface.
2. **Discover, then load.** The model queries the catalog first
   (`search_lists("revenue")` returns a few candidate lists with their columns),
   then pulls in the typed API only for those lists. It never loads the surface
   for the lists it does not touch.
3. **Descriptions carry weight.** A one-line description per list ("daily
   per-employee KPI scores vs target") lets the model pick the right list without
   sampling rows, which is what most often decides whether its first script is
   correct.

With this, context cost scales with the number of lists a question touches rather
than the number of lists that exist. `manifest.py` becomes generated output of a
schema crawl instead of a hand-maintained constant, and the same catalog grounds
the model well enough to cut wrong-list and wrong-column mistakes.

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
`Test_Team`. They are not in the repo; they lived in SharePoint.

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
\* The Graph column is the best case, assuming this data were SharePoint **Lists**.

## What it shows

- **Code execution wins on every question.** About 97% fewer tokens on live data,
  99.8% on the generated set. The difference is only that the live tables are
  small (16 to 240 rows), so there is less to save. The mechanism is the same.
- **Graph depends on the question type.** It helps on filters and top-N (Q6 -97%,
  Q1/Q2/Q4 around -60 to -67%), which are `$filter` and `$orderby`+`$top` pushed
  server-side. It does nothing on the aggregate-and-join questions (Q3, Q5),
  because OData has no server-side GROUP BY and no cross-list JOIN. These are the
  limits the article describes.
- **The catch on this tenant:** the data is stored as Excel files in a document
  library, not as Lists. Graph's Workbook API cannot return only the matching
  rows, so real Graph-on-Excel ties Direct on all six questions. The 50% Graph
  figure is the optimistic "if they had used Lists" case.

## Files

| File | Role |
|---|---|
| `generate_data.py` | writes the 5 synthetic lists into `sharepoint_lists/` |
| `sharepoint_api/__init__.py` | code-execution API over the local lists |
| `manifest.py` | compact API index the model sees |
| `queries.py` | the 6 generated-data questions, three ways each |
| `harness.py` | runs and measures the generated benchmark, writes `results.json` |
| `graph_client.py` | Graph auth and fetch `.xlsx` from the live library |
| `retail_api.py` | typed API over the live retail files |
| `inspect_data.py` | prints live schema and sample rows |
| `real_benchmark.py` | runs and measures the live benchmark, writes `real_results.json` |
| `report.html` | visual report (published as a Claude Artifact) |

## Reconstruction note

This project was deleted and rebuilt from the Claude Code session transcript.
Recovered: all source files, the generated data (regenerated), and the measured
live results. Not recovered: the original `.env` secret values (masked in the
transcript, so use `.env.example`), the live `*.xlsx` source files (they lived in
SharePoint), and `sharepoint_test.py` (a pre-existing credential-test script that
was never captured in full).
