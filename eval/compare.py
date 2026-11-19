"""Execution-accuracy check: does the predicted result contain the gold result?

Rules (standard for text-to-SQL eval, slightly relaxed for analyst-style answers):
- Row count must match. Row order is ignored.
- Every gold column must be matched by some predicted column; extra predicted columns are allowed
  (e.g. the agent also returns order counts next to the requested rate).
- Integer counts must match exactly. Other numbers match within a relative tolerance (or the gold value rounded to 2+ decimals); a 0-1 rate also matches the same rate x100 (percent).
- Boolean gold columns (group keys like is_on_time) are not required: predicted labels may differ
  ('准时' vs True), so those rows are matched on their numbers.
"""
import math

import pandas as pd

TOL = 1e-3


def _is_num(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _num_eq(a, b, tol) -> bool:
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        return (a is None or a != a) and (b is None or b != b)
    if float(a).is_integer() and float(b).is_integer() and abs(a) >= 1:
        return a == b  # counts must be exact: 15,264 orders is not 15,259
    if abs(a - b) <= tol * max(1.0, abs(a), abs(b)) or abs(a - b) <= 1e-9:
        return True
    # The prediction may round for presentation (ROUND(x, 2)); accept rounding to 2+ decimals of the gold value.
    return any(abs(round(a, d) - b) <= 1e-9 * max(1.0, abs(b)) for d in (2, 3, 4))


def _col_values(s: pd.Series, scale: float = 1.0):
    if _is_num(s):
        return sorted(float(v) * scale if pd.notna(v) else float("nan") for v in s)
    return sorted(str(v).strip().lower() for v in s)


def _columns_match(g: pd.Series, p: pd.Series, tol) -> float | None:
    """Return the scale factor applied to p (1 or 0.01) if the columns hold the same values, else None."""
    if _is_num(g) != _is_num(p):
        if _is_num(g) or _is_num(p):
            # A numeric gold column may come back as a string label like '7.32%'; not accepted.
            return None
    if not _is_num(g):
        return 1.0 if _col_values(g) == _col_values(p) else None
    gv = _col_values(g)
    for scale in (1.0, 0.01):
        pv = _col_values(p, scale)
        if len(gv) == len(pv) and all(_num_eq(a, b, tol) for a, b in zip(gv, pv)):
            return scale
    return None


def matches(pred: pd.DataFrame | None, gold: pd.DataFrame, tol: float = TOL) -> bool:
    if pred is None or len(pred) != len(gold):
        return False
    if len(gold) == 0:
        return True
    gold = gold.reset_index(drop=True)
    pred = pred.reset_index(drop=True)
    gold_cols = [c for c in gold.columns if not pd.api.types.is_bool_dtype(gold[c])]
    mapping, used = {}, set()
    for gc in gold_cols:
        for pc in pred.columns:
            if pc in used:
                continue
            scale = _columns_match(gold[gc], pred[pc], tol)
            if scale is not None:
                mapping[gc] = (pc, scale)
                used.add(pc)
                break
        else:
            return False
    # Columns match one by one; now check they line up row by row (keys paired with the right values).
    def rows(df, cols, scales):
        out = []
        for _, r in df.iterrows():
            out.append(tuple((round(float(r[c]) * s, 4) if _is_num(df[c]) and pd.notna(r[c]) else str(r[c]).strip().lower())
                             for c, s in zip(cols, scales)))
        return sorted(out, key=str)
    g_rows = rows(gold, gold_cols, [1.0] * len(gold_cols))
    p_rows = rows(pred, [mapping[c][0] for c in gold_cols], [mapping[c][1] for c in gold_cols])
    for gr, pr in zip(g_rows, p_rows):
        for a, b in zip(gr, pr):
            if isinstance(a, float) and isinstance(b, float):
                if not _num_eq(a, b, max(tol, 1e-3)):
                    return False
            elif a != b:
                return False
    return True


def _numbers_in(text: str) -> list[tuple[float, float]]:
    """All numbers in an answer as (value, half of the last stated digit), with 万/亿/k/M/B and % expanded.

    '117.3 万' -> (1173000, 500): any true value in [1172500, 1173500] is consistent with what was written.
    A percentage is also kept as a fraction ('140.4%' -> (1.404, 0.0005)).
    """
    import re
    out = []
    for m in re.finditer(r"(-?\d[\d,]*(?:\.(\d+))?)\s*(亿|万|[kKMB](?![a-zA-Z])|%)?", text):
        if text[m.end():m.end() + 1] in ("年", "月", "日"):
            continue  # dates ('2017年1月') are not quoted results
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        half = 0.5 * 10 ** -(len(m.group(2)) if m.group(2) else 0)
        unit = m.group(3)
        mult = {"亿": 1e8, "万": 1e4, "k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}.get(unit, 1)
        out.append((v * mult, half * mult))
        if unit == "%":
            out.append((v / 100, half / 100))
    return out


def _label_forms(v: str) -> list[str]:
    """'2017-11' may be written '2017年11月' or 'November 2017'; other labels must appear as-is."""
    import re
    v = v.strip().lower()
    m = re.fullmatch(r"(\d{4})-(\d{2})", v)
    if not m:
        return [v]
    y, mo = m.group(1), int(m.group(2))
    month = "january february march april may june july august september october november december".split()[mo - 1]
    return [v, f"{y}年{mo}月", f"{y}年{mo:02d}月", f"{month} {y}", f"{month[:3]} {y}"]


def text_matches(answer: str, gold: pd.DataFrame) -> bool:
    """The written answer states the gold result: every gold label appears and every gold number is quoted,
    correctly rounded at whatever precision the answer uses. Only for small results (<= 3 rows), the usual
    'which one / how much' questions."""
    if not answer or gold is None or len(gold) == 0 or len(gold) > 3:
        return False
    nums, low = _numbers_in(answer), answer.lower()
    for c in gold.columns:
        s = gold[c]
        if pd.api.types.is_bool_dtype(s):
            continue
        for v in s:
            if pd.isna(v):
                return False
            if _is_num(s):
                v = float(v)
                # The stated number must equal the true value rounded to the precision it was stated with.
                # ...and that precision must be meaningful: '1' does not state 1.40 (rounding step <= 1% of the value).
                if not any(abs(n - v) <= half * (1 + 1e-9) + 1e-9 and half <= 0.01 * abs(v) + 1e-9
                           for n, half in nums):
                    return False
            elif not any(form in low for form in _label_forms(str(v))):
                return False
    return True
