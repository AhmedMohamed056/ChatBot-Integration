"""SQLite persistence for dynamic application data."""

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "app.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                whatsapp_number TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                campaign_name TEXT NOT NULL,
                original_message TEXT NOT NULL,
                extracted_info TEXT NOT NULL,
                event_date TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
            );
            """
        )

        # Migration: add supervisor_name column to campaigns if it doesn't exist
        try:
            conn.execute("ALTER TABLE campaigns ADD COLUMN supervisor_name TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS uploaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                file_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                file_path TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visitor_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                asked_at TEXT NOT NULL,
                answered INTEGER NOT NULL DEFAULT 0,
                session_id TEXT,
                source TEXT NOT NULL DEFAULT 'website'
            );

            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prompt_templates (
                name TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        defaults = {
            "assistant_name": "معين الزائرين",
            "system_prompt": "",
            "calendar_file": "",
            "campaign_list_file": "",
            "timezone": "Asia/Riyadh",
            "organization_name": "",
            "mosque_name": "",
            "default_language": "ar",
            "country": "",
            "city": "",
            "gemini_api_key": "",
            "ai_model": "gemini-1.5-flash",
            "ai_temperature": "0.3",
            "ai_max_tokens": "1024",
            "whatsapp_bot_number": "",
            "whatsapp_welcome_message": "",
            "whatsapp_fallback_message": "",
            "session_timeout_minutes": "60",
        }
        for key, value in defaults.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO system_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, utc_now()),
            )

        prompt_defaults = {
            "system_prompt": (
                "أنت مساعد ذكي لمسجد. تجيب على أسئلة الزائرين بدقة ووضوح باستخدام المعلومات المتوفرة."
            ),
            "campaign_prompt": (
                "استخرج معلومات الحملة من رسالة المشرف: اسم الحملة، رقم واتساب، "
                "الرسالة، التاريخ، تاريخ الانتهاء، والمعلومات المستخرجة."
            ),
            "visitor_prompt": (
                "أجب على سؤال الزائر بناءً على المعرفة المتوفرة والحملات النشطة والتقويم الإسلامي."
            ),
            "update_prompt": (
                "حدد ما إذا كانت رسالة الزائر تتطلب تحديث معلومات الحملة أم مجرد استفسار."
            ),
        }
        for name, content in prompt_defaults.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO prompt_templates (name, content, updated_at)
                VALUES (?, ?, ?)
                """,
                (name, content, utc_now()),
            )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, utc_now()),
        )


def get_all_settings() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM system_settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def create_campaign(name: str, whatsapp_number: str, status: str = "active") -> dict[str, Any]:
    phone = normalize_phone(whatsapp_number)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO campaigns (name, whatsapp_number, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), phone, status, utc_now()),
        )
        campaign_id = cur.lastrowid
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    return row_to_dict(row)


