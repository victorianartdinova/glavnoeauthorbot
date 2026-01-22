#!/usr/bin/env python3

"""
GitHub Webhook Listener для Glavnoe Bot
Слушает push события с GitHub и запускает auto_update.sh

Установка:
1. Создай Personal Access Token на GitHub (Settings → Developer settings → Personal access tokens)
2. Добавь webhook в репозиторий: Settings → Webhooks → Add webhook
   - Payload URL: http://YOUR_VPS_IP:8765/webhook
   - Content type: application/json
   - Events: Just the push event
   - Secret: сгенерируй какое-то значение и используй его ниже

3. Создай файл /home/user/glavnoeauthorbot/.webhook_secret с секретом
4. Запусти: python3 scripts/webhook_listener.py
"""

import os
import sys
import json
import hmac
import hashlib
import subprocess
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import logging

# Настройка логирования
LOG_DIR = Path("/var/log/glavnoe-bot")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "webhook.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Конфигурация
BOT_DIR = Path("/home/user/glavnoeauthorbot")
WEBHOOK_SECRET_FILE = BOT_DIR / ".webhook_secret"
TARGET_BRANCH = "claude/fix-yandex-parsing-issues-1TFAw"
WEBHOOK_PORT = 8765
WEBHOOK_PATH = "/webhook"

# Скрипт для обновления
UPDATE_SCRIPT = BOT_DIR / "scripts" / "auto_update.sh"

# Прочитай secret из файла
if not WEBHOOK_SECRET_FILE.exists():
    logger.error(f"Secret file not found: {WEBHOOK_SECRET_FILE}")
    logger.info("Create it with: echo 'YOUR_SECRET' > " + str(WEBHOOK_SECRET_FILE))
    sys.exit(1)

with open(WEBHOOK_SECRET_FILE) as f:
    WEBHOOK_SECRET = f.read().strip()

logger.info(f"Webhook listener configured for branch: {TARGET_BRANCH}")
logger.info(f"Secret loaded from: {WEBHOOK_SECRET_FILE}")


class WebhookHandler(BaseHTTPRequestHandler):
    """Обработчик GitHub webhook запросов"""

    def do_POST(self):
        """Обработка POST запроса"""

        # Проверяем path
        if self.path != WEBHOOK_PATH:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        # Получаем размер content-length
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No Content")
            return

        # Читаем body
        body = self.rfile.read(content_length)

        # Проверяем signature (безопасность!)
        if not self._verify_signature(body):
            logger.warning(f"Invalid signature from {self.client_address[0]}")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return

        # Парсим JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        # Логируем событие
        event_type = self.headers.get("X-GitHub-Event", "unknown")
        logger.info(f"Received GitHub event: {event_type}")

        # Обрабатываем push события
        if event_type == "push":
            self._handle_push(payload)
        else:
            logger.info(f"Ignoring event type: {event_type}")

        # Отправляем OK
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _verify_signature(self, body: bytes) -> bool:
        """Проверяет HMAC signature из GitHub"""

        # Получаем заголовок
        signature = self.headers.get("X-Hub-Signature-256")
        if not signature:
            logger.warning("No signature header found")
            return False

        # Вычисляем ожидаемую signature
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        # Сравниваем (используем constant-time comparison)
        return hmac.compare_digest(signature, expected)

    def _handle_push(self, payload: dict):
        """Обрабатывает push событие"""

        # Получаем информацию о push
        ref = payload.get("ref", "")
        branch = ref.split("/")[-1] if "/" in ref else ref
        repo_name = payload.get("repository", {}).get("full_name", "unknown")
        pusher = payload.get("pusher", {}).get("name", "unknown")
        commits = payload.get("commits", [])

        logger.info(f"Push to {repo_name}:{branch} by {pusher}")
        logger.info(f"Commits: {len(commits)}")

        # Проверяем что это наша ветка
        if branch != TARGET_BRANCH:
            logger.info(f"Ignoring push to {branch} (not {TARGET_BRANCH})")
            return

        # Логируем коммиты
        for commit in commits:
            msg = commit.get("message", "").split("\n")[0]
            commit_id = commit.get("id", "")[:7]
            logger.info(f"  - {commit_id}: {msg}")

        # Запускаем скрипт обновления
        logger.info(f"Triggering auto-update for {TARGET_BRANCH}...")
        self._run_update_script()

    def _run_update_script(self):
        """Запускает скрипт обновления в фоне"""

        try:
            # Проверяем что скрипт существует
            if not UPDATE_SCRIPT.exists():
                logger.error(f"Update script not found: {UPDATE_SCRIPT}")
                return

            # Убеждаемся что скрипт исполняемый
            if not os.access(UPDATE_SCRIPT, os.X_OK):
                os.chmod(UPDATE_SCRIPT, 0o755)
                logger.info(f"Made script executable: {UPDATE_SCRIPT}")

            # Запускаем скрипт в фоне
            logger.info(f"Running: {UPDATE_SCRIPT}")
            subprocess.Popen(
                [str(UPDATE_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Отделяем в новую сессию
            )
            logger.info("Update script started in background")

        except Exception as e:
            logger.error(f"Failed to run update script: {e}")

    def log_message(self, format, *args):
        """Переопределяем логирование HTTP запросов"""
        logger.debug(f"{self.client_address[0]} - {format % args}")


class QuietHTTPServer(HTTPServer):
    """HTTPServer без default логирования"""
    def log_message(self, format, *args):
        pass


def main():
    """Запускает webhook listener"""

    logger.info("=" * 60)
    logger.info("GLAVNOE BOT - WEBHOOK LISTENER")
    logger.info("=" * 60)

    logger.info(f"Listening on 0.0.0.0:{WEBHOOK_PORT}{WEBHOOK_PATH}")
    logger.info(f"Target branch: {TARGET_BRANCH}")
    logger.info(f"Update script: {UPDATE_SCRIPT}")
    logger.info("Waiting for GitHub webhooks...")

    server = QuietHTTPServer(("0.0.0.0", WEBHOOK_PORT), WebhookHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
