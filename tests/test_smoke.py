"""
Smoke tests — минимальная проверка работоспособности бота
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_import_bot():
    """Проверка импорта bot.py без ошибок"""
    try:
        import bot
        assert bot.dp is not None
        assert bot.bot is not None
    except Exception as e:
        raise AssertionError(f"Failed to import bot.py: {e}")


def test_import_all_handlers():
    """Проверка импорта всех хендлеров"""
    handlers = [
        'handlers.content_handler',
        'handlers.plan_handler',
        'handlers.journal_handler',
        'handlers.meme_handler',
        'handlers.voice_handler',
        'handlers.focus_handler',
        'handlers.leadgen_cards_handler',
        'handlers.lot_handler',
        'handlers.client_handler',
        'handlers.metrics_handler',
        'handlers.dev_handler',
        'handlers.package_lot_handler'
    ]

    for handler_name in handlers:
        try:
            __import__(handler_name)
        except Exception as e:
            raise AssertionError(f"Failed to import {handler_name}: {e}")


def test_import_utils():
    """Проверка импорта утилит"""
    utils = [
        'utils.client_context',
        'utils.claude_api',
        'utils.jk_parser',
        'utils.content_state',
        'utils.plan_storage',
        'utils.content_journal',
        'utils.memory_store',
        'utils.anti_repeat',
        'utils.editor_pass'
    ]

    for util_name in utils:
        try:
            __import__(util_name)
        except Exception as e:
            raise AssertionError(f"Failed to import {util_name}: {e}")


def test_data_directories_exist():
    """Проверка существования директорий данных"""
    required_dirs = [
        'data',
        'data/content_journal',
        'data/plans',
        'data/memory'
    ]

    for dir_path in required_dirs:
        full_path = os.path.join(os.path.dirname(__file__), '..', dir_path)
        assert os.path.exists(full_path), f"Directory {dir_path} does not exist"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
