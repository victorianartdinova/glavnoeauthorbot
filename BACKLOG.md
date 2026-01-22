# BACKLOG — Glavnoe Bot

## Новые правила (январь 2026)

### UX лидген-карусели
- ✅ Принимаем текст/ссылки вместо JSON — парсим автоматически через `utils/text_parser.py`
- ✅ Если данных не хватает — бот задаёт 1-3 коротких вопроса (не спамим пользователя)
- ✅ "Сначала выбери клиента" показываем ОДИН раз в 60 сек (anti-spam throttle через `utils/anti_spam.py`)
- ✅ User-ошибки (не выбран клиент, неправильный шаг) — только пользователю, НЕ в TEAM_CHAT
- ✅ TEAM_CHAT только для реальных exceptions с stacktrace + correlation_id

### Cancel/timeout генерации
- ✅ Реальная отмена долгих задач: `asyncio.Task` per user+flow
- ✅ По Cancel → `task.cancel()` + освобождение FSM + мгновенный ответ "Отменено"
- ✅ Верхний таймаут 120 сек с graceful fallback (сообщение пользователю + лог)

### Кнопка "Дизайн" после лидген-карточек
- ✅ Добавлена кнопка "🎨 Дизайн" в результате генерации
- ✅ Сохраняем `lc_last_brief` в FSM state
- ✅ Callback `lc:design` отправляет ТЗ через `send_brief_to_designer()`

### Качество контента (nadejda_dmitruk)
- ✅ Tone Pack в `docs/CLIENTS/nadejda_dmitruk/TONE_OF_VOICE.md`:
  - Запрещённые клише: "честно говоря", "важно понимать", "поделюсь с вами"
  - Обязательные обороты: конкретные цифры, локация с минутами, личная интонация
  - Примеры "сушняк → живее"
  - Редакторский проход (5 правил)

### ТЗ дизайнеру
- ✅ Формат SHORT, компактный (буллеты, без канцеляризмов)
- ✅ Blacklist слов для рекламных баннеров в `utils/leadgen_cards.py`:
  - "собственных", "высококачественных", "уникальных", "эксклюзивных", "инновационных"
- ✅ Правило: 3-6 слов в заголовке, одно действие, один смысл

---

## TODO

### Тесты (ПРИОРИТЕТ 1)
- [ ] Unit-тесты:
  - Anti-spam throttle (`utils/anti_spam.py`)
  - Text parser (`utils/text_parser.py`)
  - Cancel mechanism (leadgen_cards_handler)
  - Callback routing для кнопки "Дизайн"
- [ ] Интеграционный тест:
  - Лидген-карусель end-to-end без JSON
  - Проверка генерации + кнопка дизайн + отправка в TEAM_CHAT

### Референсы ТЗ для дизайнера (ПРИОРИТЕТ 2)
- [ ] Admin-команда `📎 Референсы ТЗ` → сохранить в `data/design_refs/{client}.json`
- [ ] Использовать как source of truth при генерации ТЗ
- [ ] Обновить `BANNER_BRIEF_TEMPLATE.md` с новым форматом

### Backlog (ПРИОРИТЕТ 3)
- [ ] Транскрипция голосовых (внешний сервис) — файлы есть, нужна интеграция
- [ ] Metrics dashboard для клиентов
- [ ] A/B тестирование вариантов постов

---

## Архитектура

### Ключевые компоненты
- `handlers/leadgen_cards_handler.py` — лидген-карусель с text parser + cancel + timeout
- `utils/text_parser.py` — парсинг текст → структура (regex + эвристики)
- `utils/anti_spam.py` — throttle для предупреждений (60 сек cooldown)
- `utils/leadgen_cards.py` — генерация постов + SHORT ТЗ с blacklist
- `utils/team_chat.py` — отправка в командный чат (только exceptions)

### Клиенты
1. apple_real_estate — премиум жилая, от 25 млн
2. artem_solodkov — бизнес/премиум, персональный бренд
3. nadejda_dmitruk — комфорт+/бизнес, от 15 млн (+ tone pack)

---

## Версионирование

### v1.3 (15.01.2026)
- ✅ Text parser для лидген-карусели
- ✅ Anti-spam throttle
- ✅ Cancel mechanism с timeout
- ✅ Кнопка "Дизайн" после генерации
- ✅ Tone pack для nadejda_dmitruk
- ✅ SHORT ТЗ дизайнеру + blacklist слов

### v1.2 (12.01.2026)
- Журнал контента + пересылка постов
- Мемы из TG-парсера
- Связка контент-план ↔ посты

### v1.1 (10.01.2026)
- Multi-client архитектура
- Claude API интеграция
- 8 форматов контента