def update_campaign(campaign_id: int, name: str, whatsapp_number: str, status: str) -> dict[str, Any] | None:
    phone = normalize_phone(whatsapp_number)
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE campaigns
            SET name = ?, whatsapp_number = ?, status = ?
            WHERE id = ?
            """,
            (name.strip(), phone, status, campaign_id),
        )
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
    return row_to_dict(row)


def delete_campaign(campaign_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    return cur.rowcount > 0


def list_campaigns() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM campaigns ORDER BY created_at DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_campaign_by_phone(phone: str) -> dict[str, Any] | None:
    normalized = normalize_phone(phone)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE whatsapp_number = ? AND status = 'active'",
            (normalized,),
        ).fetchone()
    return row_to_dict(row)


def list_campaigns_with_stats() -> list[dict[str, Any]]:
    """List campaigns enriched with supervisor_name, last update time and total updates count.

    Campaigns are read-only from the admin UI; this view powers the read-only
    Campaigns page. The data itself is managed automatically by the AI from
    WhatsApp messages.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.name,
                COALESCE(c.supervisor_name, '') AS supervisor_name,
                c.whatsapp_number,
                c.status,
                c.created_at,
                (
                    SELECT MAX(cm.created_at)
                    FROM campaign_messages cm
                    WHERE cm.campaign_id = c.id
                ) AS last_update,
                (
                    SELECT COUNT(*)
                    FROM campaign_messages cm
                    WHERE cm.campaign_id = c.id
                ) AS total_updates
            FROM campaigns c
            ORDER BY last_update DESC NULLS LAST, c.created_at DESC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_campaign_messages(campaign_id: int) -> list[dict[str, Any]]:
    """Return all campaign update messages for a campaign, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM campaign_messages
            WHERE campaign_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (campaign_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def delete_campaign_message(message_id: int) -> bool:
    """Delete a single campaign update message. Returns True if a row was removed."""
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM campaign_messages WHERE id = ?", (message_id,)
        )
    return cur.rowcount > 0


def add_campaign_message(
    campaign_id: int,
    campaign_name: str,
    original_message: str,
    extracted_info: str,
    event_date: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO campaign_messages (
                campaign_id, campaign_name, original_message, extracted_info,
                event_date, expires_at, created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                campaign_id,
                campaign_name,
                original_message,
                extracted_info,
                event_date,
                expires_at,
                utc_now(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM campaign_messages WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return row_to_dict(row)


def get_active_campaign_messages() -> list[dict[str, Any]]:
    from date_utils import get_timezone

    tz = get_timezone()
    today = datetime.now(tz).date().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM campaign_messages
            WHERE is_active = 1
              AND (expires_at IS NULL OR expires_at >= ?)
            ORDER BY created_at DESC
            """,
            (today,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_campaign_activity_report() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT cm.campaign_name AS campaign,
                   cm.original_message AS last_message,
                   cm.extracted_info,
                   cm.created_at AS date
            FROM campaign_messages cm
            INNER JOIN (
                SELECT campaign_id, MAX(id) AS max_id
                FROM campaign_messages
                GROUP BY campaign_id
            ) latest ON cm.id = latest.max_id
            ORDER BY cm.created_at DESC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def upsert_uploaded_file(
    filename: str,
    file_type: str,
    size_bytes: int,
    file_path: str,
    uploaded_at: str | None = None,
) -> dict[str, Any]:
    uploaded_at = uploaded_at or utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO uploaded_files (filename, file_type, size_bytes, uploaded_at, file_path)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                file_type = excluded.file_type,
                size_bytes = excluded.size_bytes,
                uploaded_at = excluded.uploaded_at,
                file_path = excluded.file_path
            """,
            (filename, file_type, size_bytes, uploaded_at, file_path),
        )
        row = conn.execute(
            "SELECT * FROM uploaded_files WHERE filename = ?", (filename,)
        ).fetchone()
    return row_to_dict(row)


def delete_uploaded_file_record(filename: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM uploaded_files WHERE filename = ?", (filename,))


def list_uploaded_files_db() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM uploaded_files ORDER BY uploaded_at DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def add_visitor_question(
    question: str,
    answered: bool,
    session_id: str | None = None,
    source: str = "website",
) -> dict[str, Any]:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO visitor_questions (question, asked_at, answered, session_id, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (question.strip(), utc_now(), 1 if answered else 0, session_id, source),
        )
        row = conn.execute(
            "SELECT * FROM visitor_questions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return row_to_dict(row)


def get_dashboard_stats() -> dict[str, Any]:
    with get_connection() as conn:
        total_files = conn.execute("SELECT COUNT(*) AS c FROM uploaded_files").fetchone()["c"]
        total_campaigns = conn.execute("SELECT COUNT(*) AS c FROM campaigns").fetchone()["c"]
        total_campaign_messages = conn.execute(
            "SELECT COUNT(*) AS c FROM campaign_messages"
        ).fetchone()["c"]
        total_questions = conn.execute(
            "SELECT COUNT(*) AS c FROM visitor_questions"
        ).fetchone()["c"]
        total_unanswered = conn.execute(
            "SELECT COUNT(*) AS c FROM visitor_questions WHERE answered = 0"
        ).fetchone()["c"]

        latest_campaign = conn.execute(
            """
            SELECT campaign_name, created_at FROM campaign_messages
            ORDER BY created_at DESC LIMIT 1
            """
        ).fetchone()
        latest_file = conn.execute(
            "SELECT filename, uploaded_at FROM uploaded_files ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
        latest_question = conn.execute(
            "SELECT question, asked_at FROM visitor_questions ORDER BY asked_at DESC LIMIT 1"
        ).fetchone()
        latest_unanswered = conn.execute(
            """
            SELECT question, asked_at FROM visitor_questions
            WHERE answered = 0 ORDER BY asked_at DESC LIMIT 1
            """
        ).fetchone()

    return {
        "total_knowledge_files": total_files,
        "total_campaigns": total_campaigns,
        "total_campaign_messages": total_campaign_messages,
        "total_visitor_questions": total_questions,
        "total_unanswered_questions": total_unanswered,
        "latest_campaign_update": row_to_dict(latest_campaign),
        "latest_uploaded_file": row_to_dict(latest_file),
        "latest_visitor_question": row_to_dict(latest_question),
        "latest_unanswered_question": row_to_dict(latest_unanswered),
    }


def get_top_visitor_questions(limit: int = 10) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT question, COUNT(*) AS question_count
            FROM visitor_questions
            GROUP BY LOWER(TRIM(question))
            ORDER BY question_count DESC, question ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_unanswered_questions(limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT question, asked_at
            FROM visitor_questions
            WHERE answered = 0
            ORDER BY asked_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PROMPT_NAMES = ("system_prompt", "campaign_prompt", "visitor_prompt", "update_prompt")


def get_prompt(name: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT content FROM prompt_templates WHERE name = ?", (name,)
        ).fetchone()
    if row:
        return row["content"]
    # Fallback to system_settings for backward compatibility (system_prompt)
    if name == "system_prompt":
        return get_setting("system_prompt", default)
    return default


def set_prompt(name: str, content: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO prompt_templates (name, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at
            """,
            (name, content, utc_now()),
        )
    # Keep system_settings.system_prompt in sync for backward compatibility
    if name == "system_prompt":
        set_setting("system_prompt", content)


