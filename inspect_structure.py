import json

def inspect_qs_structure(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        qs_dashboard = json.load(f)
    
    print("📊 QuickSight Dashboard Structure Inspection")
    print("=" * 60)
    
    definition = qs_dashboard.get("Definition", {})
    
    # List all sheets and their visual types
    for sheet in definition.get("Sheets", []):
        print(f"\n📄 Sheet: {sheet['Name']} ({sheet['SheetId']})")
        print("-" * 40)
        
        for i, visual in enumerate(sheet.get("Visuals", [])):
            visual_type = list(visual.keys())[0]
            visual_id = visual[visual_type]["VisualId"]
            print(f"  Visual {i+1}: {visual_type} ({visual_id})")
            
            # Show field wells structure for this visual
            config = visual[visual_type].get("ChartConfiguration", {})
            field_wells = config.get("FieldWells", {})
            
            if field_wells:
                print(f"    Field Wells keys: {list(field_wells.keys())}")
                
                # Show first level of structure for each field well
                for key, value in field_wells.items():
                    if isinstance(value, dict):
                        print(f"    - {key}: {list(value.keys())}")
                    elif isinstance(value, list):
                        print(f"    - {key}: list with {len(value)} items")
                    else:
                        print(f"    - {key}: {type(value).__name__}")

# Run the inspection
if __name__ == "__main__":
    filename = "extracted_dashboards/7e06829f-064a-4bbc-918a-d5c287edf0bc.qs.json"
    inspect_qs_structure(filename)