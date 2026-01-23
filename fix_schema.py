import json

# Load your unified schema
with open('unified_schema.json', 'r') as f:
    schema = json.load(f)

# Fix the COMBO chart's x-axis to include timeGrain
for page in schema['pages']:
    for visual in page['visuals']:
        if visual['type'] == 'COMBO':
            # Convert simple string x-axis to object with timeGrain
            if isinstance(visual['x'][0], str):
                visual['x'] = [
                    {
                        "column": visual['x'][0],
                        "timeGrain": "DAY"  # Change to "MONTH" if you want monthly
                    }
                ]
            print(f"Fixed COMBO chart: {visual['title']}")

# Save the fixed schema
with open('unified_schema_fixed.json', 'w') as f:
    json.dump(schema, f, indent=2)

print("\nFixed schema saved to: unified_schema_fixed.json")
print("Now use this file for deployment!")