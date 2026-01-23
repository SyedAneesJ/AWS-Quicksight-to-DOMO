# calc_field_translator.py

def normalize_qs_calc(expr: str):
    """
    Normalizes QS calculated field expressions.
    Strips aggregation and returns row-level expression + aggregation.
    """
    expr = expr.strip()

    if expr.lower().startswith("sum(") and expr.endswith(")"):
        inner = expr[4:-1].strip()
        return {
            "row_expression": inner,
            "aggregation": "SUM"
        }

    return {
        "row_expression": expr,
        "aggregation": None
    }


def qs_to_beast_mode_sql(expr: str) -> str:
    """
    Translate row-level QS expression to Beast Mode SQL.
    v1.1 supports parseDecimal only.
    """
    expr = expr.strip()

    if expr.lower().startswith("parsedecimal(") and expr.endswith(")"):
        col = expr[len("parseDecimal("):-1].strip()
        return f'CAST("{col}" AS DECIMAL)'

    # fallback (pass-through)
    return expr
