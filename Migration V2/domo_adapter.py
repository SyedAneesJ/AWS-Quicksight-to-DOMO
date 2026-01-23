class DomoAdapter:
    def __init__(self, domo_client, dataset_resolver):
        """
        domo_client: instance of DomoClient
        dataset_resolver: object with resolve(dataset_ref) -> domo_dataset_id
        """
        self.client = domo_client
        self.dataset_resolver = dataset_resolver
        self._calc_field_map = {}
        self._unified_schema_cache = {}
    
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

    def _normalize_aggregation(self, agg):
        """
        Normalize aggregation function names
        QuickSight uses 'AVERAGE', Domo uses 'AVG'
        """
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

    def deploy_dashboard(self, unified_schema: dict, page_id: str):
        """
        Deploy UnifiedBISchema dashboard to an existing Domo page
        """
        # Cache calculated fields for adapter use
        self._unified_schema_cache = {
            cf["name"]: cf["expression"]
            for cf in unified_schema.get("calculatedFields", [])
        }
        self._calc_field_map = {
            cf["name"]: cf["expression"]
            for cf in unified_schema.get("calculatedFields", [])
        }

        results = []

        for page in unified_schema["pages"]:
            for visual in page["visuals"]:
                try:
                    self._deploy_visual(page_id, visual)
                    results.append({
                        "visual_id": visual.get("id"),
                        "type": visual.get("type"),
                        "status": "SUCCESS"
                    })
                except Exception as e:
                    results.append({
                        "visual_id": visual.get("id"),
                        "type": visual.get("type"),
                        "status": "FAILED",
                        "error": str(e)
                    })

        return results

    # --------------------------------------------------
    # 2.1 Router — REPLACES existing _deploy_visual
    # --------------------------------------------------
    def _deploy_visual(self, page_id: str, visual: dict):
        visual_type = visual["type"].upper()

        if visual_type == "BAR":
            payload = self._build_bar_payload(visual)

        elif visual_type == "KPI":
            payload = self._build_kpi_payload(visual)

        elif visual_type == "LINE":
            x_col = visual["x"][0]

            if self._is_time_column(x_col):
                payload = self._build_line_payload(visual)   # TRUE LINE
            else:
                # QS allows categorical line, Domo does not → downgrade safely
                payload = self._build_bar_payload(visual)

        else:
            raise NotImplementedError(
                f"Unsupported visual type: {visual_type}"
            )

        return self.client.create_card(page_id, payload)

    def _resolve_measure_column(self, column_name: str) -> str:
        """
        Resolve Unified calculated field to physical dataset column.
        v1.0 supports parseDecimal(col) only.
        """
        if column_name in self._calc_field_map:
            expr = self._calc_field_map[column_name]

            if expr.lower().startswith("parsedecimal("):
                return expr[len("parseDecimal("):-1].strip()

        return column_name

    # --------------------------------------------------
    # 2.2 KPI payload builder
    # --------------------------------------------------
    def _build_kpi_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        m = visual["measures"][0]
        
        column_name = self._resolve_measure_column(m["column"])
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
            "dataProvider": {"dataSourceId": dataset_id},
            "variables": True
        }

    # --------------------------------------------------
    # 2.3 Bar chart payload builder
    # --------------------------------------------------
    def _build_bar_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        x = visual["x"][0]
        m = visual["measures"][0]
        
        column_name = self._resolve_measure_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])
        y_axis_title = f"{aggregation} {column_name}"
        
        return {
            "definition": {
                "title": visual["title"],
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {"column": x, "mapping": "ITEM"},
                            {
                                "column": column_name,
                                "aggregation": aggregation,
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [{"column": x}],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_vert_bar",
                        "axes": {
                            "x": {"title": x},
                            "y": {"title": y_axis_title}
                        }
                    }
                }
            },
            "dataProvider": {"dataSourceId": dataset_id},
            "variables": True
        }

    # --------------------------------------------------
    # 2.4 Line chart payload builder
    # --------------------------------------------------
    def _build_line_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        x = visual["x"][0]
        m = visual["measures"][0]
        series = visual.get("series")
        
        column_name = self._resolve_measure_column(m["column"])
        aggregation = self._normalize_aggregation(m["aggregation"])
        
        columns = [
            {"column": x, "mapping": "ITEM"},
            {
                "column": column_name,
                "aggregation": aggregation,
                "mapping": "VALUE"
            }
        ]
        
        group_by = [{"column": x}]
        
        if series:
            columns.append({
                "column": series,
                "mapping": "SERIES"
            })
            group_by.insert(0, {"column": series})
        
        return {
            "definition": {
                "title": visual["title"],
                "chartVersion": "12",
                "inputTable": False,
                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": columns,
                        "groupBy": group_by,
                        "dateGrain": {"column": x},
                        "filters": [],
                        "distinct": False
                    }
                },
                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_curvedline"
                    }
                }
            },
            "dataProvider": {"dataSourceId": dataset_id},
            "variables": True
        }