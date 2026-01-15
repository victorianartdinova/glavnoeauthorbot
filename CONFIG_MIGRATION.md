# Миграция конфигурации GLAVNOE Bot

## Что изменилось

### Новая структура
```
config/
├── __init__.py       # Публичный API
├── settings.py       # Настройки с валидацией
└── validation.py     # Валидация идентичности
```

### Защита от смешивания env

**До:**
```python
import config
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
```

**После:**
```python
from config import validate_bot_identity

# В main():
bot = await validate_bot_identity()  # Проверяет username!
```

## Новые фичи

### 1. Валидация на старте
Бот теперь **падает при запуске**, если:
- Username не совпадает с ожидаемым
- Найдены env от других ботов (VIRAL_*, VIRALE_*, etc)
- Используются устаревшие ключи (BOT_TOKEN)

### 2. Bot Identity
```python
from config import BOT_IDENTITY, EXPECTED_BOT_USERNAME

print(BOT_IDENTITY)  # BotIdentity.GLAVNOE
print(EXPECTED_BOT_USERNAME)  # "glavnoeauthor_bot"
```

### 3. Redact Secrets
```python
from config import redact_secret

token = "8499202304:AAF2FULsVpXGapbC3yvXpCdX3kvOgcdNvyU"
print(redact_secret(token))  # "84992...dNvyU"
```

## Проверка здоровья

Запусти doctor script перед стартом:
```bash
python scripts/doctor.py
```

Проверяет:
- ✅ Наличие .env
- ✅ Корректность конфигурации
- ✅ Отсутствие конфликтов
- ✅ Telegram getMe (правильный username)

## Обратная совместимость

Старый `import config` всё ещё работает, но выдаёт DeprecationWarning.

**Рекомендуется:**
```python
# Вместо:
import config
x = config.TELEGRAM_BOT_TOKEN

# Используй:
from config import TELEGRAM_BOT_TOKEN
x = TELEGRAM_BOT_TOKEN
```

## Запуск бота

```bash
# 1. Проверка
python scripts/doctor.py

# 2. Запуск
python bot.py
```

При старте бот выведет:
```
🔍 Проверка идентичности бота...
   Identity: GLAVNOE
   Expected Username: @glavnoeauthor_bot
✅ Идентичность бота подтверждена
🔄 Запуск polling...
```

## Что делать при ошибке

### "❌ Username НЕ СОВПАДАЕТ"
Проверь:
1. Правильный ли токен в `.env`?
2. Это точно `@glavnoeauthor_bot`?
3. Не скопирован ли `.env` от другого бота?

### "❌ Найдены запрещённые env-переменные"
Удали из `.env`:
- VIRAL_BOT_TOKEN
- VIRALE_BOT_TOKEN
- VIKA_BOT_TOKEN
- BOT_TOKEN (legacy)

### "❌ Найдены устаревшие env-ключи"
Переименуй в `.env`:
- `BOT_TOKEN` → `TELEGRAM_BOT_TOKEN`

## Тесты

```bash
# Unit-тесты
pytest tests/test_config.py -v

# Smoke-check
python scripts/doctor.py
```
