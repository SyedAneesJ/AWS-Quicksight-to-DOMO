# run_qs_to_unified.py
import json
from typing import Dict, Any
from calc_field_translator import normalize_qs_calc


# =========================================================
# Helper functions
# =========================================================
def extract_aggregation(value_entry: Dict) -> str:
    """Extract aggregation from QuickSight field entry"""
    agg = "SUM"  # default
    
    if "AggregationFunction" in value_entry:
        agg = value_entry["AggregationFunction"]
        if isinstance(agg, dict):
            agg = agg.get("SimpleNumericalAggregation", "SUM")
    
    return agg


def extract_column_name(value_entry: Dict) -> str:
    """Extract column name from QuickSight field entry"""
    if "CategoricalMeasureField" in value_entry:
        return value_entry["CategoricalMeasureField"]["Column"]["ColumnName"]
    elif "NumericalMeasureField" in value_entry:
        return value_entry["NumericalMeasureField"]["Column"]["ColumnName"]
    elif "CalculatedMeasureField" in value_entry:
        return value_entry["CalculatedMeasureField"]["Name"]
    else:
        raise KeyError(f"Unsupported measure field type: {list(value_entry.keys())}")


# =========================================================
# UnifiedBISchema v1.1 – QS → Unified Transformer (BAR + KPI + LINE)
# =========================================================
def transform_qs_dashboard_to_unified(qs_dashboard: Dict[str, Any]) -> Dict[str, Any]:
    definition = qs_dashboard.get("Definition", {})
    
    # -----------------------------
    # Datasets
    # -----------------------------
    datasets = []
    dataset_id_map = {}
    
    for idx, ds in enumerate(definition.get("DataSetIdentifierDeclarations", [])):
        uid = f"dataset_{idx + 1}"
        dataset_id_map[ds["Identifier"]] = uid
        datasets.append({
            "id": uid,
            "name": ds["Identifier"],
            "sourceArn": ds.get("DataSetArn")
        })
    
    # -----------------------------
    # Calculated Fields
    # -----------------------------
    calculated_fields = []
    for cf in definition.get("CalculatedFields", []):
        normalized = normalize_qs_calc(cf["Expression"])
        calculated_fields.append({
            "name": cf["Name"],
            "expression": normalized["row_expression"]
        })
    
    # -----------------------------
    # Pages & Visuals
    # -----------------------------
    pages = []
    
    for sheet in definition.get("Sheets", []):
        visuals = []
        
        for visual in sheet.get("Visuals", []):
            # ---------------- BAR CHART ----------------
            if "BarChartVisual" in visual:
                try:
                    bar = visual["BarChartVisual"]
                    fw = bar["ChartConfiguration"]["FieldWells"]["BarChartAggregatedFieldWells"]
                    
                    cat = fw["Category"][0]["CategoricalDimensionField"]
                    value_entry = fw["Values"][0]
                    
                    column_name = extract_column_name(value_entry)
                    aggregation = extract_aggregation(value_entry)
                    
                    visuals.append({
                        "id": bar["VisualId"],
                        "type": "BAR",
                        "title": sheet["Name"],
                        "datasetRef": dataset_id_map[cat["Column"]["DataSetIdentifier"]],
                        "x": [cat["Column"]["ColumnName"]],
                        "measures": [{
                            "column": column_name,
                            "aggregation": aggregation
                        }]
                    })
                except Exception as e:
                    print(f"⚠️ Error processing BAR chart: {e}")
                    continue
            
            # ---------------- KPI CHART ----------------
            elif "KPIVisual" in visual:
                try:
                    kpi = visual["KPIVisual"]
                    fw = kpi["ChartConfiguration"]["FieldWells"]
                    
                    if not fw.get("Values"):
                        continue
                    
                    value_entry = fw["Values"][0]
                    column_name = extract_column_name(value_entry)
                    aggregation = extract_aggregation(value_entry)
                    
                    # Get dataset identifier safely
                    if "CategoricalMeasureField" in value_entry:
                        dataset_identifier = value_entry["CategoricalMeasureField"]["Column"]["DataSetIdentifier"]
                    elif "NumericalMeasureField" in value_entry:
                        dataset_identifier = value_entry["NumericalMeasureField"]["Column"]["DataSetIdentifier"]
                    elif "CalculatedMeasureField" in value_entry:
                        dataset_identifier = value_entry["CalculatedMeasureField"].get("DataSetIdentifier", 
                                                                                     list(dataset_id_map.keys())[0])
                    else:
                        dataset_identifier = list(dataset_id_map.keys())[0]
                    
                    visuals.append({
                        "id": kpi["VisualId"],
                        "type": "KPI",
                        "title": f"{sheet['Name']} KPI",
                        "datasetRef": dataset_id_map[dataset_identifier],
                        "measures": [{
                            "column": column_name,
                            "aggregation": aggregation
                        }]
                    })
                except Exception as e:
                    print(f"⚠️ Error processing KPI chart: {e}")
                    continue
            
            # ---------------- LINE CHART ----------------
            elif "LineChartVisual" in visual:
                try:
                    line = visual["LineChartVisual"]
                    fw = line["ChartConfiguration"]["FieldWells"]["LineChartAggregatedFieldWells"]
                    
                    # Extract series (colors field)
                    series = None
                    colors = fw.get("Colors", [])
                    if colors:
                        color_field = colors[0].get("CategoricalDimensionField")
                        if color_field:
                            series = color_field["Column"]["ColumnName"]
                    
                    # Extract X-axis
                    cat = fw["Category"][0]["CategoricalDimensionField"]
                    x_col = cat["Column"]["ColumnName"]
                    dataset_identifier = cat["Column"]["DataSetIdentifier"]
                    
                    # Extract Y-axis value
                    value_entry = fw["Values"][0]
                    column_name = extract_column_name(value_entry)
                    aggregation = extract_aggregation(value_entry)
                    
                    visuals.append({
                        "id": line["VisualId"],
                        "type": "LINE",
                        "title": sheet["Name"],
                        "datasetRef": dataset_id_map[dataset_identifier],
                        "x": [x_col],
                        "series": series,
                        "measures": [{
                            "column": column_name,
                            "aggregation": aggregation
                        }]
                    })
                except Exception as e:
                    print(f"⚠️ Error processing LINE chart: {e}")
                    continue
        
        if visuals:
            pages.append({
                "id": sheet["SheetId"],
                "name": sheet["Name"],
                "visuals": visuals
            })
            print(f"✓ Processed sheet '{sheet['Name']}' with {len(visuals)} visuals")
        else:
            print(f"⚠️ No supported visuals found in sheet: {sheet['Name']}")
    
    # -----------------------------
    # UnifiedBISchema Output
    # -----------------------------
    unified_schema = {
        "schemaVersion": "1.1",
        "source": {
            "tool": "AWS QuickSight",
            "dashboardId": qs_dashboard.get("DashboardId"),
            "dashboardName": qs_dashboard.get("Name")
        },
        "datasets": datasets,
        "calculatedFields": calculated_fields,
        "pages": pages
    }
    
    # Print summary
    total_visuals = sum(len(p["visuals"]) for p in pages)
    print(f"\n📊 Transformation Summary:")
    print(f"  • Datasets: {len(datasets)}")
    print(f"  • Calculated Fields: {len(calculated_fields)}")
    print(f"  • Pages: {len(pages)}")
    print(f"  • Visuals: {total_visuals}")
    
    # Count by type
    visual_types = {}
    for page in pages:
        for visual in page["visuals"]:
            visual_type = visual["type"]
            visual_types[visual_type] = visual_types.get(visual_type, 0) + 1
    
    for vis_type, count in visual_types.items():
        print(f"    - {vis_type}: {count}")
    
    return unified_schema


# =========================================================
#  Main Runner
# =========================================================
if __name__ == "__main__":
    try:
        print("🚀 Starting QuickSight to UnifiedBISchema transformation...")
        
        with open("qs_dashboard.json", "r") as f:
            qs_dashboard = json.load(f)
        
        print(f"📁 Loaded QuickSight dashboard: {qs_dashboard.get('Name', 'Unknown')}")
        
        unified_schema = transform_qs_dashboard_to_unified(qs_dashboard)
        
        with open("unified_schema.json", "w") as f:
            json.dump(unified_schema, f, indent=2)
        
        print("\n✅ UnifiedBISchema generated: unified_schema.json")
        
    except FileNotFoundError:
        print("❌ Error: qs_dashboard.json not found!")
        print("Please ensure qs_dashboard.json exists in the current directory.")
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON format in qs_dashboard.json!")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")