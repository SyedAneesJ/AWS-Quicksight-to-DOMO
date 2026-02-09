"""
Dataset Registry - Tracks QuickSight datasets and their datasource metadata
"""

from typing import Dict, Any, Optional
import json
from pathlib import Path


class DatasetRegistry:
    """
    Manages dataset mappings with datasource awareness
    """

    def __init__(self, storage_path: str = "dataset_mappings.json"):
        self.storage_path = Path(storage_path)
        self.mappings: Dict[str, Dict[str, Any]] = {}
        self.load()

    def register_dataset(
        self,
        qs_dataset_id: str,
        qs_dataset_name: str,
        datasource_type: str,
        connection_properties: Dict[str, Any],
        domo_dataset_id: Optional[str] = None
    ):
        self.mappings[qs_dataset_id] = {
            "qs_name": qs_dataset_name,
            "datasource_type": datasource_type,
            "connection_properties": connection_properties,
            "domo_dataset_id": domo_dataset_id,
            "status": "mapped" if domo_dataset_id else "unmapped"
        }
        self.save()

    def get_mapping(self, qs_dataset_id: str) -> Optional[Dict[str, Any]]:
        return self.mappings.get(qs_dataset_id)

    def set_domo_mapping(self, qs_dataset_id: str, domo_dataset_id: str):
        if qs_dataset_id in self.mappings:
            self.mappings[qs_dataset_id]["domo_dataset_id"] = domo_dataset_id
            self.mappings[qs_dataset_id]["status"] = "mapped"
            self.save()

    def get_all_snowflake_datasets(self) -> Dict[str, Dict[str, Any]]:
        return {
            k: v for k, v in self.mappings.items()
            if v.get("datasource_type") == "SNOWFLAKE"
        }

    def suggest_domo_match(
        self,
        qs_dataset_id: str,
        available_domo_datasets: list
    ) -> Optional[str]:
        qs_info = self.mappings.get(qs_dataset_id)
        if not qs_info:
            return None

        qs_props = qs_info.get("connection_properties", {})
        qs_table = str(qs_props.get("table", "")).lower()
        qs_database = str(qs_props.get("database", "")).lower()

        for domo_ds in available_domo_datasets:
            domo_name = str(domo_ds.get("name", "")).lower()
            if qs_table and qs_table in domo_name:
                return domo_ds.get("id")
            if qs_database and qs_table:
                if qs_database in domo_name and qs_table in domo_name:
                    return domo_ds.get("id")

        return None

    def save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.mappings, f, indent=2)

    def load(self):
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.mappings = json.load(f)
