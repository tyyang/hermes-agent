"""Deterministic generator for task_large_data_pipeline (own LCG: stable across Python versions)."""
import sys

state = 20261113


def rnd():
    global state
    state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
    return state >> 33


REGIONS = ["north", "south", "east", "west", "central"]
PRODUCTS = [f"SKU-{i:03d}" for i in range(1, 21)]
STATUSES = ["completed"] * 17 + ["refunded", "cancelled", "completed"]

with open(sys.argv[1], "w", newline="") as f:
    f.write("order_id,date,region,product,units,unit_price,status\n")
    for i in range(1, 200_001):
        month = 1 + rnd() % 12
        day = 1 + rnd() % 28
        region = REGIONS[rnd() % len(REGIONS)]
        prod = PRODUCTS[rnd() % len(PRODUCTS)]
        units = 1 + rnd() % 9
        price_cents = 199 + (rnd() % 9800) + (PRODUCTS.index(prod) * 37)
        status = STATUSES[rnd() % len(STATUSES)]
        f.write(f"{i},2025-{month:02d}-{day:02d},{region},{prod},{units},{price_cents / 100:.2f},{status}\n")
