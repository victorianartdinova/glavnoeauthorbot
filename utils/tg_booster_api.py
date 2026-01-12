"""
Утилита для работы с метриками TG Booster и Telegram Ads

Каждый клиент имеет свой API-токен TG Booster.
Токен хранится в docs/CLIENTS/{client}/tg_booster.json

Этот модуль управляет хранением и получением метрик.
"""
import os
import json
import aiohttp
from datetime import datetime
from typing import Optional

import config


def get_tg_booster_config(client_slug: str) -> dict:
    """
    Получить конфигурацию TG Booster для клиента

    Returns:
        {
            "api_token": str,
            "campaign_ids": list
        }
    """
    config_file = os.path.join(config.CLIENTS_DIR, client_slug, "tg_booster.json")

    if not os.path.exists(config_file):
        return {"api_token": None, "campaign_ids": []}

    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tg_booster_config(client_slug: str, api_token: str, campaign_ids: list = None) -> bool:
    """Сохранить конфигурацию TG Booster для клиента"""
    client_dir = os.path.join(config.CLIENTS_DIR, client_slug)

    if not os.path.exists(client_dir):
        return False

    config_file = os.path.join(client_dir, "tg_booster.json")

    data = {
        "api_token": api_token,
        "campaign_ids": campaign_ids or []
    }

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return True


async def fetch_tg_booster_stats(client_slug: str) -> Optional[dict]:
    """
    Получить статистику из TG Booster API

    Returns:
        dict с метриками или None если ошибка
    """
    tg_config = get_tg_booster_config(client_slug)

    if not tg_config.get("api_token"):
        return None

    # TODO: Реализовать когда будет известен формат API
    # Пока возвращаем None — метрики вводятся вручную
    # или через /update_metrics

    # Пример структуры ответа API:
    # async with aiohttp.ClientSession() as session:
    #     headers = {"Authorization": f"Bearer {tg_config['api_token']}"}
    #     async with session.get("https://api.tgbooster.ru/stats", headers=headers) as resp:
    #         if resp.status == 200:
    #             return await resp.json()
    # return None

    return None


def get_metrics_file(client_slug: str) -> str:
    """Путь к файлу метрик клиента"""
    return os.path.join(config.CLIENTS_DIR, client_slug, "metrics.json")


