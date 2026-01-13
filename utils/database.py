"""
База данных Glavnoe Bot — SQLite
"""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
from contextlib import contextmanager

import config


DB_PATH = os.path.join(config.BASE_DIR, "data", "glavnoe.db")


def now_iso() -> str:
    """Текущее время в ISO формате (UTC)"""
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    """Получить соединение с БД"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Доступ к колонкам по имени
    return conn


@contextmanager
def db_connection():
    """Context manager для соединения"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Инициализация таблиц"""
    with db_connection() as conn:
        conn.executescript("""
            -- Посты (журнал контента)
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                title TEXT,
                content TEXT,
                format TEXT,                        -- lidgen, case, meme, expert, etc.
                status TEXT NOT NULL DEFAULT 'draft', -- draft|planned|published
                planned_for TEXT,                   -- ISO datetime
                published_at TEXT,                  -- ISO datetime
                telegram_chat_id TEXT,
                telegram_message_id INTEGER,
                source TEXT DEFAULT 'bot_generated', -- bot_generated|forwarded|from_plan
                hook_type TEXT,                     -- financial, location, premium, etc.
                angle TEXT,
                cta TEXT,
                lot_id TEXT,
                lot_name TEXT,
                link TEXT,                          -- ссылка на пост в канале
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_posts_client_planned_for
            ON posts (client_id, planned_for);

            CREATE INDEX IF NOT EXISTS idx_posts_client_status
            ON posts (client_id, status);

            CREATE INDEX IF NOT EXISTS idx_posts_client_date
            ON posts (client_id, published_at);

            -- Контент-планы
            CREATE TABLE IF NOT EXISTS content_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                period INTEGER DEFAULT 7,           -- дней в плане
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_plans_client
            ON content_plans (client_id);

            -- Дни планов (связь план -> посты)
            CREATE TABLE IF NOT EXISTS plan_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                day_num INTEGER NOT NULL,           -- 1, 2, 3...
                date TEXT NOT NULL,                 -- DD.MM или YYYY-MM-DD
                weekday TEXT,                       -- Пн, Вт...
                FOREIGN KEY (plan_id) REFERENCES content_plans(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_plan_days_plan
            ON plan_days (plan_id);

            -- Посты в плане (связь день -> посты)
            CREATE TABLE IF NOT EXISTS plan_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_day_id INTEGER NOT NULL,
                post_id INTEGER,                    -- ссылка на posts.id (может быть NULL пока не создан)
                format TEXT NOT NULL,
                topic TEXT,
                is_ads INTEGER DEFAULT 0,           -- для рекламы
                protected INTEGER DEFAULT 0,        -- защищён от удаления
                status TEXT DEFAULT 'pending',      -- pending|written|approved|sent
                raw_content TEXT,
                FOREIGN KEY (plan_day_id) REFERENCES plan_days(id) ON DELETE CASCADE,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_plan_posts_day
            ON plan_posts (plan_day_id);

            -- Dev Backlog (задачи разработки)
            CREATE TABLE IF NOT EXISTS dev_backlog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'feature',   -- bug|feature|debt
                priority TEXT NOT NULL DEFAULT 'P2',    -- P0|P1|P2|P3
                status TEXT NOT NULL DEFAULT 'todo',    -- todo|in_progress|done|blocked
                source TEXT DEFAULT 'user',             -- user|auto
                notes TEXT,
                related_files TEXT,                     -- JSON array
                acceptance_criteria TEXT,
                last_seen_context TEXT,
                title_hash TEXT,                        -- для дедупликации
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_dev_backlog_status
            ON dev_backlog (status);

            CREATE INDEX IF NOT EXISTS idx_dev_backlog_priority
            ON dev_backlog (priority);

            CREATE INDEX IF NOT EXISTS idx_dev_backlog_hash
            ON dev_backlog (title_hash);
        """)
        conn.commit()


# ===================
# PostsStore — работа с постами
# ===================

