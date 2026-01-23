import json
from typing import Dict, Any, Optional
from calc_field_translator import normalize_qs_calc


# =========================================================
# Helper: Safe first element access
# =========================================================
def safe_first(lst, default=None):
    """Safely get first element from list or return default"""
    return lst[0] if lst and len(lst) > 0 else default


# =========================================================
# Helper: Extract Dimension Field (SAFE)
# =========================================================
def extract_dimension_field(dim_entry: dict):
    if not dim_entry:
        return None
    
    if "CategoricalDimensionField" in dim_entry:
        field = dim_entry["CategoricalDimensionField"]
    elif "DateDimensionField" in dim_entry:
        field = dim_entry["DateDimensionField"]
    elif "NumericalDimensionField" in dim_entry:
        field = dim_entry["NumericalDimensionField"]
    else:
        raise KeyError(
            f"Unsupported dimension field type: {dim_entry.keys()}"
        )

    return {
        "column_name": field["Column"]["ColumnName"],
        "dataset_identifier": field["Column"]["DataSetIdentifier"]
    }


# =========================================================
# Helper: Extract Measure Field
# =========================================================
def extract_measure_field(measure_entry: dict):
    """Extract measure field from various QuickSight measure types"""
    if not measure_entry:
        return None
    
    if "CategoricalMeasureField" in measure_entry:
        val = measure_entry["CategoricalMeasureField"]
        return {
            "column_name": val["Column"]["ColumnName"],
            "aggregation": val.get("AggregationFunction", "COUNT"),
            "dataset_identifier": val["Column"]["DataSetIdentifier"]
        }
    elif "NumericalMeasureField" in measure_entry:
        val = measure_entry["NumericalMeasureField"]
        return {
            "column_name": val["Column"]["ColumnName"],
            "aggregation": val.get("AggregationFunction", "SUM"),
            "dataset_identifier": val["Column"]["DataSetIdentifier"]
        }
    elif "CalculatedMeasureField" in measure_entry:
        val = measure_entry["CalculatedMeasureField"]
        return {
            "column_name": val["Name"],
            "aggregation": val.get("AggregationFunction", "SUM"),
            "dataset_identifier": ""
        }
    else:
        raise KeyError(f"Unsupported measure field type: {measure_entry.keys()}")


# =========================================================
# Helper: Resolve Calculated Field to Base Column
# =========================================================
def resolve_calculated_field(calc_field_name: str, calculated_fields: list) -> str:
    """
    If a calculated field is just a simple column reference like {working_hours},
    return the base column name. Otherwise return the calculated field name.
    """
    for cf in calculated_fields:
        if cf["Name"] == calc_field_name:
            expr = cf["Expression"].strip()
            # Check if it's just a simple column reference: {column_name}
            if expr.startswith("{") and expr.endswith("}") and expr.count("{") == 1:
                base_column = expr[1:-1]  # Remove { and }
                print(f"  📄 Resolved calculated field '{calc_field_name}' -> '{base_column}'")
                return base_column
    return calc_field_name

def normalize_aggregation(aggregation):
    if isinstance(aggregation, dict):
        return aggregation.get("SimpleNumericalAggregation", "SUM")
    return aggregation

# HELPER FOR CHECKING AREA CHART
def is_area_chart(line_visual: dict) -> bool:
    config = line_visual.get("ChartConfiguration", {})
    chart_type = config.get("Type")
    return chart_type in ["AREA", "STACKED_AREA"]


