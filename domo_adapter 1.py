

class DomoAdapter:
    def __init__(self, domo_client, dataset_resolver):
        """
        domo_client: instance of DomoClient
        dataset_resolver: object with resolve(dataset_ref) -> domo_dataset_id
        """
        self.client = domo_client
        self.dataset_resolver = dataset_resolver

    def deploy_dashboard(self, unified_schema: dict, page_id: str):
        """
        Deploy UnifiedBISchema dashboard to an existing Domo page
        """
        #self.cleanup_existing_cards(page_id) #-----public API limitations causing card creation error
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
            payload = self._build_line_payload(visual)

        elif visual_type == "PIE":
            payload = self._build_pie_payload(visual)

        else:
            raise NotImplementedError(
                f"Unsupported visual type: {visual_type}"
            )

        return self.client.create_card(page_id, payload)




    # --------------------------------------------------
    # 2.2 KPI payload builder
    # --------------------------------------------------
    def _build_kpi_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        m = visual["measures"][0]

        return {
            "definition": {
                "title": visual["title"],

                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": m["column"],
                                "aggregation": m["aggregation"],
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
                        "chartType": "badge_singlevalue"  # ✅ WORKING TYPE
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }


    # --------------------------------------------------
    # 2.3 Bar chart payload builder
    # --------------------------------------------------
    def _build_bar_payload(self, visual):
        dataset_id = self.dataset_resolver.resolve(visual["datasetRef"])
        x = visual["x"][0]
        m = visual["measures"][0]

        y_axis_title = f'{m["aggregation"]} {m["column"]}'

        return {
            "definition": {
                "title": visual["title"],

                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": x,
                                "mapping": "ITEM"
                            },
                            {
                                "column": m["column"],
                                "aggregation": m["aggregation"],
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {
                                "column": x
                            }
                        ],
                        "distinct": False
                    }
                },

                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_vert_bar",

                        "axes": {
                            "x": {
                                "title": x
                            },
                            "y": {
                                "title": y_axis_title
                            }
                        }
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }

    # --------------------------------------------------
    # 2.4 Line chart payload builder
    # --------------------------------------------------
    def _build_line_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(
            visual["datasetRef"]
        )

        x = visual["x"][0]                     # date / time column
        m = visual["measures"][0]              # metric

        y_axis_title = f'{m["aggregation"]} {m["column"]}'

        return {
            "definition": {
                "title": visual["title"],

                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": x,
                                "mapping": "ITEM"
                            },
                            {
                                "column": m["column"],
                                "aggregation": m["aggregation"],
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {
                                "column": x
                            }
                        ],
                        "distinct": False
                    }
                },

                "charts": {
                    "main": {
                        "component": "main",
                        "chartType": "badge_line",
                        "labels": {
                            "xAxis": x,
                            "yAxis": y_axis_title
                        }
                    }
                }
            },
            "dataProvider": {
                "dataSourceId": dataset_id
            },
            "variables": True
        }


    # --------------------------------------------------
    # 2.5 Pie chart payload builder
    # --------------------------------------------------
    def _build_pie_payload(self, visual: dict):
        dataset_id = self.dataset_resolver.resolve(
            visual["datasetRef"]
        )

        x = visual["x"][0]                 # slice dimension
        m = visual["measures"][0]          # measure

        return {
            "definition": {
                "title": visual["title"],

                "subscriptions": {
                    "main": {
                        "name": "main",
                        "columns": [
                            {
                                "column": x,
                                "mapping": "ITEM"
                            },
                            {
                                "column": m["column"],
                                "aggregation": m["aggregation"],
                                "mapping": "VALUE"
                            }
                        ],
                        "filters": [],
                        "groupBy": [
                            {
                                "column": x
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
