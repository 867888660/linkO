import os
import sqlite3

OutPutNum = 1
InPutNum = 1

Outputs = [
    {
        "Num": None,
        "Kind": "String",
        "Boolean": False,
        "Id": "Output1",
        "Context": None,
        "name": "result功能1",
        "Link": 0,
        "Description": "",
    }
]

Inputs = [
    {
        "Num": None,
        "Kind": "String_FilePath",
        "Id": "Input1",
        "Context": None,
        "Isnecessary": True,
        "name": "DB_Path",
        "Link": 0,
        "IsLabel": True,
    }
]

NodeKind = "Normal"
Lable = [{"Id": "Label1", "Kind": "None"}]
FunctionIntroduction = (
    "组件功能：参数兜底组件。输入 SQLite 数据库路径后，扫描表 polyMarket_Monitor 并修复空值默认参数。"
)


def _run_update(cur, sql, params=None):
    if params is None:
        params = []
    cur.execute(sql, params)
    return cur.rowcount if cur.rowcount is not None else 0


def run_node(node):
    db_path = (node.get("Inputs", [{}])[0].get("Context") or "").strip()
    result_lines = []

    if not db_path:
        Outputs[0]["Context"] = "失败：DB_Path 不能为空。"
        return Outputs

    if not os.path.exists(db_path):
        Outputs[0]["Context"] = f"失败：数据库文件不存在 -> {db_path}"
        return Outputs

    table_name = "polyMarket_Monitor"
    required_columns = {
        "Strategy",
        "Yes_Min_Qty",
        "Yes_Max_Qty",
        "No_Min_Qty",
        "No_Max_Qty",
        "Search_words",
        "days_to_end",
        "Inputs1",
        "Inputs2",
        "Inputs3",
        "Inputs4",
        "Inputs5",
        "Inputs6",
        "Inputs7",
    }

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=8)
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout=8000;")

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
            (table_name,),
        )
        if not cur.fetchone():
            Outputs[0]["Context"] = f"失败：表不存在 -> {table_name}"
            return Outputs

        cur.execute(f'PRAGMA table_info("{table_name}")')
        table_columns = {row[1] for row in cur.fetchall()}

        missing_cols = [c for c in sorted(required_columns) if c not in table_columns]
        if missing_cols:
            Outputs[0]["Context"] = "失败：缺少列 -> " + ", ".join(missing_cols)
            return Outputs

        # 1) 全表兜底：Yes/No Min/Max Qty 不能为空
        updated_yes_min = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "Yes_Min_Qty" = 0
            WHERE "Yes_Min_Qty" IS NULL OR TRIM(CAST("Yes_Min_Qty" AS TEXT)) = '';
            ''',
        )
        updated_yes_max = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "Yes_Max_Qty" = 20
            WHERE "Yes_Max_Qty" IS NULL OR TRIM(CAST("Yes_Max_Qty" AS TEXT)) = '';
            ''',
        )
        updated_no_min = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "No_Min_Qty" = 0
            WHERE "No_Min_Qty" IS NULL OR TRIM(CAST("No_Min_Qty" AS TEXT)) = '';
            ''',
        )
        updated_no_max = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "No_Max_Qty" = 20
            WHERE "No_Max_Qty" IS NULL OR TRIM(CAST("No_Max_Qty" AS TEXT)) = '';
            ''',
        )

        # 2) Strategy = Stragy_Fllow_Stock_Value.py 时，Search_words 兜底
        updated_search_words = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "Search_words" = ?
            WHERE "Strategy" = ?
              AND ("Search_words" IS NULL OR TRIM(CAST("Search_words" AS TEXT)) = '');
            ''',
            ["AAPL,MSFT,GOOGL,AMZN,NVDA", "Stragy_Fllow_Stock_Value.py"],
        )

        # 3) Strategy = Stragy_Fllow_Stock_Value.py 且 Inputs1=GooG 时，修正为 GOOGL
        updated_inputs1_goog = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "Inputs1" = ?
            WHERE "Strategy" = ?
              AND "Inputs1" = ?;
            ''',
            ["GOOGL", "Stragy_Fllow_Stock_Value.py", "GooG"],
        )

        # 4) Strategy = Stragy_Fllow_Truth.py 时，Inputs1-6 兜底 0.5
        truth_strategy = "Stragy_Fllow_Truth.py"
        truth_input_filled = 0
        for idx in range(1, 7):
            col = f"Inputs{idx}"
            truth_input_filled += _run_update(
                cur,
                f'''
                UPDATE "{table_name}"
                SET "{col}" = 0.5
                WHERE "Strategy" = ?
                  AND ("{col}" IS NULL OR TRIM(CAST("{col}" AS TEXT)) = '');
                ''',
                [truth_strategy],
            )

        # 5) Strategy = Stragy_Fllow_Truth.py 时，Inputs7 = days_to_end
        updated_inputs7 = _run_update(
            cur,
            f'''
            UPDATE "{table_name}"
            SET "Inputs7" = "days_to_end"
            WHERE "Strategy" = ?;
            ''',
            [truth_strategy],
        )

        conn.commit()

        result_lines.append("执行成功：polyMarket_Monitor 参数兜底完成。")
        result_lines.append(f"Yes_Min_Qty 兜底行数: {updated_yes_min}")
        result_lines.append(f"Yes_Max_Qty 兜底行数: {updated_yes_max}")
        result_lines.append(f"No_Min_Qty 兜底行数: {updated_no_min}")
        result_lines.append(f"No_Max_Qty 兜底行数: {updated_no_max}")
        result_lines.append(f"Search_words 兜底行数: {updated_search_words}")
        result_lines.append(f"Inputs1 GooG->GOOGL 修正行数: {updated_inputs1_goog}")
        result_lines.append(f"Inputs1-6 兜底总行数: {truth_input_filled}")
        result_lines.append(f"Inputs7=days_to_end 更新行数: {updated_inputs7}")

        Outputs[0]["Context"] = "\n".join(result_lines)
        return Outputs

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        Outputs[0]["Context"] = f"失败：{e}"
        return Outputs
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
