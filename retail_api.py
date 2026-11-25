"""Typed API over the live Test_Team > Mock_Data retail files.

Thin wrapper on graph_client so benchmark code reads cleanly and the API
index shown to the model stays small. Each call fetches once (cached).
"""
import graph_client as gc

STORE_FILE = "Store Network Register.xlsx"


def stores():      return gc.records("Store Network Register.xlsx")
def employees():   return gc.records("Employee Directory.xlsx")
def attendance():  return gc.records("Attendance Register 2026.xlsx")
def shifts():      return gc.records("Shift Schedule Register.xlsx")
def scorecards():  return gc.records("Store Employee Scorecards.xlsx")
def incentives():  return gc.records("Store Incentive Register.xlsx")
def store_kpis():  return gc.records("Store KPI Register.xlsx")


def store_of(emp_or_store):
    """Derive the Store ID (e.g. 'TX-0218') from a store-employee ID like
    'TX-0218-E1' or a Shift 'Store' value like 'TX-0218 Plano Preston Rd'."""
    s = str(emp_or_store)
    if "-E" in s:
        return s.rsplit("-E", 1)[0]
    return s.split(" ", 1)[0]
