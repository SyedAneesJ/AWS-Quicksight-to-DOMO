"""
Schema Validator - Ensures QS and Domo datasets are compatible
"""

from typing import Dict, Any, List


class SchemaValidator:
    """
    Validates schema compatibility between QuickSight and Domo datasets
    """

    def __init__(self):
        pass

    def validate_mapping(
        self,
        qs_dataset_columns: List[str],
        domo_schema_columns: List[Dict[str, Any]],
        required_columns: List[str]
    ) -> Dict[str, Any]:
        """
        Validate that Domo dataset has required columns

        Returns:
            {
                "valid": True/False,
                "missing_columns": [],
                "type_mismatches": [],
                "warnings": []
            }
        """

        domo_columns_by_name = {
            str(col.get("name", "")).lower(): col
            for col in domo_schema_columns
        }

        missing = []
        mismatches = []
        warnings = []

        for required_col in required_columns:
            col_name = str(required_col).lower()
            if col_name not in domo_columns_by_name:
                missing.append(required_col)
                continue

            qs_type = self._infer_type(required_col, qs_dataset_columns)
            domo_type = str(domo_columns_by_name[col_name].get("type", "")).upper()
            if qs_type and domo_type and not self._types_compatible(qs_type, domo_type):
                mismatches.append({
                    "column": required_col,
                    "qs_type": qs_type,
                    "domo_type": domo_type
                })

        return {
            "valid": len(missing) == 0 and len(mismatches) == 0,
            "missing_columns": missing,
            "type_mismatches": mismatches,
            "warnings": warnings
        }

    def _infer_type(self, column_name: str, qs_columns: List[str]) -> str:
        """
        Placeholder: if QS column list includes type info, infer it here.
        Currently returns empty and relies on name-only validation.
        """
        return ""

    def _types_compatible(self, qs_type: str, domo_type: str) -> bool:
        """
        Check if QuickSight and Domo types are compatible
        """
        type_map = {
            "STRING": ["STRING", "TEXT"],
            "INTEGER": ["LONG", "DOUBLE", "DECIMAL"],
            "INT": ["LONG", "DOUBLE", "DECIMAL"],
            "DECIMAL": ["DOUBLE", "DECIMAL", "LONG"],
            "DOUBLE": ["DOUBLE", "DECIMAL", "LONG"],
            "DATETIME": ["DATE", "DATETIME"],
            "DATE": ["DATE", "DATETIME"],
            "BOOLEAN": ["STRING", "LONG"]
        }
        compatible = type_map.get(qs_type.upper(), [])
        return domo_type.upper() in compatible
