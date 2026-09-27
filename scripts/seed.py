"""Seed script: preset users / sample materials / teaching relations.

Runs on EVERY startup via db.seed_preset(). All inserts are idempotent —
deduped by natural keys (users.username is UNIQUE, materials checked by
title+class_id, teacher_classes UNIQUE constraint) — so existing data is
never modified, and old volumes get class-002 backfilled losslessly.
Passwords are bcrypt-hashed with random salt at insert time only.
"""
from __future__ import annotations

from sqlite3 import Connection

import bcrypt


def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


CLASS_001 = "class-001"
CLASS_002 = "class-002"

# Preset users — 2 classes for class-isolation demos
# (username, plaintext password, role, class_id)
_PRESET_USERS = [
    ("teacher",  "teacher123", "teacher", CLASS_001),
    ("student1", "student123", "student", CLASS_001),
    ("student2", "student123", "student", CLASS_001),
    ("teacher2", "teacher123", "teacher", CLASS_002),
    ("student3", "student123", "student", CLASS_002),
]

# Teaching relations — teacher co-teaches both classes so class switching
# is demoable out of the box (deliberate preset, see user-auth spec)
_PRESET_TEACHING = [
    ("teacher",  CLASS_001),
    ("teacher",  CLASS_002),
    ("teacher2", CLASS_002),
]

# Sample materials (class_id, owner username, title, content)
# Fixed titles double as dedup keys for idempotent re-runs.
_PRESET_MATERIALS = [
    (CLASS_001, "teacher", "《高等数学》第一章课件",
     "本章节讲解极限、导数、积分的基本概念与典型例题，配套习题详解见附录。"),
    (CLASS_001, "teacher", "数据结构复习提纲",
     "线性表、栈与队列、树与图、排序与查找算法要点整理，期末考试重点。"),
    (CLASS_002, "teacher2", "【预置】操作系统进程与线程讲义",
     "进程状态转换、线程调度、死锁四个必要条件与银行家算法示例。"),
    (CLASS_002, "teacher2", "【预置】计算机网络期末复习要点",
     "OSI 七层模型、TCP 三次握手与四次挥手、子网划分计算例题。"),
]


def seed_preset(conn: Connection) -> None:
    """Insert missing preset rows only; existing data stays untouched."""
    n_users = n_mat = n_teach = 0

    # --- users (username UNIQUE → INSERT OR IGNORE) ---
    for username, plain_pwd, role, class_id in _PRESET_USERS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role, class_id) "
            "VALUES (?, ?, ?, ?)",
            (username, _hash(plain_pwd), role, class_id),
        )
        n_users += cur.rowcount

    # --- teaching relations (UNIQUE(teacher_id, class_id) → INSERT OR IGNORE) ---
    for username, class_id in _PRESET_TEACHING:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO teacher_classes (teacher_id, class_id) VALUES (?, ?)",
            (row["id"], class_id),
        )
        n_teach += cur.rowcount

    # --- sample materials (no UNIQUE on title → check-then-insert) ---
    for class_id, owner, title, content in _PRESET_MATERIALS:
        exists = conn.execute(
            "SELECT 1 FROM materials WHERE title = ? AND class_id = ?",
            (title, class_id),
        ).fetchone()
        if exists:
            continue
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (owner,)
        ).fetchone()
        if row is None:
            continue
        conn.execute(
            "INSERT INTO materials (class_id, owner_id, title, content) VALUES (?, ?, ?, ?)",
            (class_id, row["id"], title, content),
        )
        n_mat += 1

    print(f"[seed] backfilled users={n_users} teaching={n_teach} materials={n_mat}")


# Backwards-compatible alias (standalone runs / old callers)
seed = seed_preset


if __name__ == "__main__":
    # Allow running as: python -m scripts.seed  (for standalone / testing)
    from app.db import connect, init_schema

    conn = connect()
    init_schema(conn)
    seed_preset(conn)
    conn.commit()
    conn.close()
