"""
Журнал контента — хранение опубликованных и запланированных постов
Теперь использует SQLite вместо JSON
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from utils.database import db_connection, PostsStore, now_iso


def add_entry(
    client_slug: str,
    date: str,
    format_type: str,
    text: str,
    status: str = "published",
    source: str = "bot_generated",
    hook_type: Optional[str] = None,
    angle: Optional[str] = None,
    cta: Optional[str] = None,
    lot_id: Optional[str] = None,
    lot_name: Optional[str] = None,
    published_at: Optional[str] = None,
    link: Optional[str] = None
) -> int:
    """
    Добавить запись в журнал.

    Args:
        client_slug: slug клиента
        date: дата публикации (YYYY-MM-DD)
        format_type: формат (lidgen, case, meme, expert, digest, live, circle, podcast)
        text: полный текст поста
        status: planned | published
        source: bot_generated | forwarded | from_plan
        hook_type: тип хука (financial, location, premium, urgency, emotional)
        angle: угол/подход поста
        cta: call-to-action слово
        lot_id: ID лота (если есть)
        lot_name: название лота/ЖК
        published_at: фактическое время публикации
        link: ссылка на пост в канале

    Returns:
        ID записи
    """
    # Конвертируем date в ISO datetime для planned_for
    planned_for = None
    if date and status == "planned":
        try:
            planned_for = datetime.strptime(date, "%Y-%m-%d").isoformat()
        except ValueError:
            planned_for = None

    with db_connection() as conn:
        store = PostsStore(conn)
        post_id = store.create(
            client_id=client_slug,
            content=text,
            format=format_type.lower(),
            status=status,
            planned_for=planned_for,
            source=source,
            hook_type=hook_type,
            angle=angle,
            cta=cta,
            lot_id=lot_id,
            lot_name=lot_name,
            link=link
        )

        # Если уже опубликован, устанавливаем published_at
        if status == "published":
            pub_time = published_at or now_iso()
            store.update(post_id, published_at=pub_time)

    # Обновляем индекс истории (для совместимости)
    try:
        from utils.history_index import update_history_index
        entry = {
            "id": str(post_id),
            "date": date,
            "format": format_type,
            "text": text,
            "status": status
        }
        update_history_index(client_slug, entry)
    except ImportError:
        pass

    return post_id


def update_entry(client_slug: str, entry_id: str, updates: Dict) -> bool:
    """
    Обновить запись в журнале.

    Args:
        client_slug: slug клиента
        entry_id: ID записи (строка или int)
        updates: dict с обновлениями

    Returns:
        True если успешно
    """
    try:
        post_id = int(entry_id.replace("entry_", "")) if entry_id.startswith("entry_") else int(entry_id)
    except ValueError:
        return False

    # Конвертируем ключи для совместимости
    db_updates = {}
    if "text" in updates:
        db_updates["content"] = updates["text"]
    if "format" in updates:
        db_updates["format"] = updates["format"].lower()
    if "status" in updates:
        db_updates["status"] = updates["status"]
    if "link" in updates:
        db_updates["link"] = updates["link"]

    if not db_updates:
        return False

    with db_connection() as conn:
        store = PostsStore(conn)
        return store.update(post_id, **db_updates)


def delete_entry(client_slug: str, entry_id: str) -> bool:
    """Удалить запись из журнала"""
    try:
        post_id = int(entry_id.replace("entry_", "")) if entry_id.startswith("entry_") else int(entry_id)
    except ValueError:
        return False

    with db_connection() as conn:
        store = PostsStore(conn)
        return store.delete(post_id)


def load_journal(client_slug: str) -> List[Dict]:
    """
    Загрузить журнал клиента.
    Для обратной совместимости возвращает формат старого JSON.
    """
    with db_connection() as conn:
        store = PostsStore(conn)
        posts = store.get_by_client(client_slug, limit=500)

    # Конвертируем в старый формат
    entries = []
    for p in posts:
        entry = {
            "id": f"entry_{p['id']}",  # Совместимость со старым форматом ID
            "date": _extract_date(p),
            "format": p["format"] or "lidgen",
            "text": p["content"] or "",
            "status": p["status"],
            "source": p["source"] or "bot_generated",
            "created_at": p["created_at"]
        }
        if p.get("hook_type"):
            entry["hook_type"] = p["hook_type"]
        if p.get("angle"):
            entry["angle"] = p["angle"]
        if p.get("cta"):
            entry["cta"] = p["cta"]
        if p.get("lot_id"):
            entry["lot_id"] = p["lot_id"]
        if p.get("lot_name"):
            entry["lot_name"] = p["lot_name"]
        if p.get("published_at"):
            entry["published_at"] = p["published_at"]
        if p.get("link"):
            entry["link"] = p["link"]
        entries.append(entry)

    return entries


def _extract_date(post: Dict) -> str:
    """Извлечь дату из поста (YYYY-MM-DD)"""
    if post.get("published_at"):
        try:
            return post["published_at"][:10]
        except:
            pass
    if post.get("planned_for"):
        try:
            return post["planned_for"][:10]
        except:
            pass
    if post.get("created_at"):
        try:
            return post["created_at"][:10]
        except:
            pass
    return datetime.now().strftime("%Y-%m-%d")


def get_entries_by_date(client_slug: str, date: str) -> List[Dict]:
    """Получить записи за конкретную дату"""
    with db_connection() as conn:
        store = PostsStore(conn)
        posts = store.get_by_date(client_slug, date)

    # Конвертируем
    return [_post_to_entry(p) for p in posts]


def get_entries_by_week(client_slug: str, week_start: datetime) -> Dict[str, List[Dict]]:
    """
    Получить записи за неделю, сгруппированные по дням.

    Args:
        client_slug: slug клиента
        week_start: начало недели (понедельник)

    Returns:
        Dict: {date_str: [entries]}
    """
    week_end = week_start + timedelta(days=7)

    with db_connection() as conn:
        store = PostsStore(conn)
        posts = store.get_by_week(
            client_slug,
            week_start.isoformat(),
            week_end.isoformat()
        )

    # Группируем по дням
    result = {}
    for i in range(7):
        day = week_start + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        result[date_str] = []

    for p in posts:
        date_str = _extract_date(p)
        if date_str in result:
            result[date_str].append(_post_to_entry(p))

    return result


def _post_to_entry(post: Dict) -> Dict:
    """Конвертировать пост из БД в формат entry"""
    entry = {
        "id": f"entry_{post['id']}",
        "date": _extract_date(post),
        "format": post["format"] or "lidgen",
        "text": post["content"] or "",
        "status": post["status"],
        "source": post["source"] or "bot_generated",
        "created_at": post["created_at"]
    }
    for key in ["hook_type", "angle", "cta", "lot_id", "lot_name", "published_at", "link"]:
        if post.get(key):
            entry[key] = post[key]
    return entry


def get_week_start(date: datetime = None) -> datetime:
    """Получить начало недели (понедельник)"""
    if date is None:
        date = datetime.now()

    # Понедельник = 0, Воскресенье = 6
    days_since_monday = date.weekday()
    return date - timedelta(days=days_since_monday)


def format_journal_calendar(client_slug: str, week_start: datetime) -> str:
    """
    Форматировать журнал в виде календаря недели.

    Returns:
        Текст календаря для отображения
    """
    week_data = get_entries_by_week(client_slug, week_start)

    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    lines = [f"📅 *Журнал контента*"]
    lines.append(f"Неделя: {week_start.strftime('%d.%m')} — {(week_start + timedelta(days=6)).strftime('%d.%m')}")
    lines.append("")

    for i, (date_str, entries) in enumerate(week_data.items()):
        day = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = weekdays[i]
        day_display = day.strftime("%d.%m")

        if entries:
            # Есть записи
            status_icons = []
            for e in entries:
                if e["status"] == "published":
                    status_icons.append("✅")
                else:
                    status_icons.append("📝")

            formats = [e["format"].upper()[:3] for e in entries]
            lines.append(f"{' '.join(status_icons)} *{weekday} {day_display}*: {', '.join(formats)}")
        else:
            # Пусто
            lines.append(f"⬜ {weekday} {day_display}: —")

    # Статистика
    all_entries = [e for entries in week_data.values() for e in entries]
    published = len([e for e in all_entries if e["status"] == "published"])
    planned = len([e for e in all_entries if e["status"] == "planned"])

    lines.append("")
    lines.append(f"✅ Опубликовано: {published} | 📝 В плане: {planned}")

    return "\n".join(lines)


# Маппинг форматов
FORMAT_MAP = {
    "lidgen": "Лидген",
    "case": "Кейс",
    "meme": "Мем",
    "expert": "Эксперт",
    "digest": "Дайджест",
    "live": "Live",
    "circle": "Кружок",
    "podcast": "Подкаст",
}

FORMAT_EMOJI = {
    "lidgen": "🏢",
    "case": "📈",
    "meme": "😂",
    "expert": "💡",
    "digest": "📰",
    "live": "📱",
    "circle": "🎙",
    "podcast": "🎤",
}


def get_format_display(format_type: str) -> str:
    """Получить отображаемое название формата"""
    return FORMAT_MAP.get(format_type.lower(), format_type)


def get_format_emoji(format_type: str) -> str:
    """Получить эмодзи формата"""
    return FORMAT_EMOJI.get(format_type.lower(), "📝")


# ============
# Функции управления журналом
# ============

def clear_day(client_slug: str, date: str) -> int:
    """
    Очистить все записи за день.

    Args:
        client_slug: slug клиента
        date: дата в формате YYYY-MM-DD

    Returns:
        количество удалённых записей
    """
    with db_connection() as conn:
        cur = conn.cursor()
        # Удаляем записи где published_at или planned_for попадает на эту дату
        cur.execute("""
            DELETE FROM posts
            WHERE client_id = ? AND (
                DATE(published_at) = ? OR DATE(planned_for) = ?
            )
        """, (client_slug, date, date))
        conn.commit()
        return cur.rowcount


def clear_week(client_slug: str, week_start: datetime) -> int:
    """
    Очистить все записи за неделю.

    Args:
        client_slug: slug клиента
        week_start: начало недели (понедельник)

    Returns:
        количество удалённых записей
    """
    week_end = week_start + timedelta(days=7)

    with db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM posts
            WHERE client_id = ? AND (
                (published_at >= ? AND published_at < ?) OR
                (planned_for >= ? AND planned_for < ?)
            )
        """, (
            client_slug,
            week_start.isoformat(),
            week_end.isoformat(),
            week_start.isoformat(),
            week_end.isoformat()
        ))
        conn.commit()
        return cur.rowcount