def get_all_prompts() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, content FROM prompt_templates"
        ).fetchall()
    result = {row["name"]: row["content"] for row in rows}
    # Ensure all expected prompts exist
    for name in PROMPT_NAMES:
        if name not in result:
            result[name] = get_prompt(name)
    return result


# ---------------------------------------------------------------------------
# Admin password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password with a random salt using PBKDF2-HMAC-SHA256."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100000)
    return f"pbkdf2_sha256${salt}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        if stored.startswith("pbkdf2_sha256$"):
            parts = stored.split("$")
            if len(parts) != 3:
                return False
            salt = parts[1]
            expected = parts[2]
            h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100000)
            return secrets.compare_digest(h.hex(), expected)
        # Fallback: plaintext (legacy)
        return secrets.compare_digest(password, stored)
    except Exception:
        return False


def get_admin_user(username: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM admin_users WHERE username = ?", (username,)
        ).fetchone()
    return row_to_dict(row)


def upsert_admin_user(username: str, password_hash: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO admin_users (username, password_hash, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, updated_at = excluded.updated_at
            """,
            (username, password_hash, utc_now()),
        )


def change_admin_password(username: str, new_password: str) -> None:
    upsert_admin_user(username, hash_password(new_password))


# ---------------------------------------------------------------------------
# Uploaded file info helpers
# ---------------------------------------------------------------------------

def get_uploaded_file_by_filename(filename: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM uploaded_files WHERE filename = ?", (filename,)
        ).fetchone()
    return row_to_dict(row)
