"""
Планировщик для автоматического анализа победителей (self-learning).

Запускает анализ парсированных постов каждый понедельник в 10:30 (после парсера).
Результаты сохраняются в WINNERS.md каждого клиента.
"""

import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from utils.winner_analyzer import (
    load_scraped_posts,
    analyze_winners,
    save_winners_markdown,
)
from utils.client_context import list_clients

logger = logging.getLogger(__name__)

# Глобальный планировщик (инициализируется в main)
scheduler: AsyncIOScheduler = None


async def analyze_week_winners():
    """
    Анализ победительных постов за неделю.
    Запускается каждый понедельник в 10:30 (после парсера в 09:00).
    """
    logger.info("🔄 Запуск еженедельного анализа победителей...")

    try:
        # Загружаем парсированные посты
        posts = load_scraped_posts()
        if not posts:
            logger.warning("❌ Парсированные посты не найдены")
            return

        logger.info(f"✅ Загружено {len(posts)} постов из парсера")

        # Анализируем для каждого клиента
        clients = list_clients()
        if not clients:
            logger.warning("⚠️ Нет клиентов для анализа")
            return

        for client_slug in clients:
            try:
                # Анализируем победителей за неделю
                analysis = analyze_winners(posts, days=7)

                if analysis.get("status") == "success":
                    # Сохраняем отчёт
                    saved = save_winners_markdown(client_slug, analysis)
                    if saved:
                        logger.info(
                            f"✅ Анализ сохранён для {client_slug} "
                            f"({analysis['analyzed_posts']} постов)"
                        )
                    else:
                        logger.error(f"❌ Ошибка сохранения для {client_slug}")
                else:
                    logger.warning(
                        f"⚠️ Недостаточно данных для {client_slug}: "
                        f"{analysis.get('message')}"
                    )

            except Exception as e:
                logger.error(f"❌ Ошибка анализа для {client_slug}: {e}")
                continue

        logger.info("✅ Еженедельный анализ завершён")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в analyze_week_winners: {e}")


def init_scheduler(event_loop=None):
    """
    Инициализировать планировщик.

    Args:
        event_loop: asyncio event loop (опционально)
    """
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler уже инициализирован")
        return scheduler

    try:
        # Используем переданный event loop или текущий
        if event_loop:
            scheduler = AsyncIOScheduler(event_loop=event_loop)
        else:
            scheduler = AsyncIOScheduler()

        # Добавляем задачу: каждый понедельник в 10:30
        scheduler.add_job(
            analyze_week_winners,
            trigger=CronTrigger(day_of_week="mon", hour=10, minute=30),
            id="weekly_winners_analysis",
            name="Weekly Winners Analysis",
            replace_existing=True,
        )

        logger.info("✅ Планировщик инициализирован")
        logger.info("📅 Задача: каждый понедельник в 10:30 анализировать победителей")

        return scheduler

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации планировщика: {e}")
        return None


async def start_scheduler():
    """Запустить планировщик"""
    global scheduler

    if scheduler is None:
        logger.error("Планировщик не инициализирован")
        return False

    try:
        if not scheduler.running:
            scheduler.start()
            logger.info("✅ Планировщик запущен")
        else:
            logger.warning("⚠️ Планировщик уже запущен")

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика: {e}")
        return False


async def stop_scheduler():
    """Остановить планировщик"""
    global scheduler

    if scheduler is None:
        logger.warning("Планировщик не инициализирован")
        return

    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
            logger.info("✅ Планировщик остановлен")
        else:
            logger.warning("⚠️ Планировщик уже остановлен")

    except Exception as e:
        logger.error(f"❌ Ошибка остановки планировщика: {e}")


async def trigger_winners_analysis_now():
    """
    Принудительно запустить анализ немедленно (для тестирования).
    Используется в команде /retro force.
    """
    logger.info("🔄 Принудительный запуск анализа победителей...")
    await analyze_week_winners()
    logger.info("✅ Анализ завершён")


def get_scheduler():
    """Получить экземпляр планировщика (для проверки статуса)"""
    return scheduler


def get_scheduler_status() -> str:
    """Получить статус планировщика для показа в боте"""
    global scheduler

    if scheduler is None:
        return "❌ Планировщик не инициализирован"

    if not scheduler.running:
        return "⚠️ Планировщик остановлен"

    jobs = scheduler.get_jobs()
    if not jobs:
        return "⚠️ Нет активных задач"

    job = jobs[0]  # Наша задача анализа победителей
    next_run = job.next_run_time

    return f"✅ Планировщик активен\n📅 Следующий анализ: {next_run.strftime('%d.%m.%Y %H:%M')}"
