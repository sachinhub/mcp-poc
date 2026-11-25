# I gave an AI agent the same data three ways. One was 600x cheaper.

Anthropic published a piece called [Code Execution with MCP](https://www.anthropic.com/research/code-execution-with-mcp) that makes a narrow claim: when an AI agent works with your data, a lot of the cost is just the reading. Every row the model pulls into context costs money and time, and agents tend to pull in way more than they need.

I wanted to measure it on data that looks like a real company's, so I built a small test.

## The setup

Five Excel files, the kind sitting in SharePoint at most retail companies: Stores, Suppliers, Products, Inventory, and Sales. The Sales table had 4,000 rows.

Six questions a normal person at that company might ask: top 5 products by revenue, how many items are below their reorder point, revenue by region, which clearance products are still selling, how reliable the suppliers are behind the best category, and one store's sales for one month.

I answered each question three ways.

**Direct.** The tool hands the model the whole Sales list, all 4,000 rows, and it works from there.

**Microsoft Graph.** Graph is the official SharePoint API. You ask the server to filter the data before it sends it, using a query language called OData. The server trims the list, the model reads less.

**Code execution.** The Anthropic approach. You give the model a short list of functions instead of data. It writes a few lines of code, the code runs next to the data, and only the answer comes back.

I ran all three and counted tokens, which is just how much text the model had to read. Every path returned the same answers. Only the reading changed.

## The numbers

| | Direct | Graph | Code execution |
|---|--:|--:|--:|
| All six questions | 1,331,640 | 1,070,145 | **2,112** |

Direct made the model read 1.3 million tokens. Code execution: 2,112, a 99.8% cut. That lines up with what Anthropic reported.

The number I didn't expect was Graph. I assumed the official filtered API would land somewhere in the middle. It cut the reading by 19.6%.

## Why Graph came up short

Graph is built for one shape of question: "give me the rows where this column equals this value." Store 1004. March. Clearance items. For that it works well. My sixth question was exactly that, "store 1004's March sales," and Graph trimmed 4,000 rows to 16 on the server. A 99.6% cut, about the same as code execution.

The other five questions weren't that shape. They total, combine, or compare, and Graph can't do those.

It can't total. "Revenue by region" needs every sale added up, and Graph has no way to sum on the server, so all 4,000 rows come over and the model does the math.

It can't join two lists. Revenue by region means matching Sales (store IDs) to Stores (regions). Graph won't connect two lists, so both arrive whole.

It can't compare two columns in a row. "Below reorder point" means stock against the reorder level, one column against another. Graph only compares a column to a value you type in, so it can't express the question at all. The whole inventory ships.

There's also a limit a bigger dataset would hit that mine didn't: SharePoint won't filter a list past 5,000 items unless the column was indexed in advance. Real sales tables are well past that, so the simple filters that worked here would often fail.

So on anything that totals, joins, or compares, Graph sends the full list and the model reads about as much as it would with no API at all.

## What code execution did differently

The work ran next to the data instead of inside the model. For "revenue by region," the generated code loops the sales, sums them, matches each store to its region, and prints five numbers. The model never sees the 4,000 rows, just the five lines of output.

It isn't free. You need a safe place to run the code, and the model has to write code that works, so a mistake shows up as a broken script instead of a quietly wrong answer. For heavy questions over big tables, that trade paid off here. For a one-row lookup, Graph is simpler and fine.

## I tried it on a real tenant too

The numbers above come from generated data, so I pointed the same three approaches at an actual company SharePoint through Microsoft Graph. The data there was a retail workforce set: stores, employees, shifts, scorecards, incentives, with 16 to 240 rows per file rather than thousands. Six questions again, read-only.

Code execution cut the reading by 97%, steady across every question. Lower than the 99.8% from the big generated table, which is exactly what you'd expect: less data, less to save. Graph came in at 50% overall, and it split along the same line as before. It helped on the simple-shaped questions (filter one column, or take the top five), up to 97% on a single-store lookup. It did nothing, 0%, on the two questions that totalled and combined across files. Same behaviour, now on live data.

One thing the real tenant made obvious that my demo had hidden. The data there wasn't in SharePoint Lists at all. It was Excel files sitting in a document library, which is how a lot of "SharePoint data" actually lives. Graph can read those files, but it can't hand back only the rows you asked for the way it can for a List. So the 50% Graph looked like it was saving mostly evaporates: against Excel files it ends up reading about as much as the naive approach. Code execution didn't care either way, because it just fetches the file once and does the work next to it.

## Where this leaves me

For simple lookups, a filtered API like Graph does the job. For questions that total, join, or compare, it didn't help much in my test, and those also happened to be the expensive ones. Code execution was the only option that stayed cheap across all six.

Worth saying what this is and isn't. It's a small test on generated data, six questions, one domain. The direct numbers assume whole-list returns, which is the default but not the only way to wire it up. I'd want to run it against a real SharePoint tenant with real volumes before treating 99.8% as a number to quote. But the direction was consistent enough that I'll reach for code execution first next time an agent needs to work over a lot of rows.

*Built as a proof of concept with generated retail data. Data, code, and measurements reproduce in a couple of minutes.*
