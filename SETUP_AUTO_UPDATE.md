# 🚀 Настройка Автоматического Обновления для Glavnoe Bot

**Смысл**: Когда ты делаешь `git push` из VS Code, изменения **сразу же** автоматически применяются на VPS.

---

## 📋 Что это делает?

1. **Webhook Listener** слушает события с GitHub на порту 8765
2. Когда ты делаешь push в ветку `claude/fix-yandex-parsing-issues-1TFAw`:
   - GitHub отправляет webhook уведомление
   - Listener запускает `auto_update.sh` в фоне
   - Скрипт пулит изменения, проверяет синтаксис, перезапускает бота
3. **Всё происходит автоматически** за 5-10 секунд

---

## ✅ Шаг 1: Создай Secret для GitHub

Запусти на VPS:

```bash
cd /home/user/glavnoeauthorbot

# Генерируем случайный secret
python3 << 'EOF'
import secrets
secret = secrets.token_urlsafe(32)
print(f"SECRET: {secret}")
with open(".webhook_secret", "w") as f:
    f.write(secret)
EOF

# Проверь
cat .webhook_secret
# Копируй этот secret - он понадобится в GitHub
```

Сохрани значение secret, оно будет нужно в следующем шаге.

---

## ✅ Шаг 2: Добавь Webhook в GitHub репозиторий

1. Открой репозиторий на GitHub: https://github.com/victorianartdinova/glavnoeauthorbot
2. Перейди в **Settings** → **Webhooks** → **Add webhook**
3. Заполни форму:
   ```
   Payload URL: http://YOUR_VPS_IP:8765/webhook
   Content type: application/json
   Secret: [ВСТАВЬ secret из шага 1]
   Events: ✓ Just the push event
   Active: ✓ ДА
   ```
4. Нажми **Add webhook**

**Как узнать свой IP VPS?**
```bash
curl -s https://api.ipify.org
# или
hostname -I | awk '{print $1}'
```

---

## ✅ Шаг 3: Установи Webhook Listener как Systemd Сервис

Запусти на VPS:

```bash
# Копируем systemd сервис
sudo cp /home/user/glavnoeauthorbot/scripts/glavnoe-webhook.service \
        /etc/systemd/system/

# Перезагружаем конфиги systemd
sudo systemctl daemon-reload

# Запускаем сервис
sudo systemctl start glavnoe-webhook

# Проверяем статус
sudo systemctl status glavnoe-webhook

# Включаем автозапуск (запустится при перезагрузке VPS)
sudo systemctl enable glavnoe-webhook
```

**Проверка что работает:**
```bash
# Смотрим логи
sudo journalctl -u glavnoe-webhook -f

# Или смотрим файл логов
tail -f /var/log/glavnoe-bot/webhook.log
```

Должно быть что-то вроде:
```
2026-01-22 15:45:32 - INFO - ================================================================================
2026-01-22 15:45:32 - INFO - GLAVNOE BOT - WEBHOOK LISTENER
2026-01-22 15:45:32 - INFO - ================================================================================
2026-01-22 15:45:32 - INFO - Listening on 0.0.0.0:8765/webhook
2026-01-22 15:45:32 - INFO - Target branch: claude/fix-yandex-parsing-issues-1TFAw
2026-01-22 15:45:32 - INFO - Waiting for GitHub webhooks...
```

---

## ✅ Шаг 4: Проверка что Webhook работает

**Способ 1: Тестовый push из VS Code**

1. Сделай небольшое изменение в файле (например, добавь комментарий)
2. Commit: `git add . && git commit -m "test: webhook trigger"`
3. Push в нужную ветку:
   ```bash
   git push origin claude/fix-yandex-parsing-issues-1TFAw
   ```
4. Смотри логи на VPS:
   ```bash
   tail -f /var/log/glavnoe-bot/webhook.log
   ```

Должно быть:
```
2026-01-22 15:46:12 - INFO - Received GitHub event: push
2026-01-22 15:46:12 - INFO - Push to victorianartdinova/glavnoeauthorbot:claude/fix-yandex-parsing-issues-1TFAw by your_username
2026-01-22 15:46:12 - INFO - Triggering auto-update for claude/fix-yandex-parsing-issues-1TFAw...
2026-01-22 15:46:12 - INFO - Update script started in background
```