# =========================================================
# Helper: Extract Scatter Plot Fields
# =========================================================
def extract_scatter_fields(scatter_visual: dict, qs_calculated_fields: list):
    """Extract fields from scatter plot visual"""
    fw = scatter_visual["ChartConfiguration"]["FieldWells"]["ScatterPlotCategoricallyAggregatedFieldWells"]
    
    # X Axis
    x_field = None
    x_entries = fw.get("XAxis", [])
    if x_entries:
        x_entry = x_entries[0]
        if "NumericalMeasureField" in x_entry:
            val = x_entry["NumericalMeasureField"]
            x_field = {
                "column": val["Column"]["ColumnName"],
                "aggregation": val.get("AggregationFunction", "SUM"),
                "dataset_identifier": val["Column"]["DataSetIdentifier"]
            }
        elif "CalculatedMeasureField" in x_entry:
            val = x_entry["CalculatedMeasureField"]
            column_name = resolve_calculated_field(val["Name"], qs_calculated_fields)
            x_field = {
                "column": column_name,
                "aggregation": val.get("AggregationFunction", "SUM"),
                "dataset_identifier": ""
            }
    
    # Y Axis
    y_field = None
    y_entries = fw.get("YAxis", [])
    if y_entries:
        y_entry = y_entries[0]
        if "NumericalMeasureField" in y_entry:
            val = y_entry["NumericalMeasureField"]
            y_field = {
                "column": val["Column"]["ColumnName"],
                "aggregation": val.get("AggregationFunction", "SUM"),
                "dataset_identifier": val["Column"]["DataSetIdentifier"]
            }
        elif "CalculatedMeasureField" in y_entry:
            val = y_entry["CalculatedMeasureField"]
            column_name = resolve_calculated_field(val["Name"], qs_calculated_fields)
            y_field = {
                "column": column_name,
                "aggregation": val.get("AggregationFunction", "SUM"),
                "dataset_identifier": ""
            }
    
    # Size (for bubble charts)
    size_field = None
    size_entries = fw.get("Size", [])
    if size_entries:
        size_entry = size_entries[0]
        if "NumericalMeasureField" in size_entry:
            val = size_entry["NumericalMeasureField"]
            size_field = {
                "column": val["Column"]["ColumnName"],
                "aggregation": val.get("AggregationFunction", "AVG"),
                "dataset_identifier": val["Column"]["DataSetIdentifier"]
            }
        elif "CalculatedMeasureField" in size_entry:
            val = size_entry["CalculatedMeasureField"]
            column_name = resolve_calculated_field(val["Name"], qs_calculated_fields)
            size_field = {
                "column": column_name,
                "aggregation": val.get("AggregationFunction", "AVG"),
                "dataset_identifier": ""
            }
    
    # Category/Color (for grouping)
    category_fields = []
    category_entries = fw.get("Category", [])
    for category_entry in category_entries:
        if "CategoricalDimensionField" in category_entry:
            field = category_entry["CategoricalDimensionField"]
            category_fields.append({
                "column": field["Column"]["ColumnName"],
                "dataset_identifier": field["Column"]["DataSetIdentifier"]
            })
        elif "NumericalDimensionField" in category_entry:
            field = category_entry["NumericalDimensionField"]
            category_fields.append({
                "column": field["Column"]["ColumnName"],
                "dataset_identifier": field["Column"]["DataSetIdentifier"]
            })
    
    return x_field, y_field, size_field, category_fields


# =========================================================
# Helper: Extract Pie Chart Fields
# =========================================================
def extract_pie_chart_fields(pie_visual: dict, qs_calculated_fields: list):
    """Extract fields from pie chart visual"""
    fw = pie_visual["ChartConfiguration"]["FieldWells"]["PieChartAggregatedFieldWells"]
    
    # Category/Group By
    category_field = None
    category_entries = fw.get("Category", [])
    if category_entries:
        category_entry = category_entries[0]
        dim_info = extract_dimension_field(category_entry)
        if dim_info:
            category_field = {
                "column": dim_info["column_name"],
                "dataset_identifier": dim_info["dataset_identifier"]
            }
    
    # Values
    value_field = None
    value_entries = fw.get("Values", [])
    if value_entries:
        value_entry = value_entries[0]
        if "CategoricalMeasureField" in value_entry:
            val = value_entry["CategoricalMeasureField"]
            value_field = {
                "column": val["Column"]["ColumnName"],
                "aggregation": val.get("AggregationFunction", "COUNT"),
                "dataset_identifier": val["Column"]["DataSetIdentifier"]
            }
        elif "NumericalMeasureField" in value_entry:
            val = value_entry["NumericalMeasureField"]
            value_field = {
                "column": val["Column"]["ColumnName"],
                "aggregation": val.get("AggregationFunction", "SUM"),
                "dataset_identifier": val["Column"]["DataSetIdentifier"]
            }
        elif "CalculatedMeasureField" in value_entry:
            val = value_entry["CalculatedMeasureField"]
            column_name = resolve_calculated_field(val["Name"], qs_calculated_fields)
            value_field = {
                "column": column_name,
                "aggregation": val.get("AggregationFunction", "SUM"),
                "dataset_identifier": ""
            }
    
    return category_field, value_field

