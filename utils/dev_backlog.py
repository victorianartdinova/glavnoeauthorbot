"""
Dev Backlog Store — персистентный бэклог задач разработки
"""
import json
import hashlib
import re
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict

from utils.database import db_connection, now_iso

import config

# Пути к MD-файлам
DOCS_DIR = os.path.join(config.BASE_DIR, "docs")
BACKLOG_MD = os.path.join(DOCS_DIR, "BACKLOG.md")
STATUS_MD = os.path.join(DOCS_DIR, "STATUS.md")


def normalize_title(title: str) -> str:
    """Нормализация заголовка для дедупликации"""
    # Lowercase, убираем пунктуацию, множественные пробелы
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def title_hash(title: str) -> str:
    """Хеш нормализованного заголовка"""
    return hashlib.md5(normalize_title(title).encode()).hexdigest()[:16]


class DevBacklogStore:
    """CRUD для dev_backlog"""

    def create(
        self,
        title: str,
        type: str = "feature",
        priority: str = "P2",
        status: str = "todo",
        source: str = "user",
        notes: Optional[str] = None,
        related_files: Optional[List[str]] = None,
        acceptance_criteria: Optional[str] = None,
        last_seen_context: Optional[str] = None
    ) -> Optional[int]:
        """Создать задачу (с дедупликацией)"""
        t_hash = title_hash(title)

        # Проверка дубликата
        existing = self.find_by_hash(t_hash)
        if existing:
            # Обновляем last_seen_context
            self.update(existing["id"], last_seen_context=last_seen_context)
            return None  # Дубликат

        ts = now_iso()
        files_json = json.dumps(related_files) if related_files else None

        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO dev_backlog (
                    title, type, priority, status, source, notes,
                    related_files, acceptance_criteria, last_seen_context,
                    title_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, type, priority, status, source, notes,
                files_json, acceptance_criteria, last_seen_context,
                t_hash, ts, ts
            ))
            conn.commit()
            return cur.lastrowid

    def get(self, task_id: int) -> Optional[Dict]:
        """Получить задачу по ID"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM dev_backlog WHERE id = ?", (task_id,))
            row = cur.fetchone()
            if row:
                d = dict(row)
                if d.get("related_files"):
                    d["related_files"] = json.loads(d["related_files"])
                return d
            return None

    def find_by_hash(self, t_hash: str) -> Optional[Dict]:
        """Найти задачу по хешу заголовка"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM dev_backlog
                WHERE title_hash = ? AND status != 'done'
            """, (t_hash,))
            row = cur.fetchone()
            if row:
                d = dict(row)
                if d.get("related_files"):
                    d["related_files"] = json.loads(d["related_files"])
                return d
            return None

    def find_similar(self, title: str) -> Optional[Dict]:
        """Найти похожую задачу"""
        return self.find_by_hash(title_hash(title))

    def update(self, task_id: int, **kwargs) -> bool:
        """Обновить задачу"""
        if not kwargs:
            return False

        # Конвертируем related_files в JSON
        if "related_files" in kwargs and kwargs["related_files"] is not None:
            kwargs["related_files"] = json.dumps(kwargs["related_files"])

        kwargs["updated_at"] = now_iso()
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [task_id]

        with db_connection() as conn:
            conn.execute(f"UPDATE dev_backlog SET {fields} WHERE id = ?", values)
            conn.commit()
        return True

    def set_status(self, task_id: int, status: str) -> bool:
        """Изменить статус"""
        return self.update(task_id, status=status)

    def delete(self, task_id: int) -> bool:
        """Удалить задачу"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM dev_backlog WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0

    # === Выборки ===

    def list_all(self, limit: int = 100) -> List[Dict]:
        """Все задачи (не done)"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM dev_backlog
                WHERE status != 'done'
                ORDER BY
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        WHEN 'P3' THEN 3
                    END,
                    created_at DESC
                LIMIT ?
            """, (limit,))
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def list_by_status(self, status: str, limit: int = 50) -> List[Dict]:
        """Задачи по статусу"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM dev_backlog
                WHERE status = ?
                ORDER BY
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        WHEN 'P3' THEN 3
                    END,
                    created_at DESC
                LIMIT ?
            """, (status, limit))
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def list_by_priority(self, priority: str, limit: int = 50) -> List[Dict]:
        """Задачи по приоритету"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM dev_backlog
                WHERE priority = ? AND status != 'done'
                ORDER BY created_at DESC
                LIMIT ?
            """, (priority, limit))
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """Поиск по заголовку и notes"""
        with db_connection() as conn:
            cur = conn.cursor()
            q = f"%{query}%"
            cur.execute("""
                SELECT * FROM dev_backlog
                WHERE (title LIKE ? OR notes LIKE ?)
                ORDER BY
                    CASE priority
                        WHEN 'P0' THEN 0
                        WHEN 'P1' THEN 1
                        WHEN 'P2' THEN 2
                        WHEN 'P3' THEN 3
                    END,
                    created_at DESC
                LIMIT ?
            """, (q, q, limit))
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def stats(self) -> Dict:
        """Статистика по бэклогу"""
        with db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT status, COUNT(*) as cnt
                FROM dev_backlog
                GROUP BY status
            """)
            by_status = {row["status"]: row["cnt"] for row in cur.fetchall()}

            cur.execute("""
                SELECT priority, COUNT(*) as cnt
                FROM dev_backlog
                WHERE status != 'done'
                GROUP BY priority
            """)
            by_priority = {row["priority"]: row["cnt"] for row in cur.fetchall()}

            return {
                "by_status": by_status,
                "by_priority": by_priority,
                "total_active": sum(v for k, v in by_status.items() if k != "done")
            }

    def _row_to_dict(self, row) -> Dict:
        """Конвертация строки в dict"""
        d = dict(row)
        if d.get("related_files"):
            d["related_files"] = json.loads(d["related_files"])
        return d


# === Синхронизация с MD ===

def sync_backlog_to_md():
    """Синхронизировать бэклог в BACKLOG.md и STATUS.md"""
    store = DevBacklogStore()
    tasks = store.list_all(limit=200)
    stats = store.stats()

    os.makedirs(DOCS_DIR, exist_ok=True)

    # BACKLOG.md
    lines = [
        "# Dev Backlog",
        "",
        f"*Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    # Группируем по приоритету
    for priority in ["P0", "P1", "P2", "P3"]:
        p_tasks = [t for t in tasks if t["priority"] == priority and t["status"] != "done"]
        if p_tasks:
            lines.append(f"## {priority}")
            lines.append("")
            for t in p_tasks:
                status_icon = {"todo": "⬜", "in_progress": "🔄", "blocked": "🚫"}.get(t["status"], "⬜")
                type_icon = {"bug": "🐛", "feature": "✨", "debt": "🔧"}.get(t["type"], "📝")
                lines.append(f"- {status_icon} {type_icon} **#{t['id']}** {t['title']}")
                if t.get("notes"):
                    lines.append(f"  - {t['notes'][:100]}...")
            lines.append("")

    with open(BACKLOG_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # STATUS.md (канбан)
    status_lines = [
        "# Dev Status",
        "",
        f"*Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Статистика",
        "",
        f"- Todo: {stats['by_status'].get('todo', 0)}",
        f"- In Progress: {stats['by_status'].get('in_progress', 0)}",
        f"- Blocked: {stats['by_status'].get('blocked', 0)}",
        f"- Done: {stats['by_status'].get('done', 0)}",
        "",
        "## In Progress",
        "",
    ]

    in_progress = store.list_by_status("in_progress")
    for t in in_progress:
        status_lines.append(f"- **#{t['id']}** {t['title']}")

    if not in_progress:
        status_lines.append("*Нет задач в работе*")

    status_lines.extend(["", "## Blocked", ""])
    blocked = store.list_by_status("blocked")
    for t in blocked:
        status_lines.append(f"- **#{t['id']}** {t['title']}")

    if not blocked:
        status_lines.append("*Нет заблокированных*")

    with open(STATUS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(status_lines))

    return {"backlog": BACKLOG_MD, "status": STATUS_MD}


# === Автосоздание задачи из фидбека ===

def create_from_feedback(
    text: str,
    source: str = "auto",
    context: Optional[str] = None
) -> Optional[Dict]:
    """
    Создать задачу из текста фидбека.
    Возвращает созданную задачу или None (дубликат).
    """
    store = DevBacklogStore()

    # Определяем тип по ключевым словам
    text_lower = text.lower()
    if any(w in text_lower for w in ["баг", "bug", "сломано", "не работает", "ошибка", "error"]):
        task_type = "bug"
        priority = "P1"
    elif any(w in text_lower for w in ["рефактор", "долг", "debt", "переписать"]):
        task_type = "debt"
        priority = "P2"
    else:
        task_type = "feature"
        priority = "P2"

    # Повышаем приоритет для критичных слов
    if any(w in text_lower for w in ["критично", "срочно", "urgent", "p0", "память", "статус"]):
        priority = "P0"
    elif any(w in text_lower for w in ["важно", "p1", "ux"]):
        priority = "P1"

    task_id = store.create(
        title=text[:200],
        type=task_type,
        priority=priority,
        source=source,
        last_seen_context=context
    )

    if task_id:
        return store.get(task_id)
    return None  # Дубликат


# Singleton для удобства
backlog_store = DevBacklogStore()
