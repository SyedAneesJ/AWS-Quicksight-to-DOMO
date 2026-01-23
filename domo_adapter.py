# domo_adapter.py - FINAL FIXED VERSION
from typing import Dict, Any
from calc_field_translator import qs_to_beast_mode_sql

class DomoAdapter:
    def __init__(self, domo_client, dataset_resolver, column_mapping=None):
        self.client = domo_client
        self.dataset_resolver = dataset_resolver
        self.column_mapping = column_mapping or {}
        self.calculated_fields_map = {}

    def deploy_dashboard(self, unified_schema: dict, page_id: str):
        self._process_calculated_fields(unified_schema.get("calculatedFields", []))
        
        results = []

        for page in unified_schema.get("pages", []):
            for visual in page.get("visuals", []):
                try:
                    response = self._deploy_visual(page_id, visual)
                    results.append({
                        "visual_id": visual.get("id"),
                        "type": visual.get("type"),
                        "status": "SUCCESS",
                        "card_id": response.get("id")
                    })
                except Exception as e:
                    results.append({
                        "visual_id": visual.get("id"),
                        "type": visual.get("type"),
                        "status": "FAILED",
                        "error": str(e),
                        "card_id": None
                    })

        return results

    def _process_calculated_fields(self, calculated_fields):
        for cf in calculated_fields:
            name = cf.get("name")
            expression = cf.get("expression")
            
            beast_mode_sql = qs_to_beast_mode_sql(expression)
            
            self.calculated_fields_map[name] = {
                "original_expression": expression,
                "beast_mode_sql": beast_mode_sql
            }

    def _map_column(self, column_name):
        return self.column_mapping.get(column_name, column_name)

    def _normalize_aggregation(self, agg):
        if isinstance(agg, dict):
            agg = agg.get("SimpleNumericalAggregation", "SUM")
        
        agg_map = {
            "AVERAGE": "AVG",
            "SUM": "SUM",
            "COUNT": "COUNT",
            "MIN": "MIN",
            "MAX": "MAX",
            "DISTINCT_COUNT": "COUNT_DISTINCT"
        }
        
        agg_upper = str(agg).upper()
        return agg_map.get(agg_upper, agg_upper)

    def _extract_time_grain(self, x_entry):
        """Extract time grain from x-axis entry"""
        if isinstance(x_entry, dict):
            time_grain = x_entry.get("timeGrain", "DAY")
            column = x_entry.get("column")
            return column, time_grain
        return x_entry, "DAY"

    def _map_time_grain_to_domo(self, qs_grain):
        """Map QuickSight time grain to Domo dateTimeElement"""
        grain_map = {
            "YEAR": "YEAR",
            "QUARTER": "QUARTER",
            "MONTH": "MONTH",
            "WEEK": "WEEK",
            "DAY": "DAY",
            "HOUR": "HOUR",
            "MINUTE": "MINUTE"
        }
        return grain_map.get(qs_grain.upper(), "DAY")

    def _is_date_column(self, column_name):
        """Check if a column is a date field"""
        date_keywords = ["date", "time", "timestamp", "datetime", "day", "month", "year"]
        return any(keyword in column_name.lower() for keyword in date_keywords)

    def _deploy_visual(self, page_id: str, visual: dict):
        visual_type = visual["type"].upper()

        if visual_type == "TABLE":
            payload = self._build_table_payload(visual)
        elif visual_type == "BAR":
            payload = self._build_bar_payload(visual)
        elif visual_type == "STACKED_BAR":
            payload = self._build_stacked_bar_payload(visual)
        elif visual_type == "KPI":
            payload = self._build_kpi_payload(visual)
        elif visual_type == "LINE":
            payload = self._build_line_payload(visual)
        elif visual_type == "AREA":
            payload = self._build_area_payload(visual)
        elif visual_type == "STACKED_AREA":
            payload = self._build_stacked_area_payload(visual)
        elif visual_type == "PIE":
            payload = self._build_pie_payload(visual)
        elif visual_type == "DONUT":
            payload = self._build_donut_payload(visual)
        elif visual_type in ["SCATTER", "BUBBLE"]:
            payload = self._build_scatter_payload(visual)
        elif visual_type == "COMBO":
            payload = self._build_combo_payload(visual)
        else:
            raise NotImplementedError(f"Unsupported visual type: {visual_type}")

        return self.client.create_card(page_id, payload)

    def _build_kpi_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        m = visual["measures"][0]

        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_singlevalue"
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_bar_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        x = visual["x"][0]
        m = visual["measures"][0]

        x_mapped = self._map_column(x)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])
        
        x_title = x_mapped.replace("_", " ").title()
        y_title = f"{aggregation} of {column_name}".replace("_", " ").title()

        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": x_mapped,
                                "mapping": "ITEM"
                            },
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {
                                "column": x_mapped
                            }
                        ],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_vert_bar",
                        "overrides": {
                            "title_x": x_title,
                            "title_y": y_title
                        }
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_stacked_bar_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        
        x = visual["x"][0]
        stack = visual["stack"][0]
        m = visual["measures"][0]
        
        x_mapped = self._map_column(x)
        stack_mapped = self._map_column(stack)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        x_title = x_mapped.replace("_", " ").title()
        y_title = f"{aggregation} of {column_name}".replace("_", " ")
        
        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": x_mapped,
                                "mapping": "ITEM"
                            },
                            {
                                "column": stack_mapped,
                                "mapping": "SERIES"
                            },
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {"column": x_mapped},
                            {"column": stack_mapped}
                        ],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_vert_stackedbar",
                        "overrides": {
                            "title_x": x_title,
                            "title_y": y_title
                        },
                        "goal": None
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }
    
    def _build_line_payload(self, visual: dict):
        """Build Domo card definition for LINE visual with proper date grain handling"""
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])

        # --- EXTRACT X AXIS (with time grain) ---
        x_entry = visual["x"][0]
        
        if isinstance(x_entry, dict):
            # Format: {"column": "attendance_date", "timeGrain": "MONTH"}
            x_col = x_entry.get("column")
            time_grain = x_entry.get("timeGrain", "DAY")
        else:
            # Format: "attendance_date"
            x_col = x_entry
            time_grain = "DAY"
        
        # Map the column name
        x_col = self._map_column(x_col)
        
        # --- EXTRACT MEASURE ---
        m = visual["measures"][0]
        val_col = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m.get("aggregation", "SUM"))

        # --- GET AXIS TITLES ---
        x_title = visual.get("axes", {}).get("x", {}).get(
            "title", x_col.replace("_", " ").title()
        )
        y_title = visual.get("axes", {}).get("y", {}).get(
            "title", f"{aggregation} of {val_col}".replace("_", " ").title()
        )

        # --- DETERMINE IF THIS IS A DATE FIELD ---
        is_date_field = self._is_date_column(x_col)
        
        # --- MAP TIME GRAIN TO DOMO ---
        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else "DAY"
        
        # --- BUILD CALENDAR COLUMN NAME ---
        # Domo uses CalendarDay, CalendarWeek, CalendarMonth, CalendarYear, etc.
        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }
        calendar_column = calendar_column_map.get(domo_grain, "CalendarDay")

        print(f"  📅 Line chart date grain: {time_grain} -> Domo: {domo_grain} -> Calendar: {calendar_column}")

        # --- BUILD BIG_NUMBER SUBSCRIPTION (for summary value) ---
        big_number_subscription = {
            "name": "big_number",
            "columns": [
                {
                    "aggregation": aggregation,
                    "alias": f"{aggregation} of {val_col}",
                    "column": val_col,
                    "format": {
                        "format": "#A",
                        "type": "abbreviated"
                    }
                }
            ],
            "filters": [],
            "orderBy": [],
            "groupBy": [],
            "fiscal": False,
            "projection": False,
            "distinct": False,
            "limit": 1
        }

        # --- BUILD MAIN SUBSCRIPTION ---
        main_columns = [
            {
                "column": calendar_column,  # ✅ CalendarMonth, CalendarDay, etc.
                "calendar": True,
                "mapping": "ITEM"
            },
            {
                "column": val_col,
                "aggregation": aggregation,
                "mapping": "VALUE"
            }
        ]

        main_subscription = {
            "name": "main",
            "columns": main_columns,
            "filters": [],
            "orderBy": [],
            "groupBy": [
                {
                    "column": calendar_column,  # ✅ Group by CalendarMonth
                    "calendar": True
                }
            ],
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        # --- ADD DATE GRAIN (references the actual date column) ---
        if is_date_field:
            main_subscription["dateGrain"] = {
                "column": x_col,  # ✅ The actual date column: "attendance_date"
                "dateTimeElement": domo_grain  # ✅ MONTH
            }

        # --- BUILD COMPLETE PAYLOAD ---
        return {
            "definition": {
                "subscriptions": {
                    "big_number": big_number_subscription,
                    "main": main_subscription
                },
                "formulas": {
                    "dsUpdated": [],
                    "dsDeleted": [],
                    "card": []
                },
                "annotations": {
                    "new": [],
                    "modified": [],
                    "deleted": []
                },
                "conditionalFormats": {
                    "card": [],
                    "datasource": []
                },
                "controls": [],
                "segments": {
                    "active": [],
                    "create": [],
                    "update": [],
                    "delete": []
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_two_trendline",
                        "overrides": {
                            "title_x": x_title,
                            "title_y": y_title
                        },
                        "goal": None
                    }
                },
                "dynamicTitle": {
                    "text": [
                        {
                            "text": visual["title"],
                            "type": "TEXT"
                        }
                    ]
                },
                "dynamicDescription": {
                    "text": [],
                    "displayOnCardDetails": True
                },
                "chartVersion": "12",
                "inputTable": False,
                "title": visual["title"],
                "description": "",
                "includeEmptyFilters": True
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }


    def _build_table_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])

        columns = []
        group_by = []

        for col in visual["columns"]:
            column_name = self._map_column(col["field"])

            if col["type"] == "DIMENSION":
                columns.append({
                    "column": column_name,
                    "mapping": "ITEM"
                })
                group_by.append({
                    "column": column_name
                })

            elif col["type"] == "MEASURE":
                aggregation = self._normalize_aggregation(col["aggregation"])
                columns.append({
                    "column": column_name,
                    "aggregation": aggregation,
                    "mapping": "VALUE"
                })

        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": columns,
                        "filters": [],
                        "groupBy": group_by,
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_table",
                        "overrides": {}
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_area_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        x = visual["x"][0]
        m = visual["measures"][0]

        x_mapped = self._map_column(x)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": x_mapped,
                                "mapping": "ITEM"
                            },
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {"column": x_mapped}
                        ],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_area"
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_stacked_area_payload(self, visual: dict):
        """✅ FIXED: Removed calendar flag, only using dateGrain"""
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])

        # Extract x-axis with time grain
        x_entry = visual["x"][0]
        x_col, time_grain = self._extract_time_grain(x_entry)
        x_col = self._map_column(x_col)
        
        # Map stack column
        stack_col = self._map_column(visual["stack"][0])

        # Map measure
        m = visual["measures"][0]
        val_col = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m.get("aggregation", "AVERAGE"))

        # Get axis titles
        x_title = visual.get("axes", {}).get("x", {}).get(
            "title", x_col.replace("_", " ").title()
        )
        y_title = visual.get("axes", {}).get("y", {}).get(
            "title", f"{aggregation} of {val_col}".replace("_", " ").title()
        )

        # Check if x_col is a date field
        is_date_field = self._is_date_column(x_col)
        
        # Build main subscription - NO calendar flag in columns!
        main_subscription = {
            "name": "main",
            "columns": [
                {
                    "column": x_col,
                    "mapping": "ITEM"
                },
                {
                    "column": val_col,
                    "aggregation": aggregation,
                    "mapping": "VALUE"
                },
                {
                    "column": stack_col,
                    "mapping": "SERIES"
                }
            ],
            "groupBy": [
                {"column": x_col},
                {"column": stack_col}
            ],
            "filters": [],
            "orderBy": [],
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        # ✅ ADD DATE GRAIN - dateGrain goes in subscription, not column
        if is_date_field:
            domo_grain = self._map_time_grain_to_domo(time_grain)
            main_subscription["dateGrain"] = {
                "column": x_col,
                "dateTimeElement": domo_grain
            }

        return {
            "definition": {
                "subscriptions": {
                    "main": main_subscription
                },
                "formulas": {"dsUpdated": [], "dsDeleted": [], "card": []},
                "annotations": {"new": [], "modified": [], "deleted": []},
                "conditionalFormats": {"card": [], "datasource": []},
                "controls": [],
                "segments": {"active": [], "create": [], "update": [], "delete": []},
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_stackedtrend",
                        "overrides": {
                            "title_x": x_title,
                            "title_y": y_title
                        },
                        "goal": None
                    }
                },
                "dynamicTitle": {
                    "text": [{"text": visual["title"], "type": "TEXT"}]
                },
                "dynamicDescription": {"text": [], "displayOnCardDetails": True},
                "chartVersion": "12",
                "inputTable": False,
                "title": visual["title"],
                "description": "",
                "includeEmptyFilters": True
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_pie_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        
        category = visual.get("categories", [None])[0]
        if not category:
            category = visual.get("x", [None])[0]
        
        m = visual["measures"][0]

        category_mapped = self._map_column(category)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": category_mapped,
                                "mapping": "ITEM"
                            },
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {
                                "column": category_mapped
                            }
                        ],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_pie"
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_scatter_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        
        x_measure = next((m for m in visual["measures"] if m.get("mapping") == "XAXIS"), None)
        y_measure = next((m for m in visual["measures"] if m.get("mapping") == "YAXIS"), None)
        size_measure = next((m for m in visual["measures"] if m.get("mapping") == "SIZE"), None)
        
        if not x_measure or not y_measure:
            raise ValueError("Scatter/Bubble chart requires both X and Y axis measures")
        
        x_col = self._map_column(x_measure["column"])
        y_col = self._map_column(y_measure["column"])
        x_agg = self._normalize_aggregation(x_measure["aggregation"])
        y_agg = self._normalize_aggregation(y_measure["aggregation"])
        
        x_title = visual.get("axes", {}).get("x", {}).get("title", None)
        y_title = visual.get("axes", {}).get("y", {}).get("title", None)
        
        if not x_title:
            x_title = f"{x_agg} of {x_col}".replace("_", " ").title()
        
        if not y_title:
            y_title = f"{y_agg} of {y_col}".replace("_", " ").title()
        
        columns = [
            {
                "column": x_col,
                "mapping": "XTIME",
                "aggregation": x_agg
            },
            {
                "column": y_col,
                "mapping": "VALUE",
                "aggregation": y_agg
            }
        ]
        
        group_by = []
        if visual.get("categories"):
            for category in visual["categories"]:
                category_mapped = self._map_column(category)
                columns.append({
                    "column": category_mapped,
                    "mapping": "SERIES"
                })
                group_by.append({
                    "column": category_mapped
                })
        
        if size_measure and visual["type"].upper() == "BUBBLE":
            size_col = self._map_column(size_measure["column"])
            size_agg = self._normalize_aggregation(size_measure["aggregation"])
            columns.append({
                "column": size_col,
                "mapping": "BUBBLESIZE",
                "aggregation": size_agg
            })
        
        chart_type = "badge_xybubble" if visual["type"].upper() == "BUBBLE" else "badge_xyscatter"
        
        main_subscription = {
            "name": "main",
            "columns": columns,
            "filters": [],
            "orderBy": [],
            "groupBy": group_by,
            "fiscal": False,
            "projection": False,
            "distinct": False
        }
        
        date_col = None
        for col_name in [x_col, y_col]:
            if self._is_date_column(col_name):
                date_col = col_name
                break
        
        if date_col:
            main_subscription["dateGrain"] = {"column": date_col, "dateTimeElement": "DAY"}
        
        return {
            "definition": {
                "subscriptions": {
                    "main": main_subscription
                },
                "formulas": {
                    "dsUpdated": [],
                    "dsDeleted": [],
                    "card": []
                },
                "annotations": {
                    "new": [],
                    "modified": [],
                    "deleted": []
                },
                "conditionalFormats": {
                    "card": [],
                    "datasource": []
                },
                "controls": [],
                "segments": {
                    "active": [],
                    "create": [],
                    "update": [],
                    "delete": []
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": chart_type,
                        "overrides": {
                            "title_x": x_title,
                            "title_y": y_title
                        },
                        "goal": None
                    }
                },
                "dynamicTitle": {
                    "text": [
                        {
                            "text": visual["title"],
                            "type": "TEXT"
                        }
                    ]
                },
                "dynamicDescription": {
                    "text": [],
                    "displayOnCardDetails": True
                },
                "chartVersion": "12",
                "inputTable": False,
                "title": visual["title"],
                "description": "",
                "includeEmptyFilters": True
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_donut_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        
        category = visual.get("categories", [None])[0]
        if not category:
            category = visual.get("x", [None])[0]
        
        m = visual["measures"][0]

        category_mapped = self._map_column(category)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": category_mapped,
                                "mapping": "ITEM"
                            },
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {
                                "column": category_mapped
                            }
                        ],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_donut"
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_combo_payload(self, visual: dict):
        """✅ FIXED: Line+Bar combo matching Domo's expected structure"""
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        
        # Extract x-axis with time grain
        x_entry = visual["x"][0]
        x_col, time_grain = self._extract_time_grain(x_entry)
        x_col_mapped = self._map_column(x_col)
        
        # Handle series
        series_list = visual.get("series", [])
        series_col_mapped = None
        if series_list and len(series_list) > 0:
            series_col_mapped = self._map_column(series_list[0])
        
        bar_measures = visual.get("barMeasures", [])
        line_measures = visual.get("lineMeasures", [])
        
        is_date_field = self._is_date_column(x_col_mapped)
        
        # Map time grain to Domo format
        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else "DAY"
        
        # Build columns array with metadata
        columns = []
        aliases = []
        formats = []
        mappings = []
        metadata = []
        
        # ✅ X-axis column (ITEM mapping)
        if is_date_field:
            columns.append("Date")
            aliases.append(x_col_mapped)
            formats.append(None)
            mappings.append("ITEM")
            metadata.append({
                "type": "DATE",
                "dataSourceId": dataset_id,
                "maxLength": -1,
                "minLength": -1,
                "periodIndex": 0,
                "aggregated": False,
                "label": x_col_mapped,
                "column": "Date",
                "filterType": "CALENDAR",
                "dateJoinColumn": x_col_mapped,
                "fiscal": False,
                "calendarColumn": True
            })
        else:
            columns.append(x_col_mapped)
            aliases.append(x_col_mapped)
            formats.append(None)
            mappings.append("ITEM")
            metadata.append({
                "type": "STRING",
                "dataSourceId": dataset_id,
                "maxLength": -1,
                "minLength": -1,
                "periodIndex": 0,
                "aggregated": False,
                "label": x_col_mapped,
                "column": x_col_mapped,
                "filterType": "COLUMN_ID",
                "calendarColumn": False
            })
        
        # ✅ Add measure columns (VALUE mappings)
        all_measures = []
        
        if bar_measures:
            for bar_measure in bar_measures:
                all_measures.append(bar_measure)
        
        if line_measures:
            for line_measure in line_measures:
                all_measures.append(line_measure)
        
        # Add first measure (bar or line)
        if all_measures:
            first_measure = all_measures[0]
            measure_col = self._map_column(first_measure["column"])
            measure_agg = self._normalize_aggregation(first_measure["aggregation"])
            
            columns.append(measure_col)
            aliases.append(measure_col)
            formats.append(None)
            mappings.append("VALUE")
            metadata.append({
                "type": "LONG",
                "dataSourceId": dataset_id,
                "maxLength": -1,
                "minLength": -1,
                "periodIndex": 0,
                "aggregated": True,
                "label": measure_col,
                "column": measure_col,
                "filterType": "COLUMN_ID",
                "aggregation": measure_agg,
                "calendarColumn": False
            })
        
        # ✅ Series column (if exists)
        if series_col_mapped:
            columns.append(series_col_mapped)
            aliases.append(series_col_mapped)
            formats.append(None)
            mappings.append("SERIES")
            metadata.append({
                "type": "STRING",
                "dataSourceId": dataset_id,
                "maxLength": -1,
                "minLength": -1,
                "periodIndex": 0,
                "aggregated": False,
                "label": series_col_mapped,
                "column": series_col_mapped,
                "filterType": "COLUMN_ID",
                "calendarColumn": False
            })
        
        # Build main subscription with proper structure
        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": [],  # Will be built from column mappings
            "filters": [],
            "orderBy": [],
            "groupBy": [],
            "fiscal": False,
            "projection": False,
            "distinct": False
        }
        
        # Add dateGrain if date field
        if is_date_field:
            main_subscription["dateGrain"] = {
                "column": x_col_mapped,
                "dateTimeElement": domo_grain
            }
        
        # Build column definitions for subscription
        subscription_columns = []
        
        # X-axis
        if is_date_field:
            subscription_columns.append({
                "column": "Date",
                "calendar": True,
                "mapping": "ITEM"
            })
            main_subscription["groupBy"].append({
                "column": "Date",
                "calendar": True
            })
        else:
            subscription_columns.append({
                "column": x_col_mapped,
                "mapping": "ITEM"
            })
            main_subscription["groupBy"].append({
                "column": x_col_mapped
            })
        
        # Measures
        if all_measures:
            for measure in all_measures:
                measure_col = self._map_column(measure["column"])
                measure_agg = self._normalize_aggregation(measure["aggregation"])
                subscription_columns.append({
                    "column": measure_col,
                    "aggregation": measure_agg,
                    "mapping": "VALUE"
                })
        
        # Series
        if series_col_mapped:
            subscription_columns.append({
                "column": series_col_mapped,
                "mapping": "SERIES"
            })
            main_subscription["groupBy"].append({
                "column": series_col_mapped
            })
        
        main_subscription["columns"] = subscription_columns
        
        # ✅ Return payload matching Domo's structure
        return {
            "definition": {
                "subscriptions": {
                    "main": main_subscription
                },
                "formulas": {"dsUpdated": [], "dsDeleted": [], "card": []},
                "annotations": {"new": [], "modified": [], "deleted": []},
                "conditionalFormats": {"card": [], "datasource": []},
                "controls": [],
                "segments": {"active": [], "create": [], "update": [], "delete": []},
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_line_stackedbar",
                        "overrides": {},
                        "goal": None
                    }
                },
                "dynamicTitle": {
                    "text": [{"text": visual.get("title", "Combo Chart"), "type": "TEXT"}]
                },
                "dynamicDescription": {"text": [], "displayOnCardDetails": True},
                "chartVersion": "12",
                "inputTable": False,
                "title": visual.get("title", "Combo Chart"),
                "description": "",
                "includeEmptyFilters": True
            },
            "dataProvider": {"dataSourceId": dataset_id},
            "variables": True
        }