def load_metrics(client_slug: str) -> dict:
    """
    Загрузить метрики клиента

    Returns:
        {
            "cpl": float,           # Стоимость лида (ручной ввод)
            "cpl_updated": str,     # Дата обновления CPL
            "ctr": float,           # CTR из TG Booster
            "cps": float,           # Стоимость подписки
            "impressions": int,     # Показы
            "clicks": int,          # Клики
            "subscribers": int,     # Подписки
            "spend": float,         # Расход
            "tg_booster_updated": str,  # Дата обновления из TG Booster
            "history": []           # История обновлений
        }
    """
    metrics_file = get_metrics_file(client_slug)

    if not os.path.exists(metrics_file):
        return {
            "cpl": None,
            "cpl_updated": None,
            "ctr": None,
            "cps": None,
            "impressions": None,
            "clicks": None,
            "subscribers": None,
            "spend": None,
            "tg_booster_updated": None,
            "history": []
        }

    with open(metrics_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_metrics(client_slug: str, metrics: dict) -> bool:
    """Сохранить метрики клиента"""
    client_dir = os.path.join(config.CLIENTS_DIR, client_slug)

    if not os.path.exists(client_dir):
        return False

    metrics_file = get_metrics_file(client_slug)

    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    return True


def update_cpl(client_slug: str, cpl: float) -> dict:
    """
    Обновить CPL клиента (ручной ввод после созвона)

    Args:
        client_slug: идентификатор клиента
        cpl: стоимость лида в рублях

    Returns:
        Обновлённые метрики
    """
    metrics = load_metrics(client_slug)

    # Сохраняем в историю
    if metrics["cpl"] is not None:
        metrics["history"].append({
            "type": "cpl",
            "old_value": metrics["cpl"],
            "new_value": cpl,
            "date": datetime.now().isoformat()
        })

    metrics["cpl"] = cpl
    metrics["cpl_updated"] = datetime.now().strftime("%d.%m.%Y")

    save_metrics(client_slug, metrics)
    return metrics


def update_tg_booster_metrics(
    client_slug: str,
    ctr: float = None,
    cps: float = None,
    impressions: int = None,
    clicks: int = None,
    subscribers: int = None,
    spend: float = None
) -> dict:
    """
    Обновить метрики из TG Booster

    Args:
        client_slug: идентификатор клиента
        ctr: CTR в процентах
        cps: стоимость подписки
        impressions: количество показов
        clicks: количество кликов
        subscribers: количество подписок
        spend: общий расход

    Returns:
        Обновлённые метрики
    """
    metrics = load_metrics(client_slug)

    old_values = {
        "ctr": metrics.get("ctr"),
        "cps": metrics.get("cps"),
        "impressions": metrics.get("impressions"),
        "clicks": metrics.get("clicks"),
        "subscribers": metrics.get("subscribers"),
        "spend": metrics.get("spend")
    }

    # Обновляем только переданные значения
    if ctr is not None:
        metrics["ctr"] = ctr
    if cps is not None:
        metrics["cps"] = cps
    if impressions is not None:
        metrics["impressions"] = impressions
    if clicks is not None:
        metrics["clicks"] = clicks
    if subscribers is not None:
        metrics["subscribers"] = subscribers
    if spend is not None:
        metrics["spend"] = spend

    metrics["tg_booster_updated"] = datetime.now().strftime("%d.%m.%Y")

    # Сохраняем в историю
    metrics["history"].append({
        "type": "tg_booster",
        "old_values": old_values,
        "date": datetime.now().isoformat()
    })

    save_metrics(client_slug, metrics)
    return metrics


def format_metrics_report(client_slug: str) -> str:
    """
    Сформировать отчёт по метрикам клиента

    Returns:
        Текстовый отчёт для отправки в Telegram
    """
    metrics = load_metrics(client_slug)

    report = f"📊 {client_slug} — Метрики\n\n"

    # TG Booster метрики
    if metrics.get("ctr") is not None or metrics.get("cps") is not None:
        report += "TG Booster:\n"
        if metrics.get("ctr") is not None:
            report += f"• CTR: {metrics['ctr']:.2f}%\n"
        if metrics.get("cps") is not None:
            report += f"• CPS: {metrics['cps']:,.0f} ₽\n"
        if metrics.get("impressions") is not None:
            report += f"• Показы: {metrics['impressions']:,}\n"
        if metrics.get("clicks") is not None:
            report += f"• Клики: {metrics['clicks']:,}\n"
        if metrics.get("subscribers") is not None:
            report += f"• Подписки: {metrics['subscribers']:,}\n"
        if metrics.get("spend") is not None:
            report += f"• Расход: {metrics['spend']:,.0f} ₽\n"
        if metrics.get("tg_booster_updated"):
            report += f"📅 Обновлено: {metrics['tg_booster_updated']}\n"
        report += "\n"

    # Ручные метрики
    report += "Ручные данные:\n"
    if metrics.get("cpl") is not None:
        report += f"• CPL: {metrics['cpl']:,.0f} ₽\n"
        if metrics.get("cpl_updated"):
            report += f"📅 Обновлено: {metrics['cpl_updated']}\n"
    else:
        report += "• CPL: не указан (обнови через /update_cpl)\n"

    return report


def get_best_creatives(client_slug: str, limit: int = 5) -> list:
    """
    Получить топ креативов по CTR

    Примечание: для полной реализации нужен парсинг
    детальной статистики из TG Booster CSV-экспорта

    Returns:
        Список топ креативов
    """
    # TODO: реализовать парсинг CSV-экспорта из TG Booster
    # Пока возвращаем пустой список
    return []


def calculate_roi(client_slug: str) -> Optional[float]:
    """
    Рассчитать ROI рекламы

    Требует:
    - CPL (стоимость лида)
    - Средний чек клиента
    - Конверсия из лида в сделку

    Returns:
        ROI в процентах или None если данных недостаточно
    """
    # TODO: добавить расчёт ROI когда будут данные о сделках
    return None
