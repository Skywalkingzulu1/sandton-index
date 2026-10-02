import json
from collections import Counter

d = json.load(open("data/businesses.json", encoding="utf-8"))
recs = d["records"]

tier = Counter(r["tier"] for r in recs)
print(f"total records      : {len(recs)}")
print(f"  A no website     : {tier['A']}")
print(f"  B chain/no site  : {tier['B']}")
print(f"  C has website    : {tier['C']}")

# the defensible number: no website AND contactable
a = [r for r in recs if r["tier"] == "A"]
print(f"\ntier A breakdown:")
print(f"  with phone       : {sum(1 for r in a if r['phone'])}")
print(f"  with address     : {sum(1 for r in a if r['street_address'] or r['building_name'])}")
print(f"  with hours       : {sum(1 for r in a if r['opening_hours'])}")
print(f"  phone + address  : {sum(1 for r in a if r['phone'] and (r['street_address'] or r['building_name']))}")

print(f"\ntop zones for tier A:")
for z, n in Counter(r["zone_display"] for r in a).most_common(6):
    print(f"  {n:>4}  {z}")

print(f"\ntop categories for tier A:")
hubs = Counter(r["hub_title"] for r in a)
for h, n in hubs.most_common(6):
    print(f"  {n:>4}  {h}")
