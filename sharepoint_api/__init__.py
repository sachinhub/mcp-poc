"""Code-API over the SharePoint lists (the 'code execution with MCP' layer).

This is the filesystem of tools the article describes. Instead of each list's
full contents flowing through the model context, the model imports these typed
functions and runs them in the execution sandbox. Only the function's small
return value comes back to the model.

Each loader reads the matching .xlsx once and caches it.
"""
from functools import lru_cache
from pathlib import Path
from openpyxl import load_workbook

_ROOT = Path(__file__).parent.parent / "sharepoint_lists"


@lru_cache(maxsize=None)
def _load(list_name):
    wb = load_workbook(_ROOT / f"{list_name}.xlsx", read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = rows[0]
    return [dict(zip(headers, r)) for r in rows[1:]]


def get_list(list_name):
    """Return all rows of a SharePoint list as a list of dicts."""
    return list(_load(list_name))


# Convenience typed accessors (one per list) ---------------------------------
def stores():      return _load("Stores")
def suppliers():   return _load("Suppliers")
def products():    return _load("Products")
def inventory():   return _load("Inventory")
def sales():       return _load("Sales")
