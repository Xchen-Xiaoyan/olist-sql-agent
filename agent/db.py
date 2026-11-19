"""Read-only SQL execution with guardrails: one SELECT/WITH statement, no file access, timeout, row cap."""
import re
import threading
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "olist.duckdb"
MAX_ROWS = 1000
TIMEOUT_S = 15

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|create|drop|alter|attach|detach|copy|export|import|install|load|pragma|set|"
    r"call|checkpoint|vacuum|use)\b|read_(csv|parquet|json|text|blob)\w*|glob\s*\(", re.I)


class SQLError(Exception):
    pass


def _strip(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return sql.strip().rstrip(";").strip()


def validate(sql: str) -> str:
    body = _strip(sql)
    if not body:
        raise SQLError("empty query")
    if ";" in body:
        raise SQLError("only one statement is allowed")
    if not re.match(r"(select|with|from)\b", body, re.I):
        raise SQLError("only SELECT queries are allowed")
    # String literals may legitimately contain words like 'set', so check the query with literals blanked out.
    if m := _FORBIDDEN.search(re.sub(r"'(?:[^']|'')*'", "''", body)):
        raise SQLError(f"forbidden keyword: {m.group(0)}")
    return body


class Database:
    def __init__(self, path: Path = DB_PATH):
        # read_only blocks writes; disabling external access blocks reading local files and the network.
        self.con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False})
        self.lock = threading.Lock()

    def query(self, sql: str, max_rows: int = MAX_ROWS, timeout: float = TIMEOUT_S) -> pd.DataFrame:
        body = validate(sql)
        with self.lock:
            cur = self.con.cursor()
            timer = threading.Timer(timeout, cur.interrupt)
            timer.start()
            try:
                df = cur.execute(f"SELECT * FROM ({body}) LIMIT {max_rows + 1}").df()
            except duckdb.InterruptException:
                raise SQLError(f"query timed out after {timeout:.0f}s") from None
            except duckdb.Error as e:
                raise SQLError(str(e).split("\n\nLINE")[0][:600]) from None
            finally:
                timer.cancel()
                cur.close()
        if len(df) > max_rows:
            df = df.head(max_rows)
            df.attrs["truncated"] = True
        return df
