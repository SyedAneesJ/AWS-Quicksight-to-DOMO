# domo_adapter.py - FINAL FIXED VERSION
from typing import Dict, Any
from calc_field_translator import qs_to_beast_mode_sql

class DomoAdapter:
    def __init__(self, domo_client, dataset_resolver, column_mapping=None):
        self.client = domo_client
        self.dataset_resolver = dataset_resolver
        self.column_mapping = column_mapping or {}
        self.calculated_fields_map = {}

    #check if x-axis is a date or not - used for line chart (domo not allowing to create x-axis which is not date/time)
    def _is_time_column(self, column_name: str) -> bool:
        """
        Heuristic check for time-based columns.
        v1.0: name-based detection only.
        """
        col = column_name.lower()

        time_keywords = [
            "date",
            "time",
            "timestamp",
            "created",
            "updated",
            "order_date",
            "event_time"
        ]

        return any(k in col for k in time_keywords)


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

    def _build_big_number_subscription(self, val_col: str, aggregation: str):
        return {
            "name": "big_number",
            "columns": [
                {
                    "column": val_col,
                    "aggregation": aggregation,
                    "alias": f"{aggregation} of {val_col}",
                    "format": {
                        "type": "abbreviated",
                        "format": "#A"
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

    def _build_standard_definition(
        self,
        title: str,
        main_subscription: dict,
        chart_type: str,
        overrides: dict | None = None,
        value_column: str | None = None,
        value_aggregation: str | None = None
    ):
        return {
            "subscriptions": {
                "big_number": self._build_big_number_subscription(
                    value_column or main_subscription["columns"][-1]["column"],
                    value_aggregation or main_subscription["columns"][-1].get("aggregation", "SUM")
                ),
                "main": main_subscription
            },
            "charts": {
                "main": {
                    "component": "main",
                    "chartType": chart_type,
                    "overrides": overrides or {},
                    "goal": None
                }
            },
            "dynamicTitle": {
                "text": [
                    {"type": "TEXT", "text": title}
                ]
            },
            "dynamicDescription": {
                "text": [],
                "displayOnCardDetails": True
            },
            "formulas": {"card": [], "dsUpdated": [], "dsDeleted": []},
            "annotations": {"new": [], "modified": [], "deleted": []},
            "conditionalFormats": {"card": [], "datasource": []},
            "controls": [],
            "segments": {"active": [], "create": [], "update": [], "delete": []},
            "chartVersion": "12",
            "inputTable": False,
            "title": title,
            "description": "",
            "includeEmptyFilters": True
        }


    def _deploy_visual(self, page_id: str, visual: dict):
        payload = self.build_card_config(visual)
        return self.client.create_card(page_id, payload)

    def build_card_config(self, visual: dict) -> dict:
        """
        Build a Domo card config payload without creating the card.
        Useful for frontend codeengine flows.
        """
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

        return payload


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

        x_col = x.get("column") if isinstance(x, dict) else x
        time_grain = x.get("timeGrain") if isinstance(x, dict) else None

        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }

        calendar_column = None
        if time_grain:
            calendar_column = calendar_column_map.get(str(time_grain).upper(), "CalendarDay")

        x_mapped = calendar_column or self._map_column(x_col)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])
        
        x_title = (x_col or x_mapped).replace("_", " ").title()
        y_title = f"{aggregation} of {column_name}".replace("_", " ").title()

        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else None
        date_grain = (
            {"column": x_col, "dateTimeElement": domo_grain}
            if time_grain and x_col and domo_grain else None
        )

        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": [
                {
                    "column": x_mapped,
                    **({"calendar": True} if calendar_column else {}),
                    "mapping": "ITEM"
                },
                {
                    "column": column_name,
                    "aggregation": aggregation,
                    "mapping": "VALUE"
                }
            ],
            "filters": [],
            "orderBy": [],
            "groupBy": [
                {
                    "column": x_mapped,
                    **({"calendar": True} if calendar_column else {})
                }
            ],
            **({"dateGrain": date_grain} if date_grain else {}),
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        return {
            "definition": {
                **self._build_standard_definition(
                    visual["title"],
                    main_subscription,
                    "badge_vert_bar",
                    {"title_x": x_title, "title_y": y_title},
                    column_name,
                    aggregation
                )
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
        
        x_col = x.get("column") if isinstance(x, dict) else x
        time_grain = x.get("timeGrain") if isinstance(x, dict) else None

        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }

        calendar_column = None
        if time_grain:
            calendar_column = calendar_column_map.get(str(time_grain).upper(), "CalendarDay")

        x_mapped = calendar_column or self._map_column(x_col)
        stack_mapped = self._map_column(stack)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        x_title = (x_col or x_mapped).replace("_", " ").title()
        y_title = f"{aggregation} of {column_name}".replace("_", " ")

        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else None
        date_grain = (
            {"column": x_col, "dateTimeElement": domo_grain}
            if time_grain and x_col and domo_grain else None
        )

        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": [
                {
                    "column": x_mapped,
                    **({"calendar": True} if calendar_column else {}),
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
            "orderBy": [],
            "groupBy": [
                {"column": x_mapped, **({"calendar": True} if calendar_column else {})},
                {"column": stack_mapped}
            ],
            **({"dateGrain": date_grain} if date_grain else {}),
            "fiscal": False,
            "projection": False,
            "distinct": False
        }
        
        return {
            "definition": {
                **self._build_standard_definition(
                    visual["title"],
                    main_subscription,
                    "badge_vert_stackedbar",
                    {"title_x": x_title, "title_y": y_title},
                    column_name,
                    aggregation
                )
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }
    
    def _build_line_payload(self, visual: dict):
        """
        ✅ UPDATED: Now supports both single-line and multi-line charts
        - If visual has 'stack' field with values, creates multi-line chart
        - Otherwise creates single-line chart
        """
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])

        # -------- X AXIS --------
        x_entry = visual["x"][0]
        if isinstance(x_entry, dict):
            x_raw = x_entry.get("column")
            time_grain = x_entry.get("timeGrain")
        else:
            x_raw = x_entry
            time_grain = None

        x_col = self._map_column(x_raw)

        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else None

        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }

        calendar_column = (
            calendar_column_map.get(str(time_grain).upper(), "CalendarDay")
            if time_grain else None
        )

        # -------- MEASURE --------
        measures = visual.get("measures", [])
        m = measures[0]
        val_col = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m.get("aggregation", "SUM"))

        # -------- CHECK FOR MULTI-LINE (SERIES) --------
        stack_fields = visual.get("stack", [])
        has_series = len(stack_fields) > 0
        series_col = self._map_column(stack_fields[0]) if has_series else None
        has_multi_measure = len(measures) > 1

        # -------- AXIS TITLES --------
        x_title = visual.get("axes", {}).get("x", {}).get(
            "title",
            "Date" if time_grain else (x_raw or "Category")
        )
        y_title = visual.get("axes", {}).get("y", {}).get(
            "title", f"{aggregation} of {val_col}"
        )

        if time_grain:
            print(
                f"📈 LINE chart - Date grain: {time_grain} -> "
                f"Domo: {domo_grain} -> Calendar: {calendar_column}"
            )
        else:
            print(f"📈 LINE chart - Non-date category: {x_col}")
        if has_series:
            print(f"   Multi-line mode: SERIES = {series_col}")
        elif has_multi_measure:
            print("   Multi-line mode: MULTI-MEASURE")
        else:
            print(f"   Single-line mode")

        # -------- BIG NUMBER --------
        big_number_subscription = {
            "name": "big_number",
            "columns": [
                {
                    "column": val_col,
                    "aggregation": aggregation,
                    "alias": f"{aggregation} of {val_col}",
                    "format": {
                        "type": "abbreviated",
                        "format": "#A"
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

        # -------- MAIN SUBSCRIPTION --------
        item_column = calendar_column or x_col
        main_columns = [
            {
                "column": item_column,
                **({"calendar": True} if calendar_column else {}),
                "mapping": "ITEM"
            },
        ]
        
        main_groupby = [
            {
                "column": item_column,
                **({"calendar": True} if calendar_column else {})
            }
        ]

        if has_series:
            # ✅ Dimension-based multi-line: VALUE + SERIES
            main_columns.append({
                "column": val_col,
                "aggregation": aggregation,
                "mapping": "VALUE"
            })
            main_columns.append({
                "column": series_col,
                "mapping": "SERIES"
            })
            main_groupby.append({
                "column": series_col
            })
        elif has_multi_measure:
            # ✅ Measure-based multi-line: each measure as SERIES
            for measure in measures:
                main_columns.append({
                    "column": self._map_column(measure["column"]),
                    "aggregation": self._normalize_aggregation(measure.get("aggregation", "SUM")),
                    "mapping": "SERIES"
                })
        else:
            # ✅ Single-line
            main_columns.append({
                "column": val_col,
                "aggregation": aggregation,
                "mapping": "VALUE"
            })

        date_grain = (
            {"column": x_raw, "dateTimeElement": domo_grain}
            if time_grain and x_raw and domo_grain else None
        )

        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": main_columns,
            "filters": [],
            "orderBy": [],
            "groupBy": main_groupby,
            **({"dateGrain": date_grain} if date_grain else {}),
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        return {
            "definition": {
                "subscriptions": {
                    "big_number": big_number_subscription,
                    "main": main_subscription
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
                        {"type": "TEXT", "text": visual["title"]}
                    ]
                },
                "dynamicDescription": {
                    "text": [],
                    "displayOnCardDetails": True
                },
                "formulas": {"card": [], "dsUpdated": [], "dsDeleted": []},
                "annotations": {"new": [], "modified": [], "deleted": []},
                "conditionalFormats": {"card": [], "datasource": []},
                "controls": [],
                "segments": {"active": [], "create": [], "update": [], "delete": []},
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

        x_col = x.get("column") if isinstance(x, dict) else x
        time_grain = x.get("timeGrain") if isinstance(x, dict) else None

        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }

        calendar_column = None
        if time_grain:
            calendar_column = calendar_column_map.get(str(time_grain).upper(), "CalendarDay")

        x_mapped = calendar_column or self._map_column(x_col)
        column_name = self._map_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])

        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else None
        date_grain = (
            {"column": x_col, "dateTimeElement": domo_grain}
            if time_grain and x_col and domo_grain else None
        )

        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": [
                {
                    "column": x_mapped,
                    **({"calendar": True} if calendar_column else {}),
                    "mapping": "ITEM"
                },
                {
                    "column": column_name,
                    "aggregation": aggregation,
                    "mapping": "VALUE"
                }
            ],
            "filters": [],
            "orderBy": [],
            "groupBy": [
                {"column": x_mapped, **({"calendar": True} if calendar_column else {})}
            ],
            **({"dateGrain": date_grain} if date_grain else {}),
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        return {
            "definition": {
                **self._build_standard_definition(
                    visual["title"],
                    main_subscription,
                    "badge_vert_area_overlay",
                    {},
                    column_name,
                    aggregation
                )
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    def _build_stacked_area_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])

        x_entry = visual["x"][0]
        if isinstance(x_entry, dict):
            x_raw = x_entry.get("column")
            time_grain = x_entry.get("timeGrain")
        else:
            x_raw = x_entry
            time_grain = None

        x_col = self._map_column(x_raw)
        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else None

        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }

        calendar_column = (
            calendar_column_map.get(str(time_grain).upper(), "CalendarDay")
            if time_grain else None
        )

        measure = visual["measures"][0]
        value_col = self._map_column(measure["column"])
        aggregation = self._normalize_aggregation(measure["aggregation"])

        stack_col = self._map_column(visual["stack"][0])

        item_column = calendar_column or x_col
        date_grain = (
            {"column": x_raw, "dateTimeElement": domo_grain}
            if time_grain and x_raw and domo_grain else None
        )

        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": [
                {
                    "column": item_column,
                    **({"calendar": True} if calendar_column else {}),
                    "mapping": "ITEM"
                },
                {
                    "column": value_col,
                    "aggregation": aggregation,
                    "mapping": "VALUE"
                },
                {
                    "column": stack_col,
                    "mapping": "SERIES"
                }
            ],
            "filters": [],
            "orderBy": [],
            "groupBy": [
                {
                    "column": item_column,
                    **({"calendar": True} if calendar_column else {})
                },
                {
                    "column": stack_col
                }
            ],
            **({"dateGrain": date_grain} if date_grain else {}),
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        payload = {
            "definition": {
                "subscriptions": {
                    "main": main_subscription
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_stackedtrend",
                        "overrides": {
                            "title_x": visual.get("axes", {}).get("x", {}).get("title", ""),
                            "title_y": visual.get("axes", {}).get("y", {}).get("title", "")
                        },
                        "goal": None
                    }
                },
                "dynamicTitle": {
                    "text": [
                        {
                            "type": "TEXT",
                            "text": visual.get(
                                "title",
                                f"{aggregation} of {value_col} by {x_col} and {stack_col}"
                            )
                        }
                    ]
                },
                "dynamicDescription": {
                    "text": [],
                    "displayOnCardDetails": True
                },
                "formulas": {"card": [], "dsUpdated": [], "dsDeleted": []},
                "annotations": {"new": [], "modified": [], "deleted": []},
                "conditionalFormats": {"card": [], "datasource": []},
                "controls": [],
                "segments": {"active": [], "create": [], "update": [], "delete": []},
                "chartVersion": "12",
                "inputTable": False,
                "title": visual.get("title", ""),
                "description": "",
                "includeEmptyFilters": True
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

        return payload


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
        """✅ FINAL: Working combo chart with big_number subscription"""
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])

        # Extract x-axis
        x_entry = visual["x"][0]
        x_col, time_grain = self._extract_time_grain(x_entry)
        x_col_mapped = self._map_column(x_col)

        is_date_field = self._is_date_column(x_col_mapped)
        domo_grain = self._map_time_grain_to_domo(time_grain) if time_grain else "DAY"

        calendar_column_map = {
            "DAY": "CalendarDay",
            "WEEK": "CalendarWeek",
            "MONTH": "CalendarMonth",
            "QUARTER": "CalendarQuarter",
            "YEAR": "CalendarYear"
        }
        calendar_column = calendar_column_map.get(str(time_grain).upper(), "CalendarDay") if is_date_field else None
        x_item_col = calendar_column or x_col_mapped

        bar_measures = visual.get("barMeasures", [])
        line_measures = visual.get("lineMeasures", [])
        series_list = visual.get("series", [])

        if not bar_measures or not line_measures:
            raise ValueError("COMBO requires at least one BAR and one LINE measure")

        # Resolve columns
        bar_col = self._map_column(bar_measures[0]["column"])
        bar_agg = self._normalize_aggregation(bar_measures[0]["aggregation"])

        line_col = self._map_column(line_measures[0]["column"])
        line_agg = self._normalize_aggregation(line_measures[0]["aggregation"])

        series_col = self._map_column(series_list[0]) if series_list else None

        # Build subscription columns
        subscription_columns = []
        group_by = []

        # X-axis
        subscription_columns.append({
            "column": x_item_col,
            **({"calendar": True} if calendar_column else {}),
            "mapping": "ITEM"
        })
        group_by.append({
            "column": x_item_col,
            **({"calendar": True} if calendar_column else {})
        })

        # If series exists, always include it for stacked bars
        if series_col:
            subscription_columns.append({
                "column": series_col,
                "mapping": "SERIES"
            })
            group_by.append({
                "column": series_col
            })

        if bar_col == line_col and not series_col:
            # No series: model two aggregations as SERIES to show both measures
            subscription_columns.append({
                "column": bar_col,
                "aggregation": bar_agg,
                "mapping": "SERIES"
            })
            subscription_columns.append({
                "column": line_col,
                "aggregation": line_agg,
                "mapping": "SERIES"
            })
        else:
            subscription_columns.append({
                "column": bar_col,
                "aggregation": bar_agg,
                "mapping": "VALUE"
            })
            subscription_columns.append({
                "column": line_col,
                "aggregation": line_agg,
                "mapping": "VALUE"
            })

        # Build main subscription
        main_subscription = {
            "name": "main",
            "dataSourceId": dataset_id,
            "columns": subscription_columns,
            "filters": [],
            "orderBy": [],
            "groupBy": group_by,
            "fiscal": False,
            "projection": False,
            "distinct": False
        }

        # Add dateGrain for date fields
        if is_date_field:
            main_subscription["dateGrain"] = {
                "column": x_col,
                "dateTimeElement": domo_grain
            }

        # ✅ Build big_number subscription (REQUIRED for combo charts)
        big_number_subscription = {
            "name": "big_number",
            "dataSourceId": dataset_id,
            "columns": [
                {
                    "column": bar_col,
                    "aggregation": bar_agg,
                    "alias": f"{bar_agg} of {bar_col}",
                    "format": {
                        "type": "abbreviated",
                        "format": "#A"
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

        definition = self._build_standard_definition(
            visual.get("title", "Combo Chart"),
            main_subscription,
            "badge_line_stackedbar",
            {},
            bar_col,
            bar_agg
        )
        definition["allowTableDrill"] = True
        definition["controls"] = definition.get("controls", [])
        definition["segments"] = {"active": [], "create": [], "update": [], "delete": []}

        payload = {
            "definition": definition,
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }
        
        # DEBUG: Print the payload
        # import json
        # print("\n🔍 COMBO PAYLOAD:")
        # print(json.dumps(payload, indent=2))
        # print("\n")
        
        return payload