def fill_week_from_plan(client_slug: str, week_start: datetime) -> int:
    """
    Заполнить журнал из контент-плана за неделю.

    Args:
        client_slug: slug клиента
        week_start: начало недели

    Returns:
        количество добавленных записей или -1 если плана нет
    """
    from utils.plan_storage import load_plan

    plan = load_plan(client_slug)
    if not plan:
        return -1  # Нет плана

    added = 0
    week_end = week_start + timedelta(days=7)

    for day in plan.get("days", []):
        # Парсим дату из плана (формат ДД.ММ или ДД.ММ.ГГГГ)
        date_str = day.get("date", "")
        try:
            if len(date_str.split(".")) == 2:
                day_num, month_num = date_str.split(".")
                year = datetime.now().year
                plan_date = datetime(year, int(month_num), int(day_num))
            else:
                day_num, month_num, year = date_str.split(".")
                if len(year) == 2:
                    year = f"20{year}"
                plan_date = datetime(int(year), int(month_num), int(day_num))
        except (ValueError, AttributeError):
            continue

        # Проверяем, попадает ли в нужную неделю
        if plan_date < week_start or plan_date >= week_end:
            continue

        # Добавляем посты дня
        for post in day.get("posts", []):
            format_type = post.get("format", "ПОСТ").lower()
            topic = post.get("topic", "")

            # Добавляем как запланированный
            add_entry(
                client_slug=client_slug,
                date=plan_date.strftime("%Y-%m-%d"),
                format_type=format_type,
                text=topic,
                status="planned",
                source="from_plan"
            )
            added += 1

    return added


