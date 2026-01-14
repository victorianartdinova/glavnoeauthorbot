# Правила разработки

*Обновлено: 2026-01-14*

## Журнал контента (Journal)

### Правило 1: Дата записи = selected_date

**Source of Truth для даты записи — это selected_date из UI, а НЕ datetime.now() или created_at.**

```
✅ Правильно:
   entry.date = selected_date  # Дата, которую выбрал пользователь в календаре

❌ Неправильно:
   entry.date = datetime.now()  # Текущая дата создания
```

При сохранении записи:
1. `planned_for` устанавливается на `selected_date`
2. `published_at` для опубликованных записей тоже берётся из `selected_date`
3. `_extract_date()` возвращает приоритетно `planned_for`, затем `published_at`

### Правило 2: Планирование и генерация — разные режимы

| Режим | Описание | Статус | Текст |
|-------|----------|--------|-------|
| **Plan-only** | Только тема, без генерации | `planned` | Тема поста |
| **Generated** | Полный сгенерированный пост | `planned` или `published` | Полный текст |

**Plan-only записи:**
- Создаются через "🗓 Заполнить план"
- Содержат только темы (по строке)
- Отображаются как "📝 В плане"
- НЕ увеличивают счётчик "Опубликовано"
- Можно сгенерировать пост позже через "⚙️ Сгенерировать пост"

### Правило 3: Генерация не меняет дату

При генерации контента по planned-entry:
1. Дата записи (`entry.date`) НЕ меняется
2. Обновляется только `content` и опционально `format`
3. Статус остаётся `planned` до явной публикации

```python
# ✅ Правильно
update_entry(client, entry_id, {"text": generated_text})

# ❌ Неправильно
update_entry(client, entry_id, {
    "text": generated_text,
    "date": datetime.now()  # НЕ ДЕЛАТЬ!
})
```

## Тестирование

Критические тесты в `tests/test_journal_dates.py`:
- `test_entry_date_equals_selected_date_not_now` — дата = selected_date
- `test_planned_topics_does_not_increase_published_count` — план не считается опубликованным
- `test_update_entry_preserves_date` — генерация не меняет дату
