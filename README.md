# Glavnoe Bot

Telegram-бот для автоматизации создания контента и рекламных пакетов для агентства лидгена в недвижимости.

## Возможности

- ✅ Приём лотов от клиентов в едином формате
- ✅ Проверка условий для Telegram Ads
- 🚧 Автоматическая генерация контент-планов (7-10 дней)
- 🚧 Создание авторских постов через Claude API
- 🚧 Формирование AdPack (ТЗ дизайнеру + тексты объявлений)
- 🚧 Обучение на метриках эффективности

## Быстрый старт

### 1. Установка зависимостей

```bash
cd /root/glavnoe-bot
pip install -r requirements.txt
```

### 2. Настройка

Создай `.env` файл:

```bash
cp .env.example .env
nano .env
```

Укажи токен бота (уже прописан в `config.py`).

### 3. Запуск

```bash
python bot.py
```

Или в фоне через tmux:

```bash
tm
cd /root/glavnoe-bot
python bot.py
```

## Команды бота

- `/start` — приветствие
- `/lot` — добавить новый лот
- `/plan` — создать контент-план
- `/metrics` — обновить метрики постов
- `/help` — справка

## Структура проекта

```
glavnoe-bot/
├── bot.py                    # Главный файл бота
├── config.py                 # Конфигурация
├── handlers/                 # Обработчики команд
│   ├── lot_handler.py        # Добавление лотов
│   ├── content_handler.py    # Создание контента
│   └── metrics_handler.py    # Обновление метрик
├── utils/                    # Утилиты
├── docs/                     # Документация и данные
│   └── CLIENTS/              # Папки клиентов
│       └── _TEMPLATE/        # Шаблон структуры клиента
├── glavnoe-bot-context.md    # Полный контекст для Claude
└── requirements.txt          # Зависимости
```

## Формат лота

```
CLIENT: client_slug
LOT_NAME: ЖК Пример / 2К / набережная
LOT_LINK: https://example.com/lot
COMMENT_FROM_CLIENT: описание от клиента
PRESENTATION: https://... или NONE
CONDITIONS:
  - DOWNPAYMENT: 5000000
  - MONTHLY_PAYMENT: 150000
  - DISCOUNT: UNKNOWN
  - SALES_START: YES
REQUEST: AUTO
```

## Roadmap

- [x] Базовая структура бота
- [x] Приём и сохранение лотов
- [x] Проверка условий Telegram Ads
- [ ] Интеграция Claude API для генерации контента
- [ ] Создание контент-планов
- [ ] Генерация постов
- [ ] Формирование AdPack
- [ ] Система метрик и обучения
- [ ] Автопубликация в Telegram-каналы

## Техническая документация

Полный контекст работы бота: [glavnoe-bot-context.md](glavnoe-bot-context.md)

---

**Разработано с помощью Claude Code** 🤖
