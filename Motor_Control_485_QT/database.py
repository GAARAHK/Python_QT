# -*- coding: gbk -*-
"""
数据库操作层 —— SQLite 五表结构
"""
import sqlite3
import uuid
import datetime
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "motor_control.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化所有数据表（首次运行自动建表）"""
    conn = get_conn()
    c = conn.cursor()

    # 表1: 全局参数配置
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # 表2: 工况模板
    c.execute("""
        CREATE TABLE IF NOT EXISTS work_mode_templates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE,
            steps_json      TEXT NOT NULL,   -- JSON: [{action, duration_s}, ...]
            target_loops    INTEGER NOT NULL DEFAULT 100,
            collect_interval INTEGER NOT NULL DEFAULT 10,
            alarm_min       REAL NOT NULL DEFAULT 0.0,
            alarm_max       REAL NOT NULL DEFAULT 10.0,
            created_at      TEXT NOT NULL
        )
    """)

    # 表3: 批次运行主表
    c.execute("""
        CREATE TABLE IF NOT EXISTS motor_run_history (
            batch_uuid  TEXT PRIMARY KEY,
            motor_id    INTEGER NOT NULL,
            qr_code     TEXT NOT NULL,
            template_id INTEGER,
            start_time  TEXT NOT NULL,
            end_time    TEXT,
            end_status  TEXT DEFAULT 'running'  -- running/completed/alarm/manual_stop
        )
    """)

    # 表4: 电流日志（按月分表，动态建表）
    _ensure_current_log_table(c)

    # 表5: 报警日志
    c.execute("""
        CREATE TABLE IF NOT EXISTS alarm_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_uuid  TEXT,
            motor_id    INTEGER NOT NULL,
            qr_code     TEXT NOT NULL,
            loop_count  INTEGER NOT NULL,
            alarm_value REAL NOT NULL,
            alarm_min   REAL NOT NULL,
            alarm_max   REAL NOT NULL,
            timestamp   TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def _current_table_name() -> str:
    return f"current_logs_{datetime.datetime.now().strftime('%Y_%m')}"


def _ensure_current_log_table(cursor: sqlite3.Cursor):
    table = _current_table_name()
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_uuid  TEXT,
            motor_id    INTEGER NOT NULL,
            qr_code     TEXT NOT NULL,
            loop_count  INTEGER NOT NULL,
            read_current REAL NOT NULL,
            timestamp   TEXT NOT NULL
        )
    """)


# ── 参数配置 CRUD ─────────────────────────────────────────────────────────
def save_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings_config (key, value) VALUES (?, ?)",
            (key, value)
        )


def load_setting(key: str, default: str = "") -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM settings_config WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def save_all_settings(settings: dict):
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO settings_config (key, value) VALUES (?, ?)",
            [(k, str(v)) for k, v in settings.items()]
        )


def load_all_settings() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings_config").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ── 工况模板 CRUD ─────────────────────────────────────────────────────────
def save_template(name: str, steps: list, target_loops: int,
                  collect_interval: int, alarm_min: float, alarm_max: float) -> int:
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT OR REPLACE INTO work_mode_templates
            (name, steps_json, target_loops, collect_interval, alarm_min, alarm_max, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, json.dumps(steps), target_loops, collect_interval,
              alarm_min, alarm_max, now))
        return cur.lastrowid


def load_templates() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM work_mode_templates ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["steps"] = json.loads(d["steps_json"])
        result.append(d)
    return result


def delete_template(template_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM work_mode_templates WHERE id=?", (template_id,))


# ── 批次运行 CRUD ─────────────────────────────────────────────────────────
def start_run_batch(motor_id: int, qr_code: str, template_id: int) -> str:
    batch_uuid = str(uuid.uuid4())
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO motor_run_history
            (batch_uuid, motor_id, qr_code, template_id, start_time, end_status)
            VALUES (?, ?, ?, ?, ?, 'running')
        """, (batch_uuid, motor_id, qr_code, template_id, now))
    return batch_uuid


def end_run_batch(batch_uuid: str, status: str):
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            UPDATE motor_run_history
            SET end_time=?, end_status=?
            WHERE batch_uuid=?
        """, (now, status, batch_uuid))


# ── 电流日志写入 ──────────────────────────────────────────────────────────
def log_current(batch_uuid: str, motor_id: int, qr_code: str,
                loop_count: int, current_value: float):
    table = _current_table_name()
    now = datetime.datetime.now().isoformat()
    conn = get_conn()
    try:
        _ensure_current_log_table(conn.cursor())
        conn.execute(f"""
            INSERT INTO {table}
            (batch_uuid, motor_id, qr_code, loop_count, read_current, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (batch_uuid, motor_id, qr_code, loop_count, current_value, now))
        conn.commit()
    finally:
        conn.close()


# ── 报警日志写入 ──────────────────────────────────────────────────────────
def log_alarm(batch_uuid: str, motor_id: int, qr_code: str,
              loop_count: int, alarm_value: float,
              alarm_min: float, alarm_max: float):
    now = datetime.datetime.now().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO alarm_logs
            (batch_uuid, motor_id, qr_code, loop_count, alarm_value,
             alarm_min, alarm_max, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_uuid, motor_id, qr_code, loop_count, alarm_value,
              alarm_min, alarm_max, now))


# ── 查询接口 ──────────────────────────────────────────────────────────────
def query_history_by_qrcode(qr_code: str) -> list:
    """按二维码查询运行批次"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM motor_run_history
        WHERE qr_code=? ORDER BY start_time DESC
    """, (qr_code,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_current_logs_by_batch(batch_uuid: str, table_suffix: str = None) -> list:
    """查询指定批次的电流记录"""
    if table_suffix:
        table = f"current_logs_{table_suffix}"
    else:
        table = _current_table_name()
    conn = get_conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE batch_uuid=? ORDER BY loop_count",
            (batch_uuid,)
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def query_alarm_logs(qr_code: str = None, motor_id: int = None) -> list:
    conn = get_conn()
    if qr_code:
        rows = conn.execute(
            "SELECT * FROM alarm_logs WHERE qr_code=? ORDER BY timestamp DESC",
            (qr_code,)
        ).fetchall()
    elif motor_id is not None:
        rows = conn.execute(
            "SELECT * FROM alarm_logs WHERE motor_id=? ORDER BY timestamp DESC",
            (motor_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM alarm_logs ORDER BY timestamp DESC LIMIT 500"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_available_log_tables(conn: sqlite3.Connection) -> list:
    """获取所有电流日志分表名称"""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'current_logs_%'"
    ).fetchall()
    return [r["name"] for r in rows]
