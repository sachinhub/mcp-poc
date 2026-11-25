"""Generate retail-domain Excel files that mimic SharePoint lists.

Each .xlsx = one SharePoint list. These are the shared data layer both
approaches (direct vs code-execution) read from.
"""
import random
from pathlib import Path
from openpyxl import Workbook

random.seed(42)
OUT = Path(__file__).parent / "sharepoint_lists"
OUT.mkdir(exist_ok=True)


def write_list(name, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = name
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(OUT / f"{name}.xlsx")
    print(f"  {name}.xlsx  ({len(rows)} rows)")


# ---- Stores ----------------------------------------------------------------
REGIONS = ["North", "South", "East", "West", "Central"]
CITIES = {
    "North": ["Seattle", "Portland", "Minneapolis"],
    "South": ["Dallas", "Houston", "Atlanta"],
    "East": ["Boston", "New York", "Philadelphia"],
    "West": ["Los Angeles", "San Diego", "Phoenix"],
    "Central": ["Chicago", "Denver", "Kansas City"],
}
stores = []
sid = 1000
for region in REGIONS:
    for city in CITIES[region]:
        stores.append([
            sid, f"{city} Flagship", city, region,
            random.choice(["Mall", "Street", "Outlet"]),
            random.randint(1800, 4200),  # sqft/100
            round(random.uniform(0.6, 0.98), 2),  # staffing ratio
        ])
        sid += 1
write_list("Stores",
           ["StoreID", "StoreName", "City", "Region", "Format", "AreaUnits", "StaffingRatio"],
           stores)
store_ids = [s[0] for s in stores]

# ---- Suppliers -------------------------------------------------------------
SUPPLIER_NAMES = ["Acme Textiles", "Globex Apparel", "Initech Footwear",
                  "Umbrella Goods", "Soylent Home", "Stark Supplies",
                  "Wayne Basics", "Oscorp Accessories"]
suppliers = []
for i, nm in enumerate(SUPPLIER_NAMES, start=1):
    suppliers.append([
        200 + i, nm,
        random.choice(["US", "CN", "IN", "VN", "MX"]),
        random.randint(5, 30),            # lead time days
        round(random.uniform(0.90, 0.995), 3),  # on-time rate
    ])
write_list("Suppliers",
           ["SupplierID", "SupplierName", "Country", "LeadTimeDays", "OnTimeRate"],
           suppliers)
supplier_ids = [s[0] for s in suppliers]

# ---- Products --------------------------------------------------------------
CATEGORIES = {
    "Apparel": ["T-Shirt", "Jeans", "Jacket", "Sweater", "Dress"],
    "Footwear": ["Sneakers", "Boots", "Sandals", "Loafers"],
    "Accessories": ["Belt", "Hat", "Scarf", "Wallet", "Sunglasses"],
    "Home": ["Towel Set", "Pillow", "Blanket", "Mug", "Candle"],
}
COLORS = ["Black", "White", "Navy", "Grey", "Red", "Green", "Beige"]
products = []
pid = 5000
for cat, names in CATEGORIES.items():
    for base in names:
        for color in random.sample(COLORS, 3):
            cost = round(random.uniform(4, 60), 2)
            price = round(cost * random.uniform(1.8, 3.2), 2)
            products.append([
                pid, f"{color} {base}", cat, base, color,
                cost, price, random.choice(supplier_ids),
                random.choice(["Active", "Active", "Active", "Clearance", "Discontinued"]),
            ])
            pid += 1
write_list("Products",
           ["ProductID", "ProductName", "Category", "Style", "Color",
            "UnitCost", "RetailPrice", "SupplierID", "Status"],
           products)
product_ids = [p[0] for p in products]

# ---- Inventory (Products x Stores sample) ----------------------------------
inventory = []
inv_id = 1
for store in store_ids:
    # each store stocks ~60% of catalogue
    for prod in random.sample(product_ids, int(len(product_ids) * 0.6)):
        on_hand = random.randint(0, 240)
        reorder = random.choice([20, 30, 40, 50])
        inventory.append([
            inv_id, store, prod, on_hand, reorder,
            random.randint(0, 60),  # on order
        ])
        inv_id += 1
write_list("Inventory",
           ["InventoryID", "StoreID", "ProductID", "OnHand", "ReorderPoint", "OnOrder"],
           inventory)

# ---- Sales (transaction lines) ---------------------------------------------
sales = []
order_id = 90000
MONTHS = [f"2025-{m:02d}" for m in range(1, 13)]
for _ in range(4000):
    store = random.choice(store_ids)
    prod = random.choice(product_ids)
    qty = random.randint(1, 6)
    month = random.choice(MONTHS)
    # pull price from product row
    prow = next(p for p in products if p[0] == prod)
    unit_price = prow[6]
    discount = random.choice([0, 0, 0, 0.1, 0.2])
    sales.append([
        order_id, month, store, prod, qty,
        unit_price, discount,
        round(qty * unit_price * (1 - discount), 2),
    ])
    order_id += 1
write_list("Sales",
           ["OrderLineID", "Month", "StoreID", "ProductID", "Qty",
            "UnitPrice", "Discount", "LineRevenue"],
           sales)

print("\nDone. Lists written to", OUT)
print(f"Totals: {len(stores)} stores, {len(suppliers)} suppliers, "
      f"{len(products)} products, {len(inventory)} inventory rows, {len(sales)} sales lines")