class PostsStore:
    """CRUD для постов (журнал контента)"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        client_id: str,
        content: str,
        format: str = "lidgen",
        status: str = "draft",
        title: Optional[str] = None,
        planned_for: Optional[str] = None,
        source: str = "bot_generated",
        hook_type: Optional[str] = None,
        angle: Optional[str] = None,
        cta: Optional[str] = None,
        lot_id: Optional[str] = None,
        lot_name: Optional[str] = None,
        link: Optional[str] = None
    ) -> int:
        """Создать пост"""
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO posts (
                client_id, title, content, format, status, planned_for,
                source, hook_type, angle, cta, lot_id, lot_name, link,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            client_id, title, content, format, status, planned_for,
            source, hook_type, angle, cta, lot_id, lot_name, link,
            ts, ts
        ))
        self.conn.commit()
        return cur.lastrowid

    def create_draft(self, client_id: str, title: Optional[str] = None, content: Optional[str] = None) -> int:
        """Создать черновик"""
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO posts (client_id, title, content, status, created_at, updated_at)
            VALUES (?, ?, ?, 'draft', ?, ?)
        """, (client_id, title, content, ts, ts))
        self.conn.commit()
        return cur.lastrowid

    def get(self, post_id: int) -> Optional[Dict]:
        """Получить пост по ID"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def update(self, post_id: int, **kwargs) -> bool:
        """Обновить поля поста"""
        if not kwargs:
            return False

        kwargs["updated_at"] = now_iso()
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [post_id]

        self.conn.execute(f"UPDATE posts SET {fields} WHERE id = ?", values)
        self.conn.commit()
        return True

    def set_planned(self, post_id: int, planned_for_iso: str):
        """Запланировать пост"""
        ts = now_iso()
        self.conn.execute("""
            UPDATE posts
            SET status='planned', planned_for=?, updated_at=?
            WHERE id=?
        """, (planned_for_iso, ts, post_id))
        self.conn.commit()

    def mark_published(self, post_id: int, chat_id: str = None, message_id: int = None):
        """Отметить как опубликованный"""
        ts = now_iso()
        self.conn.execute("""
            UPDATE posts
            SET status='published', telegram_chat_id=?, telegram_message_id=?,
                published_at=?, updated_at=?
            WHERE id=?
        """, (str(chat_id) if chat_id else None, message_id, ts, ts, post_id))
        self.conn.commit()

    def delete(self, post_id: int) -> bool:
        """Удалить пост"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- Выборки ---

    def get_by_client(self, client_id: str, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Посты клиента"""
        cur = self.conn.cursor()
        if status:
            cur.execute("""
                SELECT * FROM posts
                WHERE client_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (client_id, status, limit))
        else:
            cur.execute("""
                SELECT * FROM posts
                WHERE client_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (client_id, limit))
        return [dict(row) for row in cur.fetchall()]

    def get_by_date(self, client_id: str, date: str) -> List[Dict]:
        """Посты за дату (YYYY-MM-DD)"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM posts
            WHERE client_id = ? AND (
                DATE(planned_for) = ? OR DATE(published_at) = ?
            )
            ORDER BY created_at
        """, (client_id, date, date))
        return [dict(row) for row in cur.fetchall()]

    def get_by_week(self, client_id: str, week_start: str, week_end: str) -> List[Dict]:
        """Посты за неделю"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM posts
            WHERE client_id = ? AND (
                (planned_for >= ? AND planned_for < ?) OR
                (published_at >= ? AND published_at < ?)
            )
            ORDER BY COALESCE(planned_for, published_at)
        """, (client_id, week_start, week_end, week_start, week_end))
        return [dict(row) for row in cur.fetchall()]

    def week_stats(self, client_id: str, week_start_iso: str, week_end_iso: str) -> Tuple[int, int]:
        """Статистика за неделю (published, planned)"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                SUM(CASE WHEN status='published' AND published_at>=? AND published_at<? THEN 1 ELSE 0 END) AS published,
                SUM(CASE WHEN status='planned' AND planned_for>=? AND planned_for<? THEN 1 ELSE 0 END) AS planned
            FROM posts
            WHERE client_id=?
        """, (week_start_iso, week_end_iso, week_start_iso, week_end_iso, client_id))
        row = cur.fetchone() or (0, 0)
        return (row[0] or 0, row[1] or 0)


# ===================
# PlansStore — работа с планами
# ===================

class PlansStore:
    """CRUD для контент-планов"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, client_id: str, period: int = 7) -> int:
        """Создать план"""
        ts = now_iso()
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO content_plans (client_id, period, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (client_id, period, ts, ts))
        self.conn.commit()
        return cur.lastrowid

    def get(self, plan_id: int) -> Optional[Dict]:
        """Получить план с днями и постами"""
        cur = self.conn.cursor()

        # План
        cur.execute("SELECT * FROM content_plans WHERE id = ?", (plan_id,))
        plan_row = cur.fetchone()
        if not plan_row:
            return None

        plan = dict(plan_row)

        # Дни
        cur.execute("""
            SELECT * FROM plan_days WHERE plan_id = ? ORDER BY day_num
        """, (plan_id,))
        days = []
        for day_row in cur.fetchall():
            day = dict(day_row)

            # Посты дня
            cur.execute("""
                SELECT * FROM plan_posts WHERE plan_day_id = ?
            """, (day["id"],))
            day["posts"] = [dict(p) for p in cur.fetchall()]
            days.append(day)

        plan["days"] = days
        return plan

    def get_latest(self, client_id: str) -> Optional[Dict]:
        """Последний план клиента"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT id FROM content_plans
            WHERE client_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (client_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self.get(row["id"])

    def add_day(self, plan_id: int, day_num: int, date: str, weekday: str = "") -> int:
        """Добавить день в план"""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO plan_days (plan_id, day_num, date, weekday)
            VALUES (?, ?, ?, ?)
        """, (plan_id, day_num, date, weekday))
        self.conn.commit()
        return cur.lastrowid

    def add_post_to_day(
        self,
        plan_day_id: int,
        format: str,
        topic: str = "",
        is_ads: bool = False,
        protected: bool = False,
        raw_content: str = ""
    ) -> int:
        """Добавить пост к дню"""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO plan_posts (plan_day_id, format, topic, is_ads, protected, raw_content)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (plan_day_id, format, topic, int(is_ads), int(protected), raw_content))
        self.conn.commit()
        return cur.lastrowid

    def update_plan_post(self, plan_post_id: int, **kwargs) -> bool:
        """Обновить пост в плане"""
        if not kwargs:
            return False

        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [plan_post_id]

        self.conn.execute(f"UPDATE plan_posts SET {fields} WHERE id = ?", values)
        self.conn.commit()
        return True

    def delete(self, plan_id: int) -> bool:
        """Удалить план (каскадно удалит дни и посты)"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM content_plans WHERE id = ?", (plan_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def list_plans(self, client_id: str, limit: int = 10) -> List[Dict]:
        """Список планов клиента"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM content_plans
            WHERE client_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (client_id, limit))
        return [dict(row) for row in cur.fetchall()]


# ===================
# Инициализация при импорте
# ===================

# Создаём таблицы при первом импорте
init_db()
