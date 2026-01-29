# calc_field_translator.py

def normalize_qs_calc(expr: str):
    """
    Normalizes QS calculated field expressions.
    Strips aggregation and returns row-level expression + aggregation.
    """
    expr = expr.strip()

    if expr.lower().startswith("ifelse("):
        return {
            "row_expression": translate_ifelse(expr)
        }

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

    
def translate_ifelse(expr: str) -> str:
    """
    Converts QS ifelse(a > b, x, y)
    → CASE WHEN a > b THEN x ELSE y END
    """

    inner = expr.strip()[7:-1]  # remove ifelse(...)
    parts = split_args(inner)

    if len(parts) != 3:
        raise ValueError(f"Invalid ifelse syntax: {expr}")

    condition, true_val, false_val = parts

    return f"CASE WHEN {condition} THEN {true_val} ELSE {false_val} END"

def split_args(expr: str):
    args = []
    depth = 0
    current = ""

    for ch in expr:
        if ch == ',' and depth == 0:
            args.append(current.strip())
            current = ""
            continue

        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1

        current += ch

    if current:
        args.append(current.strip())

    return args

def qs_calc_to_beast_mode(calc: dict) -> dict:
    """
    Convert a classified QS calculated field into Beast Mode SQL.
    v4 supports:
      - ROW
      - AGGREGATE
      - AGG_CASE
    """

    calc_type = calc["calculationType"]

    # ---------- ROW ----------
    if calc_type == "ROW":
        return {
            "beast_sql": qs_to_beast_mode_sql(calc["row"]),
            "aggregation": None
        }

    # ---------- AGGREGATE ----------
    if calc_type == "AGGREGATE":
        return {
            "beast_sql": qs_to_beast_mode_sql(calc["aggregate"]),
            "aggregation": None
        }

    # ---------- AGG + CASE (v4) ----------
    if calc_type == "AGG_CASE":
        case_sql = translate_ifelse(calc["row"])
        return {
            "beast_sql": f'{calc["aggregate"]}({qs_to_beast_mode_sql(case_sql)})',
            "aggregation": None
        }

    raise ValueError(f"Unsupported calculation type: {calc_type}")
