"""Shared live-SharePoint helper: auth + fetch Mock_Data Excel files via Graph.

Reads credentials from .env (AZURE_TENANT_ID / CLIENT_ID / CLIENT_SECRET).
Downloads each .xlsx from Test_Team > Mock_Data and returns its rows as dicts.
Workbooks are cached in memory for the process so we fetch each file once.
"""
import io
import os
from functools import lru_cache

import msal
import requests
from dotenv import load_dotenv
from openpyxl import load_workbook

load_dotenv()
GRAPH = "https://graph.microsoft.com/v1.0"
SITE_SEARCH = "Test_Team"
LIBRARY = "Mock_Data"


@lru_cache(maxsize=1)
def _token():
    app = msal.ConfidentialClientApplication(
        os.environ["AZURE_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}",
        client_credential=os.environ["AZURE_CLIENT_SECRET"],
    )
    r = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in r:
        raise SystemExit(f"Token failed: {r.get('error_description')}")
    return r["access_token"]


def _get(url, params=None):
    r = requests.get(url, headers={"Authorization": f"Bearer {_token()}"},
                     params=params, timeout=60)
    r.raise_for_status()
    return r


@lru_cache(maxsize=1)
def _drive_and_files():
    sid = _get(f"{GRAPH}/sites", {"search": SITE_SEARCH}).json()["value"][0]["id"]
    drives = _get(f"{GRAPH}/sites/{sid}/drives").json()["value"]
    drv = next(d["id"] for d in drives if d["name"] == LIBRARY)
    files = {f["name"]: f["id"]
             for f in _get(f"{GRAPH}/drives/{drv}/root/children").json()["value"]
             if f["name"].endswith(".xlsx")}
    return drv, files


@lru_cache(maxsize=None)
def raw_rows(filename):
    """All rows of a workbook's first sheet as a tuple of tuples (header first)."""
    drv, files = _drive_and_files()
    content = _get(f"{GRAPH}/drives/{drv}/items/{files[filename]}/content").content
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    return tuple(ws.iter_rows(values_only=True))


def records(filename, header_row=0):
    """Rows as list-of-dicts, using header_row as the column names."""
    rows = raw_rows(filename)
    headers = [str(h) for h in rows[header_row]]
    out = []
    for r in rows[header_row + 1:]:
        if all(c is None for c in r):
            continue
        out.append({h: v for h, v in zip(headers, r)})
    return out


def list_files():
    _, files = _drive_and_files()
    return sorted(files)
