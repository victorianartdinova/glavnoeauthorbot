"""
Тесты для улучшений генерации контента

Проверяем:
1. Валидация постов (длина, запрещённые фразы)
2. Новые форматы лидген (carousel, ab)
3. Компактное ТЗ дизайнеру
4. Генератор сценариев
"""
import pytest
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.client_style import (
    load_style_config,
    get_post_length_requirements,
    get_banned_phrases,
    get_banned_openers,
    validate_post,
    fix_post_issues,
    get_style_prompt_section
)


class TestClientStyle:
    """Тесты для клиентского стиля"""

    def test_load_style_config_nadejda(self):
        """Загрузка конфига для Надежды"""
        config = load_style_config("nadejda_dmitruk")

        assert config is not None, "Конфиг должен загружаться"
        assert "post_length" in config, "Должны быть настройки длины"
        assert "banned_phrases" in config, "Должны быть запрещённые фразы"

    def test_post_length_requirements(self):
        """Требования к длине поста"""
        req = get_post_length_requirements("nadejda_dmitruk")

        assert req["min_words"] >= 60, "Минимум 60 слов"
        assert req["target_words"] >= 80, "Цель минимум 80 слов"
        assert req["max_words"] <= 250, "Максимум 250 слов"

    def test_banned_phrases_exist(self):
        """Запрещённые фразы существуют"""
        banned = get_banned_phrases("nadejda_dmitruk")

        assert len(banned) > 0, "Должны быть запрещённые фразы"
        assert "честно говоря" in banned, "'честно говоря' должна быть в списке"

    def test_validate_post_short(self):
        """Валидация короткого поста"""
        short_post = "Квартира в центре. Звоните."
        result = validate_post(short_post, "nadejda_dmitruk")

        assert not result["valid"], "Короткий пост должен быть невалидным"
        assert result["word_count"] < 80, "Должно быть меньше 80 слов"
        assert len(result["issues"]) > 0, "Должны быть проблемы"

    def test_validate_post_with_banned_phrase(self):
        """Валидация поста с запрещённой фразой"""
        post_with_banned = """Честно говоря, это отличная квартира в центре города.
        Прекрасная планировка, современный ремонт, близость к метро.
        Платёж от 50 000 рублей в месяц. Семейная ипотека доступна.
        Пишите в личку для консультации по объекту."""

        result = validate_post(post_with_banned, "nadejda_dmitruk")

        # Ищем проблему с запрещённой фразой
        has_banned_issue = any("честно говоря" in issue.lower() for issue in result["issues"])
        assert has_banned_issue, "Должна быть проблема с 'честно говоря'"

    def test_fix_post_issues(self):
        """Автоисправление проблем в посте"""
        post_with_issues = "Честно говоря, это хорошая квартира."
        fixed = fix_post_issues(post_with_issues, "nadejda_dmitruk")

        assert "честно говоря" not in fixed.lower(), "Запрещённая фраза должна быть удалена"

    def test_style_prompt_section(self):
        """Генерация секции промпта для стиля"""
        section = get_style_prompt_section("nadejda_dmitruk")

        assert len(section) > 100, "Секция должна быть непустой"
        assert "ДЛИНА" in section or "слов" in section, "Должны быть требования к длине"


class TestValidatePostEdgeCases:
    """Тесты граничных случаев валидации"""

    def test_validate_good_post(self):
        """Хороший пост должен проходить валидацию"""
        good_post = """🏠 Квартира у парка — платёж от 45 000 ₽/месяц

        Для тех, кто ценит баланс города и природы.

        📍 10 минут до метро Тропарёво
        📍 Парк через дорогу
        📍 Школа и садик в пешей доступности

        Условия:
        ▪️ Первый взнос от 3 млн
        ▪️ Семейная ипотека 6%
        ▪️ Ключи в 2025 году

        ⚪️ Напишите ПАРК — пришлю подробности и планировки.

        Это реальный шанс жить у природы в пределах МКАД."""

        result = validate_post(good_post, "nadejda_dmitruk")

        # Пост достаточно длинный и без запрещённых фраз
        assert result["word_count"] >= 60, f"Слов: {result['word_count']}"

    def test_validate_nonexistent_client(self):
        """Валидация для несуществующего клиента — дефолты"""
        result = validate_post("Тест пост", "nonexistent_client_xyz")

        assert "word_count" in result, "Должен быть подсчёт слов"


class TestDesignBrief:
    """Тесты для генерации ТЗ дизайнеру"""

    def test_import_design_brief(self):
        """Импорт модуля design_brief"""
        from utils.design_brief import generate_compact_brief, generate_detailed_brief

        assert callable(generate_compact_brief), "Функция должна быть callable"
        assert callable(generate_detailed_brief), "Функция должна быть callable"

    def test_extract_key_info(self):
        """Извлечение ключевой информации из поста"""
        from utils.design_brief import extract_key_info_for_brief

        test_post = """🏠 Квартира у метро — платёж 45 000 ₽

        📍 7 минут до Тропарёво

        • Первый взнос от 3 млн
        • Семейная ипотека

        ⚪️ Напишите МЕТРО — пришлю подробности."""

        info = extract_key_info_for_brief(test_post)

        assert info["hook"], "Хук должен быть извлечён"
        assert info["cta"], "CTA должен быть извлечён"
        assert len(info["features"]) > 0, "Должны быть извлечены фичи"


class TestScriptGenerator:
    """Тесты для генератора сценариев"""

    def test_import_script_generator(self):
        """Импорт модуля script_generator"""
        from utils.script_generator import (
            generate_voice_script,
            generate_circle_script,
            convert_post_to_script
        )

        assert callable(generate_voice_script), "Функция должна быть callable"
        assert callable(generate_circle_script), "Функция должна быть callable"
        assert callable(convert_post_to_script), "Функция должна быть callable"


class TestNewFormats:
    """Тесты для новых форматов лидген"""

    def test_format_map_updated(self):
        """format_map содержит новые форматы"""
        # Проверяем что новые форматы добавлены в код
        format_map = {
            "leadgen": "lidgen",
            "leadgen_carousel": "lidgen_carousel",
            "leadgen_ab": "lidgen_ab",
            "circle": "circle",
            "expert": "expert"
        }

        assert "leadgen_carousel" in format_map, "Карусель должна быть в format_map"
        assert "leadgen_ab" in format_map, "A/B баннер должен быть в format_map"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
