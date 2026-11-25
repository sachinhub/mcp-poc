"""Compact tool manifest the model sees under the code-execution approach.

This is the 'progressive disclosure' index: a few hundred tokens describing
what's available, instead of dumping every list's full contents up front.
"""
API_INDEX = '''
# SharePoint lists exposed as a code API  (import from `sharepoint_api`)
#
# sharepoint_api.stores()    -> [{StoreID, StoreName, City, Region, Format, AreaUnits, StaffingRatio}]
# sharepoint_api.suppliers() -> [{SupplierID, SupplierName, Country, LeadTimeDays, OnTimeRate}]
# sharepoint_api.products()  -> [{ProductID, ProductName, Category, Style, Color, UnitCost, RetailPrice, SupplierID, Status}]
# sharepoint_api.inventory() -> [{InventoryID, StoreID, ProductID, OnHand, ReorderPoint, OnOrder}]
# sharepoint_api.sales()     -> [{OrderLineID, Month, StoreID, ProductID, Qty, UnitPrice, Discount, LineRevenue}]
#
# Write a short Python script that filters/joins/aggregates these in the
# sandbox and prints ONLY the final answer.
'''.strip()