def get_week_stats(client_slug: str, week_start: datetime) -> Dict[str, int]:
    """
    Получить статистику за неделю.

    Returns:
        {"published": N, "planned": M, "total": K}
    """
    week_data = get_entries_by_week(client_slug, week_start)
    all_entries = [e for entries in week_data.values() for e in entries]

    return {
        "published": len([e for e in all_entries if e["status"] == "published"]),
        "planned": len([e for e in all_entries if e["status"] == "planned"]),
        "total": len(all_entries)
    }


# ============
# Функция миграции JSON -> SQLite
# ============

def migrate_json_to_sqlite():
    """
    Миграция данных из старых JSON файлов в SQLite.
    Вызывать один раз при переходе.
    """
    import json
    import os
    import config

    json_dir = os.path.join(config.BASE_DIR, "data", "content_journal")

    if not os.path.exists(json_dir):
        print("Нет данных для миграции")
        return

    migrated = 0
    for client_slug in os.listdir(json_dir):
        client_dir = os.path.join(json_dir, client_slug)
        if not os.path.isdir(client_dir):
            continue

        journal_path = os.path.join(client_dir, "journal.json")
        if not os.path.exists(journal_path):
            continue

        print(f"Мигрирую {client_slug}...")

        with open(journal_path, "r", encoding="utf-8") as f:
            entries = json.load(f)

        for entry in entries:
            add_entry(
                client_slug=client_slug,
                date=entry.get("date", ""),
                format_type=entry.get("format", "lidgen"),
                text=entry.get("text", ""),
                status=entry.get("status", "published"),
                source=entry.get("source", "bot_generated"),
                hook_type=entry.get("hook_type"),
                angle=entry.get("angle"),
                cta=entry.get("cta"),
                lot_id=entry.get("lot_id"),
                lot_name=entry.get("lot_name"),
                published_at=entry.get("published_at") or entry.get("created_at"),
                link=entry.get("link")
            )
            migrated += 1

        # Переименовываем старый файл
        backup_path = journal_path + ".migrated"
        os.rename(journal_path, backup_path)
        print(f"  Мигрировано {len(entries)} записей, бекап: {backup_path}")

    print(f"\nВсего мигрировано: {migrated} записей")


# Для запуска миграции: python -c "from utils.content_journal import migrate_json_to_sqlite; migrate_json_to_sqlite()"
