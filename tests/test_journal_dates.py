"""
Тесты для проверки корректности работы с датами в журнале.

Ключевое правило: selected_date (выбранный в UI день) должен быть
source of truth для даты записи, а не datetime.now() или created_at.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Мокаем config до импорта модулей
import config
config.BASE_DIR = "/tmp/glavnoe_test"

from utils.database import init_db, db_connection, PostsStore


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Создаём временную БД для каждого теста"""
    import config
    from utils import database

    # Переопределяем путь к БД для изоляции тестов
    test_db_path = str(tmp_path / "data" / "glavnoe.db")
    config.BASE_DIR = str(tmp_path)
    database.DB_PATH = test_db_path

    # Создаём папку data
    os.makedirs(os.path.join(str(tmp_path), "data"), exist_ok=True)

    # Инициализируем БД
    init_db()
    yield


class TestAddEntryDate:
    """Тесты для add_entry: проверка сохранения selected_date"""

    def test_entry_date_equals_selected_date_not_now(self, setup_test_db):
        """
        Критический тест: дата записи должна быть selected_date,
        а НЕ datetime.now()
        """
        from utils.content_journal import add_entry, get_entries_by_date

        # Выбираем прошлую дату (как в UI при выборе Ср 14.01)
        past_date = "2026-01-08"  # Прошлая неделя

        entry_id = add_entry(
            client_slug="test_client",
            date=past_date,  # selected_date из UI
            format_type="lidgen",
            text="Тестовый пост",
            status="published",
            source="manual"
        )

        # Проверяем, что запись сохранена именно на past_date
        entries = get_entries_by_date("test_client", past_date)

        assert len(entries) == 1, "Запись должна быть на выбранную дату"
        assert entries[0]["date"] == past_date, f"Дата записи должна быть {past_date}, не сегодня"

    def test_planned_entry_uses_selected_date(self, setup_test_db):
        """Planned записи должны использовать selected_date"""
        from utils.content_journal import add_entry, get_entries_by_date

        future_date = "2026-01-20"

        entry_id = add_entry(
            client_slug="test_client",
            date=future_date,
            format_type="expert",
            text="Запланированный пост",
            status="planned",
            source="plan_only"
        )

        entries = get_entries_by_date("test_client", future_date)

        assert len(entries) == 1
        assert entries[0]["date"] == future_date
        assert entries[0]["status"] == "planned"


class TestAddPlannedTopics:
    """Тесты для add_planned_topics: plan-only записи"""

    def test_planned_topics_creates_entries_with_selected_date(self, setup_test_db):
        """Темы создаются с выбранной датой, не с текущей"""
        from utils.content_journal import add_planned_topics, get_entries_by_date

        selected_date = "2026-01-15"  # Среда
        topics = [
            "ЖК у метро за 15 млн",
            "Ошибки при покупке квартиры",
            "Обзор района Хамовники"
        ]

        entry_ids = add_planned_topics(
            client_slug="test_client",
            date=selected_date,
            topics=topics
        )

        assert len(entry_ids) == 3, "Должно создаться 3 записи"

        entries = get_entries_by_date("test_client", selected_date)
        assert len(entries) == 3, "Все 3 записи должны быть на выбранную дату"

        for entry in entries:
            assert entry["date"] == selected_date
            assert entry["status"] == "planned"

    def test_planned_topics_does_not_increase_published_count(self, setup_test_db):
        """Plan-only записи не должны увеличивать счётчик опубликованных"""
        from utils.content_journal import add_planned_topics, get_week_stats, get_week_start

        selected_date = "2026-01-15"
        week_start = datetime.strptime("2026-01-13", "%Y-%m-%d")  # Понедельник

        # Добавляем темы
        add_planned_topics(
            client_slug="test_client",
            date=selected_date,
            topics=["Тема 1", "Тема 2"]
        )

        stats = get_week_stats("test_client", week_start)

        assert stats["published"] == 0, "Plan-only записи не должны считаться опубликованными"
        assert stats["planned"] == 2, "Должно быть 2 запланированных"


class TestGenerationDoesNotChangeDate:
    """Тесты: генерация поста не должна менять дату записи"""

    def test_update_entry_preserves_date(self, setup_test_db):
        """При обновлении записи дата не должна меняться"""
        from utils.content_journal import add_entry, update_entry, get_entry_by_id

        original_date = "2026-01-08"

        entry_id = add_entry(
            client_slug="test_client",
            date=original_date,
            format_type="lidgen",
            text="Тема поста",
            status="planned",
            source="plan_only"
        )

        # Симулируем генерацию: обновляем текст и формат
        update_entry("test_client", str(entry_id), {
            "text": "Сгенерированный текст поста...",
            "format": "expert"
        })

        # Проверяем, что дата НЕ изменилась
        entry = get_entry_by_id("test_client", str(entry_id))

        assert entry is not None
        assert entry["date"] == original_date, "Дата не должна меняться при генерации"


class TestExtractDatePriority:
    """Тесты для _extract_date: проверка приоритета полей"""

    def test_planned_for_has_priority_over_created_at(self, setup_test_db):
        """planned_for должен иметь приоритет над created_at"""
        from utils.content_journal import _extract_date

        post = {
            "planned_for": "2026-01-15T00:00:00",
            "published_at": None,
            "created_at": "2026-01-14T12:30:00"  # Дата создания — сегодня
        }

        date = _extract_date(post)

        assert date == "2026-01-15", "Должна вернуться planned_for дата, не created_at"

    def test_planned_for_has_priority_over_published_at(self, setup_test_db):
        """planned_for должен иметь приоритет (selected_date)"""
        from utils.content_journal import _extract_date

        post = {
            "planned_for": "2026-01-08T00:00:00",  # selected_date — прошлая неделя
            "published_at": "2026-01-14T15:00:00",  # Фактическая публикация — сегодня
            "created_at": "2026-01-14T12:00:00"
        }

        date = _extract_date(post)

        # Для отображения в журнале важна planned_for (selected_date)
        assert date == "2026-01-08"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