**Способ 2: Проверь логи обновления**

```bash
tail -f /var/log/glavnoe-bot/auto_update.log
```

Должно быть что-то вроде:
```
[2026-01-22 15:46:13] [INFO] ========== AUTO UPDATE STARTED ==========
[2026-01-22 15:46:13] [INFO] → Проверка директории...
[2026-01-22 15:46:13] [INFO] ✓ Директория OK: /home/user/glavnoeauthorbot
[2026-01-22 15:46:14] [INFO] ✓ Новые изменения получены
[2026-01-22 15:46:14] [INFO] ✓ Синтаксис OK
[2026-01-22 15:46:14] [INFO] ✓ Бот остановлен
[2026-01-22 15:46:15] [INFO] ✓ Конфигурация OK
[2026-01-22 15:46:16] [INFO] ✓ Бот запущен (PID: 12345)
[2026-01-22 15:46:16] [INFO] ========== AUTO UPDATE COMPLETED SUCCESSFULLY ==========
```

---

## 🔧 Альтернатива: Запусти вручную (без webhook)

Если webhook не работает, можешь запустить обновление вручную:

```bash
# На VPS запусти:
/home/user/glavnoeauthorbot/scripts/auto_update.sh
```

Это сделает то же самое: пулит, проверит синтаксис, перезапустит бота.

---

## 🛠️ Диагностика Проблем

### ❌ Webhook не приходит

1. **Проверь IP в GitHub Webhook:**
   ```bash
   # На VPS:
   curl -s https://api.ipify.org
   # Убедись что это IP совпадает с тем, что указан в GitHub
   ```

2. **Проверь что порт 8765 открыт:**
   ```bash
   sudo netstat -tlnp | grep 8765
   # Или:
   sudo ss -tlnp | grep 8765
   ```

3. **Проверь статус сервиса:**
   ```bash
   sudo systemctl status glavnoe-webhook
   ```

4. **Смотри логи:**
   ```bash
   sudo journalctl -u glavnoe-webhook -n 50
   ```

### ❌ Сервис не запускается

```bash
# Проверь есть ли ошибки:
sudo systemctl start glavnoe-webhook 2>&1

# Смотри подробные логи:
sudo journalctl -u glavnoe-webhook -n 100 --all

# Проверь что Python3 установлен:
which python3
python3 --version
```

### ❌ Обновление не работает

```bash
# Запусти скрипт вручную для отладки:
bash -x /home/user/glavnoeauthorbot/scripts/auto_update.sh

# Смотри логи:
tail -100 /var/log/glavnoe-bot/auto_update.log
```

---

## 📝 Как это работает из VS Code

1. **В VS Code:** вносишь изменения, коммитишь, делаешь push
2. **GitHub получает:** твой push в ветку
3. **GitHub отправляет:** webhook на твой VPS (порт 8765)
4. **Webhook listener** принимает запрос, проверяет signature, запускает скрипт
5. **Auto update script** пулит изменения, перезапускает бота
6. **Результат:** твои изменения живут на VPS за 5-10 секунд! 🚀

---

## 📊 Мониторинг

**Смотри статус webhook сервиса:**
```bash
sudo systemctl status glavnoe-webhook
```

**Смотри логи webhook listener:**
```bash
tail -f /var/log/glavnoe-bot/webhook.log
```

**Смотри логи обновлений:**
```bash
tail -f /var/log/glavnoe-bot/auto_update.log
```

**Смотри логи самого бота:**
```bash
tail -f /var/log/glavnoe-bot/bot_output.log
```

---

## 🚨 Emergency: Остановить webhook сервис

Если что-то пошло не так:

```bash
# Останови сервис
sudo systemctl stop glavnoe-webhook

# Отключи автозапуск
sudo systemctl disable glavnoe-webhook

# Можешь запустить снова когда будешь готов:
sudo systemctl start glavnoe-webhook
sudo systemctl enable glavnoe-webhook
```

---

## ✨ Готово!

Теперь **каждый раз когда ты делаешь push**, бот автоматически обновляется на VPS 🎉

**Проверь:**
1. Webhook listener запущен: `sudo systemctl status glavnoe-webhook`
2. Secret создан: `cat /home/user/glavnoeauthorbot/.webhook_secret`
3. Webhook добавлен в GitHub
4. Сделай тестовый push и проверь логи
