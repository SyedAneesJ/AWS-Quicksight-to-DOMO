#calc_field_classifier.py

import re
from typing import Dict
from enum import Enum

class CalcType(Enum):
    ROW = "ROW"
    AGGREGATE = "AGGREGATE"
    MIXED = "MIXED"
    UNSUPPORTED = "UNSUPPORTED"

import re

AGG_FUNCS = ["sum", "count", "avg", "min", "max"]

def classify_calc_expression(expr: str) -> Dict:
    expr = expr.strip()
    expr_l = expr.lower()

    # ---------- IF / CASE (ROW only) ----------
    if expr_l.startswith("ifelse(") or expr_l.startswith("case"):
        return {
            "calculationType": "ROW",
            "row": expr,
            "aggregate": None
        }

    # ---------- AGGREGATION ----------
    agg_match = re.match(rf"^({'|'.join(AGG_FUNCS)})\((.*)\)$", expr_l)
    if agg_match:
        agg = agg_match.group(1).upper()
        inner = agg_match.group(2).strip()

        # ❌ nested aggregate
        if re.search(rf"\b({'|'.join(AGG_FUNCS)})\(", inner):
            raise ValueError(f"Nested aggregation not supported: {expr}")

        # ❌ math on aggregate input
        if re.search(r"[+\-*/]", inner):
            raise ValueError(f"Math inside aggregate not supported: {expr}")

        # ✅ AGG + CASE (v4)
        if inner.lower().startswith("ifelse(") or inner.lower().startswith("case"):
            return {
                "calculationType": "AGG_CASE",
                "row": inner,
                "aggregate": agg
            }

        # ✅ Simple aggregate
        return {
            "calculationType": "AGGREGATE",
            "row": None,
            "aggregate": f"{agg}({inner})"
        }

    # ---------- Plain ROW ----------
    return {
        "calculationType": "ROW",
        "row": expr,
        "aggregate": None
    }