# Helper function to detect donut vs pie
def is_donut_chart(pie_visual: dict) -> bool:
    """Check if a PieChartVisual is actually a donut chart"""
    config = pie_visual.get("ChartConfiguration", {})
    donut_options = config.get("DonutOptions", {})
    arc_options = donut_options.get("ArcOptions", {})
    arc_thickness = arc_options.get("ArcThickness", "WHOLE")
    
    # If ArcThickness is not "WHOLE", it's a donut chart
    # MEDIUM, THIN, etc. indicate donut
    return arc_thickness != "WHOLE"


# =========================================================
# NEW: Helper to Extract Combo Chart Fields
# =========================================================
def extract_combo_chart_fields(combo_visual: dict, qs_calculated_fields: list):
    """Extract fields from combo chart visual (bar + line)"""
    fw = combo_visual["ChartConfiguration"]["FieldWells"]["ComboChartAggregatedFieldWells"]
    
    # Category (X-axis)
    category_field = None
    category_entries = fw.get("Category", [])
    if category_entries:
        dim_info = extract_dimension_field(category_entries[0])
        if dim_info:
            category_field = {
                "column": dim_info["column_name"],
                "dataset_identifier": dim_info["dataset_identifier"]
            }
    
    # Bar Values
    bar_measures = []
    bar_entries = fw.get("BarValues", [])
    for bar_entry in bar_entries:
        measure_info = extract_measure_field(bar_entry)
        if measure_info:
            if measure_info["column_name"] in [cf["Name"] for cf in qs_calculated_fields]:
                measure_info["column_name"] = resolve_calculated_field(
                    measure_info["column_name"], qs_calculated_fields
                )
            bar_measures.append({
                "column": measure_info["column_name"],
                "aggregation": measure_info["aggregation"],
                "type": "BAR"
            })
    
    # Line Values
    line_measures = []
    line_entries = fw.get("LineValues", [])
    for line_entry in line_entries:
        measure_info = extract_measure_field(line_entry)
        if measure_info:
            if measure_info["column_name"] in [cf["Name"] for cf in qs_calculated_fields]:
                measure_info["column_name"] = resolve_calculated_field(
                    measure_info["column_name"], qs_calculated_fields
                )
            line_measures.append({
                "column": measure_info["column_name"],
                "aggregation": measure_info["aggregation"],
                "type": "LINE"
            })
    
    # Colors (Series/Stack)
    color_fields = []
    color_entries = fw.get("Colors", [])
    for color_entry in color_entries:
        dim_info = extract_dimension_field(color_entry)
        if dim_info:
            color_fields.append({
                "column": dim_info["column_name"],
                "dataset_identifier": dim_info["dataset_identifier"]
            })
    
    return category_field, bar_measures, line_measures, color_fields


