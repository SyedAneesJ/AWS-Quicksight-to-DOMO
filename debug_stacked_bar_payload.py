import json
from domo_adapter import DomoAdapter
from dataset_resolver import StaticDatasetResolver

# Mock client that just returns the payload
class MockClient:
    def create_card(self, page_id, payload):
        return payload

# Load schema
with open("unified_schema.json", "r") as f:
    schema = json.load(f)

# Create adapter with mock client
resolver = StaticDatasetResolver({
    "dataset_1": "2fb72869-5d70-43d9-83e2-932f93a45c7b"
})

adapter = DomoAdapter(MockClient(), resolver)

# Find the stacked bar visual
stacked_bar_visual = None
for page in schema.get("pages", []):
    for visual in page.get("visuals", []):
        if visual.get("type") == "STACKED_BAR":
            stacked_bar_visual = visual
            break

if not stacked_bar_visual:
    print("❌ No STACKED_BAR visual found")
    exit()

print("=" * 80)
print("STACKED BAR VISUAL DEFINITION")
print("=" * 80)
print(json.dumps(stacked_bar_visual, indent=2))

print("\n" + "=" * 80)
print("GENERATED PAYLOAD FOR DOMO")
print("=" * 80)

payload = adapter._build_stacked_bar_payload(stacked_bar_visual)
print(json.dumps(payload, indent=2))

print("\n" + "=" * 80)
print("ANALYSIS")
print("=" * 80)

# Check the columns
columns = payload["definition"]["subscriptions"]["main"]["columns"]
print(f"\nColumns ({len(columns)}):")
for i, col in enumerate(columns):
    print(f"  {i+1}. {col.get('column')} - Mapping: {col.get('mapping')} - Agg: {col.get('aggregation', 'N/A')}")

# Check groupBy
groupBy = payload["definition"]["subscriptions"]["main"]["groupBy"]
print(f"\nGroupBy ({len(groupBy)}):")
for gb in groupBy:
    print(f"  - {gb.get('column')}")

print("\n" + "=" * 80)
print("EXPECTED STRUCTURE FOR STACKED BAR")
print("=" * 80)
print("""
For a stacked bar chart in Domo, we need:
1. ITEM mapping: The X-axis category (department)
2. SERIES mapping: The stack dimension (attendance_status)
3. VALUE mapping: The measure with aggregation (COUNT_DISTINCT employee_name)

The groupBy should include both ITEM and SERIES columns.
""")

print("\n💡 TIP: Compare this with a working stacked bar chart payload from Domo's UI")