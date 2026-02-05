#!/usr/bin/env python3
"""Update JeevesUI spools with price data from Spoolman export."""

import json
import urllib.request
import urllib.error

SPOOLS_URL = "http://localhost:3000/api/filament/spools"

def update_prices():
    with open("/Users/printer/atlas/data/spoolman-export.json") as f:
        spools = json.load(f)

    # First get all current spools
    with urllib.request.urlopen(SPOOLS_URL, timeout=10) as resp:
        current_spools = json.loads(resp.read().decode())

    # Create mapping: we need to match by filament source+productId
    # Spoolman export has "filament.external_id" we can match against JeevesUI's productId

    for sm_spool in spools:
        f = sm_spool["filament"]
        source = "bambu" if f["vendor"]["name"] == "Bambu Lab" else "sunlu"
        product_id = f.get("external_id")
        price = sm_spool.get("price")

        if not price:
            continue

        # Find matching JeevesUI spool
        for spool in current_spools:
            jeev_filament = spool.get("filament") or {}
            if jeev_filament.get("source") == source and jeev_filament.get("productId") == product_id:
                # Update price
                try:
                    req = urllib.request.Request(
                        f"{SPOOLS_URL}/{spool['id']}",
                        data=json.dumps({"pricePaid": price}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="PATCH",
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        print(f"Updated {jeev_filament.get('brand')} {jeev_filament.get('name')} with ${price}")
                except Exception as e:
                    print(f"Error updating {spool['id']}: {e}")
                break

if __name__ == "__main__":
    update_prices()
