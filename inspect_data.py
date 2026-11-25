"""Print the real schema: header + 2 sample rows for each retail file."""
from graph_client import raw_rows

FILES = [
    "Store Network Register.xlsx",
    "Employee Directory.xlsx",
    "Attendance Register 2026.xlsx",
    "Shift Schedule Register.xlsx",
    "Store Employee Scorecards.xlsx",
    "Store Incentive Register.xlsx",
    "Store KPI Register.xlsx",
]

for name in FILES:
    rows = raw_rows(name)
    print(f"\n### {name}")
    for r in rows[:3]:
        print("   ", [("" if v is None else v) for v in r])