# =========================================================
# UnifiedBISchema v1.3 – QS → Unified Transformer
# (BAR + KPI + LINE + TABLE + SCATTER + PIE + COMBO)
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
    qs_calculated_fields = definition.get("CalculatedFields", [])
    calculated_fields = []

    for cf in qs_calculated_fields:
        expr = cf["Expression"].strip()
        
        # Skip simple column references
        if expr.startswith("{") and expr.endswith("}") and expr.count("{") == 1:
            print(f"⭐ Skipping simple calculated field: {cf['Name']} = {expr}")
            continue
        
        # Keep complex calculated fields
        normalized = normalize_qs_calc(expr)
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
        table_count = 0
        scatter_count = 0
        pie_count = 0
        donut_count = 0
        combo_count = 0

        for visual in sheet.get("Visuals", []):
            visual_keys = list(visual.keys())
            
            # ================= BAR =================
            if "BarChartVisual" in visual:
                bar_count += 1
                bar = visual["BarChartVisual"]
                fw = bar["ChartConfiguration"]["FieldWells"]["BarChartAggregatedFieldWells"]

                # ---- X axis (Category) ----
                if not fw.get("Category"):
                    print(
                        f"⚠️ Skipping BarChartVisual without Category in sheet: {sheet['Name']}"
                    )
                    continue

                dim_info = extract_dimension_field(fw["Category"][0])
                x_col = dim_info["column_name"]
                dataset_identifier = dim_info["dataset_identifier"]

                # ---- Measure ----
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
                    column_name = resolve_calculated_field(
                        val["Name"], qs_calculated_fields
                    )
                    aggregation = val.get("AggregationFunction", "SUM")

                else:
                    raise KeyError("Unsupported BAR measure type")

                # ---- STACK (Color / Group) ----
                stack_cols = []
                if fw.get("Colors") and len(fw["Colors"]) > 0:
                    stack_info = extract_dimension_field(fw["Colors"][0])
                    stack_cols.append(stack_info["column_name"])

                # ---- Build semantic title ----
                normalized_agg = normalize_aggregation(aggregation)
                agg_label = normalized_agg.replace("_", " ").title()

                title = f"{agg_label} of {column_name} by {x_col}"
                if stack_cols:
                    title += f" and {stack_cols[0]}"

                visuals.append({
                    "id": bar["VisualId"],
                    "type": "STACKED_BAR" if stack_cols else "BAR",
                    "title": title,
                    "datasetRef": dataset_id_map[dataset_identifier],
                    "x": [x_col],
                    "stack": stack_cols,
                    "measures": [
                        {
                            "column": column_name,
                            "aggregation": aggregation
                        }
                    ]
                })


            # ================= KPI =================
            elif "KPIVisual" in visual:
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
                    column_name = resolve_calculated_field(column_name, qs_calculated_fields)
                    aggregation = val.get("AggregationFunction", "SUM")

                else:
                    raise KeyError(
                        f"Unsupported measure field type in KPI: {value_entry.keys()}"
                    )

                dataset_identifier = (
                    val.get("Column", {}).get("DataSetIdentifier")
                    if "Column" in val
                    else list(dataset_id_map.keys())[0]
                )

                # --- Extract KPI title exactly as in QuickSight ---
                raw_aggregation = val.get("AggregationFunction", "SUM")
                aggregation = normalize_aggregation(raw_aggregation)

                kpi_title = (
                    kpi.get("ChartConfiguration", {})
                    .get("Title", {})
                    .get("FormatText", {})
                    .get("PlainText")
                )

                if not kpi_title:
                    kpi_title = f"{aggregation.replace('_', ' ').title()} of {column_name}"

                visuals.append({
                    "id": kpi["VisualId"],
                    "type": "KPI",
                    "title": kpi_title,
                    "datasetRef": dataset_id_map[dataset_identifier],
                    "measures": [
                        {
                            "column": column_name,
                            "aggregation": aggregation
                        }
                    ]
                })



           # ================= LINE / AREA =================
            elif "LineChartVisual" in visual:
                line = visual["LineChartVisual"]
                fw = line["ChartConfiguration"]["FieldWells"].get(
                    "LineChartAggregatedFieldWells", {}
                )

                # -----------------------------
                # X AXIS (Date)
                # -----------------------------
                category_field = fw.get("Category", [])
                if not category_field or "DateDimensionField" not in category_field[0]:
                    print(f"⚠️ Skipping LineChartVisual without Date category: {line['VisualId']}")
                    continue

                date_field = category_field[0]["DateDimensionField"]

                x_col = date_field["Column"]["ColumnName"]
                dataset_identifier = date_field["Column"]["DataSetIdentifier"]
                time_grain = date_field.get("DateGranularity")  # DAY / MONTH / YEAR

                # ✅ FIX: Handle null timeGrain - default to "DAY" for line charts
                if not time_grain or time_grain == "null" or str(time_grain).lower() == "null":
                    time_grain = "DAY"
                    print(f"  ⚠️ timeGrain is null for {x_col}, defaulting to DAY")
                
                # -----------------------------
                # Y AXIS (Measure)
                # -----------------------------
                values = fw.get("Values", [])
                if not values:
                    print(f"⚠️ Skipping LineChartVisual without Values: {line['VisualId']}")
                    continue

                measure_info = extract_measure_field(values[0])
                y_col = measure_info["column_name"]
                
                # ✅ Resolve calculated fields to base columns
                if y_col in [cf["Name"] for cf in qs_calculated_fields]:
                    y_col = resolve_calculated_field(y_col, qs_calculated_fields)
                
                aggregation = normalize_aggregation(measure_info["aggregation"])

                # -----------------------------
                # SERIES / COLOR (optional)
                # -----------------------------
                stack_cols = []
                colors = fw.get("Colors", [])
                if colors:
                    dim_info = extract_dimension_field(colors[0])
                    stack_cols.append(dim_info["column_name"])

                # -----------------------------
                # DETERMINE VISUAL TYPE
                # -----------------------------
                chart_subtype = line.get("ChartConfiguration", {}).get("Type")

                if chart_subtype in ["AREA", "STACKED_AREA"]:
                    visual_type = "STACKED_AREA" if stack_cols else "AREA"
                else:
                    visual_type = "LINE"

                # -----------------------------
                # TITLES
                # -----------------------------
                agg_label = aggregation.replace("_", " ").title()
                x_title = x_col.replace("_", " ").title()
                y_title = f"{agg_label} of {y_col}".replace("_", " ").title()

                title = f"{y_title} by {x_title}"
                if stack_cols:
                    title += f" and {stack_cols[0].replace('_', ' ').title()}"

                # -----------------------------
                # ✅ UNIFIED SCHEMA OUTPUT - PROPER FORMAT
                # -----------------------------
                visuals.append({
                    "id": line["VisualId"],
                    "type": visual_type,
                    "title": title,
                    "datasetRef": dataset_id_map[dataset_identifier],
                    "x": [
                        {
                            "column": x_col,
                            "timeGrain": time_grain  # ✅ This will be DAY, MONTH, YEAR, etc.
                        }
                    ],
                    "stack": stack_cols,  # Keep for stacked area/line
                    "measures": [
                        {
                            "column": y_col,
                            "aggregation": aggregation
                        }
                    ],
                    "axes": {
                        "x": {"title": x_title},
                        "y": {"title": y_title}
                    }
                })


            # ================= TABLE =================
            elif "TableVisual" in visual:
                table_count += 1
                table = visual["TableVisual"]
                visual_id = table["VisualId"]
                
                print(f"📋 Processing TABLE visual: {visual_id}")
                
                config = table.get("ChartConfiguration", {})
                field_wells = config.get("FieldWells", {}).get("TableAggregatedFieldWells", {})
                
                table_columns = []
                
                # Process GroupBy fields (dimensions)
                group_by_fields = field_wells.get("GroupBy", [])
                for field in group_by_fields:
                    try:
                        dim_info = extract_dimension_field(field)
                        table_columns.append({
                            "field": dim_info["column_name"],
                            "type": "DIMENSION",
                            "dataType": "STRING"
                        })
                    except Exception as e:
                        print(f"  ⚠️ Error processing GroupBy field: {e}")
                        continue
                
                # Process Values fields (measures)
                values_fields = field_wells.get("Values", [])
                for field in values_fields:
                    try:
                        measure_info = extract_measure_field(field)
                        
                        if measure_info["column_name"] in [cf["Name"] for cf in qs_calculated_fields]:
                            measure_info["column_name"] = resolve_calculated_field(
                                measure_info["column_name"], qs_calculated_fields
                            )
                        
                        table_columns.append({
                            "field": measure_info["column_name"],
                            "type": "MEASURE",
                            "aggregation": measure_info["aggregation"],
                            "dataType": "NUMERIC"
                        })
                    except Exception as e:
                        print(f"  ⚠️ Error processing Values field: {e}")
                        continue
                
                # Determine dataset reference
                dataset_ref = ""
                if table_columns:
                    try:
                        if group_by_fields:
                            dim_info = extract_dimension_field(group_by_fields[0])
                            dataset_ref = dataset_id_map.get(dim_info["dataset_identifier"], "")
                        elif values_fields:
                            measure_info = extract_measure_field(values_fields[0])
                            if measure_info["dataset_identifier"]:
                                dataset_ref = dataset_id_map.get(measure_info["dataset_identifier"], "")
                    except:
                        pass
                
                if not dataset_ref and dataset_id_map:
                    dataset_ref = list(dataset_id_map.values())[0]

                # Build semantic table title
                dimension_cols = [c["field"] for c in table_columns if c["type"] == "DIMENSION"]
                measure_cols = [c for c in table_columns if c["type"] == "MEASURE"]

                if measure_cols:
                    m = measure_cols[0]
                    agg = normalize_aggregation(m.get("aggregation", "SUM"))
                    agg_label = agg.replace("_", " ").title()
                    title = f"{agg_label} of {m['field']}"
                else:
                    title = "Data Table"

                if dimension_cols:
                    title += " by " + ", ".join(dimension_cols)

                visuals.append({
                    "id": visual_id,
                    "type": "TABLE",
                    "title": title,
                    "datasetRef": dataset_ref,
                    "columns": table_columns,
                    "config": {
                        "showTotals": config.get("TotalOptions", {}).get("TotalsVisibility", "HIDDEN") != "HIDDEN",
                        "conditionalFormatting": len(config.get("ConditionalFormatting", {}).get("ConditionalFormattingOptions", [])) > 0,
                        "pagination": {
                            "enabled": True,
                            "pageSize": 50
                        }
                    }
                })
                
                print(f"  ✅ Added TABLE with {len(table_columns)} columns")
            
            # ================= SCATTER PLOT =================
            elif "ScatterPlotVisual" in visual:
                scatter_count += 1
                scatter = visual["ScatterPlotVisual"]
                
                x_field, y_field, size_field, category_fields = extract_scatter_fields(
                    scatter, qs_calculated_fields
                )
                
                if not x_field or not y_field:
                    print(f"⚠️ Skipping ScatterPlotVisual without X or Y axis in sheet: {sheet['Name']}")
                    continue
                
                dataset_identifier = ""
                if x_field and x_field.get("dataset_identifier"):
                    dataset_identifier = x_field["dataset_identifier"]
                elif y_field and y_field.get("dataset_identifier"):
                    dataset_identifier = y_field["dataset_identifier"]
                elif category_fields:
                    dataset_identifier = category_fields[0].get("dataset_identifier", "")
                
                if not dataset_identifier and dataset_id_map:
                    dataset_identifier = list(dataset_id_map.keys())[0]
                
                config = scatter.get("ChartConfiguration", {})
                chart_type = config.get("Type", "SCATTER")
                unified_type = "BUBBLE" if chart_type == "BUBBLE" or size_field else "SCATTER"
                
                measures = []
                
                if x_field:
                    measures.append({
                        "column": x_field["column"],
                        "aggregation": x_field["aggregation"],
                        "mapping": "XAXIS"
                    })
                
                if y_field:
                    measures.append({
                        "column": y_field["column"],
                        "aggregation": y_field["aggregation"],
                        "mapping": "YAXIS"
                    })
                
                if size_field:
                    measures.append({
                        "column": size_field["column"],
                        "aggregation": size_field["aggregation"],
                        "mapping": "SIZE"
                    })
                
                categories = [cf["column"] for cf in category_fields]
                
                title_parts = []
                if x_field:
                    x_agg = normalize_aggregation(x_field["aggregation"])
                    title_parts.append(f"{x_agg} of {x_field['column']}")
                if y_field:
                    y_agg = normalize_aggregation(y_field["aggregation"])
                    title_parts.append(f"{y_agg} of {y_field['column']}")
                
                title = " vs ".join(title_parts) if title_parts else f"Scatter Plot {scatter_count}"
                if categories:
                    title += f" by {', '.join(categories)}"
                
                scatter_visual = {
                    "id": scatter["VisualId"],
                    "type": unified_type,
                    "title": title,
                    "datasetRef": dataset_id_map.get(dataset_identifier, list(dataset_id_map.values())[0] if dataset_id_map else ""),
                    "categories": categories,
                    "measures": measures,
                    "config": {
                        "isBubble": unified_type == "BUBBLE",
                        "showLegend": len(categories) > 0
                    }
                }
                
                if x_field or y_field:
                    scatter_visual["axes"] = {}
                    if x_field:
                        scatter_visual["axes"]["x"] = {
                            "title": x_field["column"].replace("_", " ").title(),
                            "aggregation": normalize_aggregation(x_field["aggregation"])
                        }
                    if y_field:
                        scatter_visual["axes"]["y"] = {
                            "title": y_field["column"].replace("_", " ").title(),
                            "aggregation": normalize_aggregation(y_field["aggregation"])
                        }
                
                visuals.append(scatter_visual)
                print(f"  ✅ Added {unified_type} chart: {title}")
            
            # ================= PIE/DONUT CHART =================
            elif "PieChartVisual" in visual:
                pie = visual["PieChartVisual"]
                
                is_donut = is_donut_chart(pie)
                
                if is_donut:
                    donut_count += 1
                    print(f"  🍩 Processing DONUT chart")
                else:
                    pie_count += 1
                    print(f"  🥧 Processing PIE chart")
                
                category_field, value_field = extract_pie_chart_fields(pie, qs_calculated_fields)
                
                if not category_field or not value_field:
                    chart_type_name = "DonutChartVisual" if is_donut else "PieChartVisual"
                    print(f"⚠️ Skipping {chart_type_name} without category or value in sheet: {sheet['Name']}")
                    continue
                
                dataset_identifier = category_field.get("dataset_identifier") or value_field.get("dataset_identifier")
                if not dataset_identifier and dataset_id_map:
                    dataset_identifier = list(dataset_id_map.keys())[0]
                
                agg = normalize_aggregation(value_field["aggregation"])
                agg_label = agg.replace("_", " ").title()
                title = f"{agg_label} of {value_field['column']} by {category_field['column']}"
                
                visual_type = "DONUT" if is_donut else "PIE"
                
                visuals.append({
                    "id": pie["VisualId"],
                    "type": visual_type,
                    "title": title,
                    "datasetRef": dataset_id_map.get(dataset_identifier, list(dataset_id_map.values())[0] if dataset_id_map else ""),
                    "categories": [category_field["column"]],
                    "measures": [
                        {
                            "column": value_field["column"],
                            "aggregation": value_field["aggregation"]
                        }
                    ]
                })
                
                print(f"  ✅ Added {visual_type} chart: {title}")

            # ================= COMBO CHART (NEW!) =================
            elif "ComboChartVisual" in visual:
                combo_count += 1
                combo = visual["ComboChartVisual"]
                
                print(f"  📊 Processing COMBO chart (Line + Bar)")
                
                category_field, bar_measures, line_measures, color_fields = extract_combo_chart_fields(
                    combo, qs_calculated_fields
                )
                
                if not category_field or (not bar_measures and not line_measures):
                    print(f"⚠️ Skipping ComboChartVisual without required fields in sheet: {sheet['Name']}")
                    continue
                
                dataset_identifier = category_field.get("dataset_identifier")
                if not dataset_identifier and dataset_id_map:
                    dataset_identifier = list(dataset_id_map.keys())[0]
                
                # Build title
                title_parts = []
                if bar_measures:
                    bar_agg = normalize_aggregation(bar_measures[0]["aggregation"])
                    title_parts.append(f"{bar_agg.replace('_', ' ').title()} of {bar_measures[0]['column']}")
                if line_measures:
                    line_agg = normalize_aggregation(line_measures[0]["aggregation"])
                    title_parts.append(f"{line_agg.replace('_', ' ').title()} of {line_measures[0]['column']}")
                
                title = " and ".join(title_parts) if title_parts else "Combo Chart"
                title += f" by {category_field['column']}"
                if color_fields:
                    title += f" and {color_fields[0]['column']}"
                
                # Combine all measures
                all_measures = bar_measures + line_measures
                
                visuals.append({
                    "id": combo["VisualId"],
                    "type": "COMBO",
                    "title": title,
                    "datasetRef": dataset_id_map.get(dataset_identifier, list(dataset_id_map.values())[0] if dataset_id_map else ""),
                    "x": [category_field["column"]],
                    "series": [cf["column"] for cf in color_fields],
                    "barMeasures": bar_measures,
                    "lineMeasures": line_measures,
                    "measures": all_measures
                })
                
                print(f"  ✅ Added COMBO chart: {title}")

            else:
                print(f"⚠️ Unsupported visual type in sheet '{sheet['Name']}': {visual_keys}")

        if visuals:
            pages.append({
                "id": sheet["SheetId"],
                "name": sheet["Name"],
                "visuals": visuals
            })

        # Print summary for this sheet
        print(f"\n📊 Sheet '{sheet['Name']}' summary:")
        if bar_count > 0:
            print(f"  - BAR charts: {bar_count}")
        if kpi_count > 0:
            print(f"  - KPI visuals: {kpi_count}")
        if line_count > 0:
            print(f"  - LINE charts: {line_count}")
        if table_count > 0:
            print(f"  - TABLE visuals: {table_count}")
        if scatter_count > 0:
            print(f"  - SCATTER plots: {scatter_count}")
        if pie_count > 0:
            print(f"  - PIE charts: {pie_count}")
        if donut_count > 0:
            print(f"  - DONUT charts: {donut_count}")
        if combo_count > 0:
            print(f"  - COMBO charts: {combo_count}")

    # -----------------------------
    # UnifiedBISchema Output
    # -----------------------------
    return {
        "schemaVersion": "1.3",  # Updated to 1.3 for COMBO support
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
# Main Runner
# =========================================================
if __name__ == "__main__":
    print("=" * 80)
    print("TRANSFORMING QUICKSIGHT DASHBOARD TO UNIFIED SCHEMA")
    print("(BAR + KPI + LINE + TABLE + SCATTER + PIE + COMBO)")
    print("=" * 80)
    
    try:
        with open(
            "extracted_dashboards/e49d1c30-1172-44e5-9794-f47a4c87cef4.qs.json",
            "r",
            encoding="utf-8"
        ) as f:
            qs_dashboard = json.load(f)

        unified_schema = transform_qs_dashboard_to_unified(qs_dashboard)

        with open("unified_schema.json", "w", encoding="utf-8") as f:
            json.dump(unified_schema, f, indent=2)

        print("\n" + "=" * 80)
        print("✅ UnifiedBISchema generated: unified_schema.json")
        print("=" * 80)
        
        # Show summary
        print(f"\n📊 Dashboard Summary:")
        print(f"  Datasets: {len(unified_schema['datasets'])}")
        print(f"  Calculated Fields: {len(unified_schema['calculatedFields'])}")
        print(f"  Pages: {len(unified_schema['pages'])}")
        
        total_bar = 0
        total_kpi = 0
        total_line = 0
        total_table = 0
        total_scatter = 0
        total_pie = 0
        total_donut = 0
        total_combo = 0
        
        for page in unified_schema['pages']:
            print(f"\n  📄 Page: {page['name']} ({len(page['visuals'])} visuals)")
            for visual in page['visuals']:
                print(f"    • {visual['type']}: {visual.get('title', 'Untitled')}")
                if visual['type'] == 'BAR' or visual['type'] == 'STACKED_BAR':
                    total_bar += 1
                elif visual['type'] == 'KPI':
                    total_kpi += 1
                elif visual['type'] in ['LINE', 'AREA', 'STACKED_AREA']:
                    total_line += 1
                elif visual['type'] == 'TABLE':
                    total_table += 1
                elif visual['type'] == 'SCATTER' or visual['type'] == 'BUBBLE':
                    total_scatter += 1
                elif visual['type'] == 'PIE':
                    total_pie += 1
                elif visual['type'] == 'DONUT':
                    total_donut += 1
                elif visual['type'] == 'COMBO':
                    total_combo += 1
        
        print(f"\n📈 Visual Type Summary:")
        if total_bar > 0:
            print(f"  BAR/STACKED_BAR: {total_bar}")
        if total_kpi > 0:
            print(f"  KPI: {total_kpi}")
        if total_line > 0:
            print(f"  LINE/AREA: {total_line}")
        if total_table > 0:
            print(f"  TABLE: {total_table}")
        if total_scatter > 0:
            print(f"  SCATTER/BUBBLE: {total_scatter}")
        if total_pie > 0:
            print(f"  PIE: {total_pie}")
        if total_donut > 0:
            print(f"  DONUT: {total_donut}")
        if total_combo > 0:
            print(f"  COMBO (Line+Bar): {total_combo}")
    except FileNotFoundError as e:
        print(f"❌ Error: File not found - {e}")
        print("Make sure 'extracted_dashboards/7e06829f-064a-4bbc-918a-d5c287edf0bc.qs.json' exists")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()