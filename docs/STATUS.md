# Dev Status

*Обновлено: 2026-01-14*

## Статистика

- Todo: 0
- In Progress: 0
- Blocked: 0
- Done: 8

## Завершено (14.01.2026)

### Сессия 2 — Улучшения генерации контента
- fix(nadezhda): Посты теперь длиннее и разнообразнее
  - Добавлен STYLE_CONFIG.json с min_words=80, banned_phrases, hook_templates
  - Валидация постов с подсчётом слов
  - Автоудаление запрещённых фраз
- feat(leadgen): Новые форматы
  - 🎠 Лидген-карусель (5-8 карточек)
  - 🔀 A/B баннер (рациональный/эмоциональный)
- fix(brief): Компактное ТЗ дизайнеру
  - По умолчанию короткое ТЗ (800-1200 символов)
  - Кнопка "📖 Развернуть ТЗ" для подробной версии
- feat(scripts): Генератор сценариев
  - 🎙 Голосовое (45-90 сек) с таймкодами
  - ⭕ Кружок (20-40 сек) с визуальными подсказками
  - Кнопка "🎙️ Сценарий" из любого поста
- tests: 8 unit-тестов для новых функций

### Сессия 1 — Журнал
- fix(journal): selected_date как source of truth
- feat(journal): plan-only режим (без генерации)
- feat(journal): кнопка генерации по planned-entry
- tests: 7 unit-тестов для журнала

## Новые файлы

- `utils/client_style.py` — валидация постов, стиль клиента
- `utils/design_brief.py` — компактные и подробные ТЗ
- `utils/script_generator.py` — сценарии для voice/circle
- `docs/CLIENTS/nadejda_dmitruk/STYLE_CONFIG.json` — настройки стиля
- `tests/test_content_improvements.py` — тесты

## In Progress

*Нет задач в работе*

## Blocked

*Нет заблокированных*
