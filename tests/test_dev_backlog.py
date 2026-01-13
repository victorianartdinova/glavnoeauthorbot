"""
Тесты для Dev Backlog
"""
import os
import sys

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dev_backlog import (
    DevBacklogStore,
    sync_backlog_to_md,
    create_from_feedback,
    title_hash,
    normalize_title,
    BACKLOG_MD,
    STATUS_MD
)
from utils.database import init_db


def test_create_task():
    """Тест: создание задачи попадает в store"""
    init_db()  # Убедимся что таблицы созданы

    store = DevBacklogStore()

    # Создаём уникальную задачу
    import time
    unique_title = f"Test task {time.time()}"

    task_id = store.create(
        title=unique_title,
        type="feature",
        priority="P2"
    )

    assert task_id is not None, "Задача должна быть создана"

    # Проверяем что задача в store
    task = store.get(task_id)
    assert task is not None, "Задача должна быть в store"
    assert task["title"] == unique_title
    assert task["type"] == "feature"
    assert task["priority"] == "P2"
    assert task["status"] == "todo"

    # Cleanup
    store.delete(task_id)
    print("✅ test_create_task passed")


def test_deduplication():
    """Тест: дедупликация по хешу заголовка"""
    init_db()
    store = DevBacklogStore()

    title = "Duplicate test task"

    # Первое создание
    task_id_1 = store.create(title=title, type="bug", priority="P1")
    assert task_id_1 is not None

    # Второе создание с тем же заголовком
    task_id_2 = store.create(title=title, type="feature", priority="P2")
    assert task_id_2 is None, "Дубликат не должен создаваться"

    # Cleanup
    store.delete(task_id_1)
    print("✅ test_deduplication passed")


def test_sync_backlog_to_md():
    """Тест: sync_backlog_to_md() обновляет файлы"""
    init_db()
    store = DevBacklogStore()

    # Создаём тестовую задачу
    import time
    task_id = store.create(
        title=f"Sync test {time.time()}",
        type="feature",
        priority="P0"
    )

    # Синхронизируем
    result = sync_backlog_to_md()

    # Проверяем что файлы созданы
    assert os.path.exists(result["backlog"]), "BACKLOG.md должен существовать"
    assert os.path.exists(result["status"]), "STATUS.md должен существовать"

    # Проверяем содержимое BACKLOG.md
    with open(BACKLOG_MD, "r", encoding="utf-8") as f:
        content = f.read()
        assert "# Dev Backlog" in content
        assert "P0" in content

    # Cleanup
    store.delete(task_id)
    print("✅ test_sync_backlog_to_md passed")


def test_create_from_feedback():
    """Тест: автоопределение типа и приоритета"""
    init_db()

    # Баг
    task = create_from_feedback("баг: кнопка не работает")
    assert task is not None
    assert task["type"] == "bug"
    assert task["priority"] == "P1"

    # Cleanup
    from utils.dev_backlog import backlog_store
    backlog_store.delete(task["id"])

    # P0 по ключевому слову
    task2 = create_from_feedback("срочно: память течёт")
    assert task2 is not None
    assert task2["priority"] == "P0"
    backlog_store.delete(task2["id"])

    print("✅ test_create_from_feedback passed")


def test_status_change():
    """Тест: изменение статуса"""
    init_db()
    store = DevBacklogStore()

    import time
    task_id = store.create(title=f"Status test {time.time()}", type="feature")

    # Меняем статус
    store.set_status(task_id, "in_progress")
    task = store.get(task_id)
    assert task["status"] == "in_progress"

    store.set_status(task_id, "done")
    task = store.get(task_id)
    assert task["status"] == "done"

    # Cleanup
    store.delete(task_id)
    print("✅ test_status_change passed")


if __name__ == "__main__":
    print("Running Dev Backlog tests...\n")

    test_create_task()
    test_deduplication()
    test_sync_backlog_to_md()
    test_create_from_feedback()
    test_status_change()

    print("\n✅ All tests passed!")
