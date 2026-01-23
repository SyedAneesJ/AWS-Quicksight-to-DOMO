import json
from typing import Dict, Any
from calc_field_translator import normalize_qs_calc



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
    # Calculated Fields (QS)
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
        bar_count = 0
        kpi_count = 0
        line_count = 0

        for visual in sheet.get("Visuals", []):

            # ---------------- BAR ----------------
            if "BarChartVisual" in visual:
                bar_count += 1
                bar = visual["BarChartVisual"]
                fw = bar["ChartConfiguration"]["FieldWells"]["BarChartAggregatedFieldWells"]

                cat = fw["Category"][0]["CategoricalDimensionField"]
                value_entry = fw["Values"][0]

                if "CategoricalMeasureField" in value_entry:
                    val = value_entry["CategoricalMeasureField"]
                    column_name = val["Column"]["ColumnName"]
                    aggregation = val.get("AggregationFunction", "SUM")

                elif "NumericalMeasureField" in value_entry:
                    val = value_entry["NumericalMeasureField"]
                    column_name = val["Column"]["ColumnName"]
                    aggregation = val.get("AggregationFunction", "SUM")

                elif "CalculatedMeasureField" in value_entry:
                    val = value_entry["CalculatedMeasureField"]
                    column_name = val["Name"]
                    aggregation = val.get("AggregationFunction", "SUM")

                else:
                    raise KeyError(
                        f"Unsupported measure field type in BAR: {value_entry.keys()}"
                    )

                visuals.append({
                    "id": bar["VisualId"],
                    "type": "BAR",
                    "title": sheet["Name"],
                    "datasetRef": dataset_id_map[
                        cat["Column"]["DataSetIdentifier"]
                    ],
                    "x": [cat["Column"]["ColumnName"]],
                    "measures": [
                        {
                            "column": column_name,
                            "aggregation": aggregation
                        }
                    ]

                })

            # ---------------- KPI ----------------
            if "KPIVisual" in visual:
                kpi_count += 1
                kpi = visual["KPIVisual"]
                fw = kpi["ChartConfiguration"]["FieldWells"]

                if not fw.get("Values"):
                    continue

                value_entry = fw["Values"][0]

                if "CategoricalMeasureField" in value_entry:
                    val = value_entry["CategoricalMeasureField"]
                    column_name = val["Column"]["ColumnName"]
                    aggregation = val.get("AggregationFunction", "SUM")

                elif "NumericalMeasureField" in value_entry:
                    val = value_entry["NumericalMeasureField"]
                    column_name = val["Column"]["ColumnName"]
                    aggregation = val.get("AggregationFunction", "SUM")

                elif "CalculatedMeasureField" in value_entry:
                    val = value_entry["CalculatedMeasureField"]
                    column_name = val["Name"]
                    aggregation = val.get("AggregationFunction", "SUM")

                else:
                    raise KeyError(
                        f"Unsupported measure field type in KPI: {value_entry.keys()}"
                    )


                # Resolve dataset identifier safely (works for physical + calculated fields)
                dataset_identifier = (
                    val.get("Column", {}).get("DataSetIdentifier")
                    if "Column" in val
                    else list(dataset_id_map.keys())[0]
                )


                visuals.append({
                    "id": kpi["VisualId"],
                    "type": "KPI",
                    "title": sheet["Name"] + " KPI",
                    "datasetRef": dataset_id_map[dataset_identifier],
                    "measures": [
                        {
                            "column": column_name,
                            "aggregation": aggregation
                        }
                    ]
                })

            # ---------------- LINE ----------------
            if "LineChartVisual" in visual:
                line_count += 1
                line = visual["LineChartVisual"]
                fw = line["ChartConfiguration"]["FieldWells"]["LineChartAggregatedFieldWells"]

                # X-axis
                cat = fw["Category"][0]["CategoricalDimensionField"]
                x_col = cat["Column"]["ColumnName"]
                dataset_identifier = cat["Column"]["DataSetIdentifier"]

                # Y-axis (single metric only – v1.0)
                value_entry = fw["Values"][0]

                if "CategoricalMeasureField" in value_entry:
                    val = value_entry["CategoricalMeasureField"]
                    column_name = val["Column"]["ColumnName"]
                    aggregation = val.get("AggregationFunction", "SUM")

                elif "CalculatedMeasureField" in value_entry:
                    val = value_entry["CalculatedMeasureField"]
                    column_name = val["Name"]
                    aggregation = val.get("AggregationFunction", "SUM")

                elif "NumericalMeasureField" in value_entry:
                    val = value_entry["NumericalMeasureField"]
                    column_name = val["Column"]["ColumnName"]
                    aggregation = "SUM"   # QS implicit aggregation

                else:
                    raise KeyError(
                        f"Unsupported measure field type in LINE: {value_entry.keys()}"
                    )

                visuals.append({
                    "id": line["VisualId"],
                    "type": "LINE",
                    "title": sheet["Name"],
                    "datasetRef": dataset_id_map[dataset_identifier],
                    "x": [x_col],
                    "measures": [
                        {
                            "column": column_name,
                            "aggregation": aggregation
                        }
                    ]
                })


        if visuals:
            pages.append({
                "id": sheet["SheetId"],
                "name": sheet["Name"],
                "visuals": visuals
            })

        if bar_count == 0 and kpi_count == 0 and line_count == 0:
            print(f"⚠️ No supported visuals found in sheet: {sheet['Name']}")
    # -----------------------------
    # UnifiedBISchema Output
    # -----------------------------
    return {
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



# =========================================================
#  Main Runner
# =========================================================
if __name__ == "__main__":
    with open("qs_dashboard.json", "r") as f:
        qs_dashboard = json.load(f)

    unified_schema = transform_qs_dashboard_to_unified(qs_dashboard)

    with open("unified_schema.json", "w") as f:
        json.dump(unified_schema, f, indent=2)

    print("✅ UnifiedBISchema generated: unified_schema.json")
