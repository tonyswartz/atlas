#!/usr/bin/env python3
"""Import Spoolman data to JeevesUI via API."""

import json
import urllib.request
import urllib.error

CATALOG_URL = "http://localhost:3000/api/filament/catalog"
SPOOLS_URL = "http://localhost:3000/api/filament/spools"

def import_data():
    with open("/Users/printer/atlas/data/spoolman-export.json") as f:
        spools = json.load(f)

    filament_map = {}  # Spoolman filament_id -> JeevesUI filament id

    # First pass: create unique filaments
    for spool in spools:
        f = spool["filament"]
        sm_filament_id = str(f["id"])
        
        if sm_filament_id in filament_map:
            continue

        source = "bambu" if f["vendor"]["name"] == "Bambu Lab" else "sunlu"
        product_id = f.get("external_id", f"{source}_{f['name'].lower().replace(' ', '_')}")
        color_hex = f.get("color_hex")

        data = {
            "source": source,
            "productId": product_id,
            "name": f["name"],
            "brand": f["vendor"]["name"],
            "material": f["material"],
            "colorHex": color_hex,
            "colorName": f["name"],
            "weightG": int(f.get("weight", 1000)),
        }

        try:
            req = urllib.request.Request(
                CATALOG_URL,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    filament_map[sm_filament_id] = json.loads(resp.read().decode()).get("id")
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Already exists, fetch it
                try:
                    req = urllib.request.Request(
                        f"{CATALOG_URL}?source={source}",
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        catalog = json.loads(resp.read().decode())
                        for filament in catalog:
                            if filament.get("source") == source and filament.get("productId") == product_id:
                                filament_map[sm_filament_id] = filament["id"]
                                break
                except Exception:
                    pass
        except Exception as e:
            print(f"Error creating filament {sm_filament_id}: {e}")

    # Second pass: create spools
    created = 0
    for spool in spools:
        f = spool["filament"]
        sm_filament_id = str(f["id"])
        filament_id = filament_map.get(sm_filament_id)
        
        if not filament_id:
            print(f"Skipping spool {spool['id']} - no filament mapping")
            continue

        data = {
            "filamentId": filament_id,
            "initialWeightG": int(spool.get("initial_weight", 1000)),
            "pricePaid": spool.get("price"),
        }

        try:
            req = urllib.request.Request(
                SPOOLS_URL,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    created += 1
        except urllib.error.HTTPError as e:
            if e.code == 409:
                print(f"Spool for filament {sm_filament_id} already exists")
            else:
                print(f"Error creating spool: {e}")
        except Exception as e:
            print(f"Error creating spool: {e}")

    print(f"Imported {len(spools)} spools, {len(filament_map)} unique filaments, {created} new spools")

if __name__ == "__main__":
    import_data()
