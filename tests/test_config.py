"""
Unit-тесты для модуля конфигурации
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

# Добавляем корень проекта в PATH
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_env_isolation_forbidden_keys():
    """Тест: запрещённые ключи от других ботов вызывают ошибку"""
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "test_token",
        "ANTHROPIC_API_KEY": "test_key",
        "VIRAL_BOT_TOKEN": "should_fail",
    }):
        # Перезагружаем модуль
        import importlib
        if 'config.settings' in sys.modules:
            del sys.modules['config.settings']

        with pytest.raises(ValueError, match="запрещённые env-переменные"):
            import config.settings


def test_env_isolation_legacy_keys():
    """Тест: устаревшие ключи вызывают ошибку"""
    with patch.dict(os.environ, {
        "BOT_TOKEN": "legacy_token",
        "ANTHROPIC_API_KEY": "test_key",
    }, clear=True):
        import importlib
        if 'config.settings' in sys.modules:
            del sys.modules['config.settings']

        with pytest.raises(ValueError, match="устаревшие env-ключи"):
            import config.settings


def test_valid_env_loads():
    """Тест: валидный env загружается без ошибок"""
    with patch.dict(os.environ, {
        "TELEGRAM_BOT_TOKEN": "valid_token",
        "ANTHROPIC_API_KEY": "valid_key",
    }, clear=True):
        import importlib
        if 'config.settings' in sys.modules:
            del sys.modules['config.settings']

        try:
            import config.settings
            assert config.settings.TELEGRAM_BOT_TOKEN == "valid_token"
            assert config.settings.BOT_IDENTITY.value == "GLAVNOE"
        except Exception as e:
            pytest.fail(f"Valid env should load without errors: {e}")


def test_redact_secret():
    """Тест: функция redact_secret правильно скрывает секреты"""
    from config.settings import redact_secret

    assert redact_secret("1234567890abcdef") == "12345...bcdef"
    assert redact_secret("short") == "***"
    assert redact_secret("") == "***"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
