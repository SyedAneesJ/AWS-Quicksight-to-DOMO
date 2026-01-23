import json
import requests
from domo_client import DomoClient
from domo_adapter import DomoAdapter
from dataset_resolver import StaticDatasetResolver

PAGE_ID = "1015927758"
BASE_URL = "https://gwcteq-partner.domo.com"

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://gwcteq-partner.domo.com",
    "Referer": "https://gwcteq-partner.domo.com",
    "x-requested-with": "XMLHttpRequest",
    "x-csrf-token": "245b4006-1b3e-42c8-89b5-4efb1da46d3f",
    "x-domo-requestcontext": '{"clientToe":"I2PSJ32NTK-QINN8"}',
    "Cookie": "_pubweb_idc=gwcteq-partner_#_standard; SESSION_TOE=I2PSJ32NTK; redirectUrl=%2Fpage%2F1436968545; PLAY_SESSION=c36fa5593ab7be756ccf9fcecc80563927abcc89-isProxied=false; mbox=session#13c3c3650efc4a3b8a2e294c35e02c77#1768882730|PC#13c3c3650efc4a3b8a2e294c35e02c77.41_0#1832125670; _dsidv1=d4324bd5-6050-45c8-a97e-d0ad9833925b; csrf-token=245b4006-1b3e-42c8-89b5-4efb1da46d3f; DA-SID-prod5-gwcteq-partner=eyJjdXN0b21lcklkIjoiZ3djdGVxLXBhcnRuZXIiLCJleHBpcmF0aW9uIjoxNzY4OTE4Mzc5MDAwLCJobWFjU2lnbmF0dXJlIjoiYWEwYmFiOWU2YzA5OTQzZmVmNGYxYmM1ZDJiNzk3YzVjMjYxYjA0ZjY0NzllYjljYTRlMmFhYWM1ZTQ0YWU1MiIsInNpZCI6IjMzNGMyYTIzLWNhOGUtNDhhNS05MzNkLTI3MzY3ZDA3YmIyNCIsInRpbWVzdGFtcCI6MTc2ODg4OTU3OTAwMCwidG9lcyI6IlVOS05PV05TSUQiLCJ1c2VySWQiOiIxNTYxMjIzNDM0In0%3D"
}

# Broken card IDs from the error logs
BROKEN_CARDS = [
    "640327241",  # From the latest error
    "50198705",   # From previous error
]

print("=" * 80)
print("STEP 1: DELETE BROKEN CARDS")
print("=" * 80)

for card_id in BROKEN_CARDS:
    print(f"\n🗑️  Deleting card: {card_id}")
    url = f"{BASE_URL}/api/content/v3/cards/{card_id}"
    
    try:
        response = requests.delete(url, headers=HEADERS)
        if response.status_code in (200, 204):
            print(f"  ✅ Deleted successfully")
        elif response.status_code == 404:
            print(f"  ℹ️  Already deleted or not found")
        else:
            print(f"  ⚠️  Status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
print("STEP 2: DEPLOY FRESH CARDS")
print("=" * 80)

# Load UnifiedBISchema
with open("unified_schema.json") as f:
    unified_schema = json.load(f)

# Configure Domo client
domo_client = DomoClient(base_url=BASE_URL, headers=HEADERS)

# Dataset mapping
resolver = StaticDatasetResolver({
    "dataset_1": "2fb72869-5d70-43d9-83e2-932f93a45c7b"
})

# Deploy
adapter = DomoAdapter(domo_client, resolver, column_mapping={})

results = adapter.deploy_dashboard(
    unified_schema=unified_schema,
    page_id=PAGE_ID
)

# Summary
print("\n" + "=" * 80)
print("DEPLOYMENT SUMMARY")
print("=" * 80)

success_count = sum(1 for r in results if r["status"] == "SUCCESS")
failed_count = sum(1 for r in results if r["status"] == "FAILED")

print(f"\n✅ Successful: {success_count}")
print(f"❌ Failed: {failed_count}")

if failed_count > 0:
    print("\nFailed visuals:")
    for r in results:
        if r["status"] == "FAILED":
            print(f"  - {r['visual_id']}: {r['error']}")

print(f"\n🌐 View page: {BASE_URL}/page/{PAGE_ID}")
print("\n✅ Complete! Refresh your browser to see the new cards.")