# Архитектура Glavnoe Bot — Контент-система для недвижимости

**Дата:** 2025-01-09
**Статус:** В разработке (парсер готов, нужны API credentials)

---

## 🎯 Цель системы

Автоматизировать генерацию **живого, авторского** контента для агентств недвижимости через:
1. Парсинг каналов конкурентов и экспертов
2. Анализ через Claude API
3. Генерацию контента с учётом реальных трендов рынка

---

## 🏗️ Архитектура (2 системы)

```
┌─────────────────────────────────────────────────────────────┐
│                    GLAVNOE ECOSYSTEM                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐         ┌─────────────────┐            │
│  │ telegram-parser │  ────>  │  glavnoe-bot    │            │
│  │                 │         │                 │            │
│  │ • Парсинг       │         │ • Генерация     │            │
│  │ • Фильтрация    │         │ • Команды       │            │
│  │ • Анализ        │         │ • Claude API    │            │
│  └─────────────────┘         └─────────────────┘            │
│         │                             │                      │
│         │                             │                      │
│         v                             v                      │
│  ┌──────────────────────────────────────────────┐           │
│  │     KNOWLEDGE_BASE (общая база знаний)       │           │
│  │                                               │           │
│  │  • competitors/ — паттерны лидген-постов     │           │
│  │  • market_context/ — тренды рынка            │           │
│  └──────────────────────────────────────────────┘           │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Компоненты

### 1. telegram-parser (парсер каналов)

**Локация:** `/root/telegram-parser/`

**Задачи:**
- Парсинг Telegram-каналов (Telethon)
- Фильтрация постов по категориям
- Анализ через Claude API
- Еженедельные summary

**Структура:**
```
telegram-parser/
├── run_scraper.py           # Парсинг каналов
├── filters.py               # Фильтрация по keywords
├── weekly_summarizer.py     # Анализ через Claude
├── config/
│   └── channels.json        # Whitelist каналов + фильтры
└── output/
    ├── scraped_posts.json   # Сырые посты
    └── weekly-summaries/    # Результаты анализа
```

**Категории каналов:**

1. **Competitors** (лидген/конкуренты)
   - По сегментам: premium, business_class, comfort_class
   - Извлекаем: структуру постов, триггеры, CTA

2. **Market Context** (эксперты/аналитика)
   - Тренды рынка, болевые точки, термины

**Конфиг:** `config/channels.json`

**Текущие каналы:**
- Competitors: `leaseandsale`, `Kharyb`
- Market context: `opencity`, `chtogderealty`

---

### 2. glavnoe-bot (контент-генератор)

**Локация:** `/root/glavnoe-bot/`

**Задачи:**
- Telegram-бот для генерации контента
- Команды: `/brief`, `/plan`, `/live`, `/voice_intro`
- Интеграция с Claude API

**Структура:**
```
glavnoe-bot/
├── bot.py                   # Основной бот
├── handlers/                # Обработчики команд
├── utils/
│   └── claude_api.py        # Claude API
└── docs/
    ├── CLIENTS/             # Контекст клиентов
    │   └── apple_real_estate/
    │       ├── TONE_OF_VOICE.md
    │       ├── GOALS.md
    │       └── ...
    └── KNOWLEDGE_BASE/      # База знаний (из parser)
        ├── competitors/
        └── market_context/
```

**Команды:**
- `/brief` — ТЗ для дизайнера (баннеры Telegram Ads)
- `/plan` — контент-план на неделю
- `/live` — подводка к Instagram-посту
- `/voice_intro` — подводка к голосовому контенту

---

## 🔄 Workflow (как работает система)

### Еженедельный цикл:

```
1. ПАРСИНГ (автоматически, раз в неделю)
   └─> telegram-parser мониторит каналы
       └─> Сохраняет посты в JSON

2. ФИЛЬТРАЦИЯ (автоматически)
   └─> filters.py отбирает релевантные посты
       └─> keywords: "жк", "ипотека", "млн" и т.д.

3. АНАЛИЗ (автоматически)
   └─> weekly_summarizer.py → Claude API
       └─> Извлекает:
           • Паттерны лидген-постов
           • Триггеры конверсии
           • Тренды рынка
           • Стиль и формулировки

4. СОХРАНЕНИЕ
   └─> Результат → docs/KNOWLEDGE_BASE/
       ├── competitors/2025-01-09.md
       └── market_context/2025-01-09.md

5. ИСПОЛЬЗОВАНИЕ
   └─> glavnoe-bot читает KNOWLEDGE_BASE
       └─> Добавляет в промпты при генерации
```

### Генерация контента:

```
Пользователь → /brief → glavnoe-bot
                           │
                           v
             Загружает контекст:
             • TONE_OF_VOICE.md (стиль клиента)
             • KNOWLEDGE_BASE/competitors/ (паттерны)
             • KNOWLEDGE_BASE/market_context/ (тренды)
                           │
                           v
                     Claude API
                           │
                           v
             Готовый контент → Telegram
```

---

## 🚀 Запуск системы

### Шаг 1: Получить Telegram API credentials

1. Иди на https://my.telegram.org/auth
2. Войди через телефон
3. API development tools → Create application
4. Получи `api_id` и `api_hash`

### Шаг 2: Обновить .env

Отредактируй `/root/telegram-parser/.env`:
```bash
TG_API_ID=your_api_id_here
TG_API_HASH=your_api_hash_here
TG_PHONE=+79959077370
```

### Шаг 3: Первый запуск парсера

```bash
cd /root/telegram-parser
source venv/bin/activate
python run_scraper.py
```

При первом запуске:
- Придёт код в Telegram
- Введи код для авторизации
- Парсинг начнётся автоматически

### Шаг 4: Анализ постов через Claude

```bash
python weekly_summarizer.py
```

Результат → `glavnoe-bot/docs/KNOWLEDGE_BASE/`

### Шаг 5: Запуск glavnoe-bot

```bash
cd /root/glavnoe-bot
source venv/bin/activate
python bot.py
```

---

## 📊 Автоматизация (cron)

**Еженедельный парсинг + анализ:**

```bash
crontab -e
```

Добавь:
```cron
# Каждый понедельник в 9:00
0 9 * * 1 cd /root/telegram-parser && source venv/bin/activate && python run_scraper.py && python weekly_summarizer.py
```

---

## 🎯 Результат

**Что получаешь:**

1. **Автоматическая база знаний**
   - Обновляется раз в неделю
   - Паттерны конкурентов
   - Тренды рынка

2. **Живой контент**
   - Не "ботовский"
   - Основан на реальных каналах
   - Авторский стиль + инсайты рынка

3. **Масштабируемость**
   - Легко добавить новые каналы
   - Работает для любых клиентов
   - Автоматическое обновление

---

## 📝 Что дальше

### После получения API credentials:

1. ✅ Запустить парсер
2. ✅ Получить первый summary
3. ✅ Протестировать `/brief` с новым контекстом
4. ✅ Сравнить "до/после" (ботовский vs живой)

### Для масштабирования:

1. Добавить больше каналов в `config/channels.json`
2. Настроить фильтры под специфику клиента
3. Создать контекст для новых клиентов
4. Автоматизировать через cron

---

## 🔗 Полезные ссылки

- [README парсера](../telegram-parser/README_RU.md)
- [CONTEXT главного бота](./CONTEXT.md)
- [Конфиг каналов](../telegram-parser/config/channels.json)

---

**Готово!** Система готова к запуску после получения API credentials 🚀
