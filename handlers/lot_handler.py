"""
Обработчик добавления лотов
"""
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import json
import os
from datetime import datetime

import config


class LotStates(StatesGroup):
    waiting_for_lot_data = State()


async def cmd_lot(message: types.Message):
    """Команда /lot - начало добавления лота"""
    await LotStates.waiting_for_lot_data.set()
    await message.answer(
        "📦 **Добавление лота**\n\n"
        "Отправь данные в формате:\n"
        "```\n"
        "CLIENT: client_slug\n"
        "LOT_NAME: ЖК Пример / 2К / набережная\n"
        "LOT_LINK: https://...\n"
        "COMMENT_FROM_CLIENT: комментарий\n"
        "PRESENTATION: url или NONE\n"
        "CONDITIONS:\n"
        "  - DOWNPAYMENT: 5000000\n"
        "  - MONTHLY_PAYMENT: 150000\n"
        "  - DISCOUNT: UNKNOWN\n"
        "  - SALES_START: YES\n"
        "REQUEST: AUTO\n"
        "```",
        parse_mode="Markdown"
    )


async def process_lot_data(message: types.Message, state: FSMContext):
    """Обработка данных лота"""
    text = message.text.strip()

    # Парсинг (упрощенный)
    try:
        lot_data = parse_lot_input(text)

        # Валидация
        if not lot_data.get("client_slug"):
            await message.answer("❌ Не указан CLIENT")
            return

        # Сохранение лота
        lot_id = save_lot(lot_data)

        # Проверка на рекламу
        eligible = check_ad_eligibility(lot_data)

        response = f"✅ **Лот добавлен!**\n\n"
        response += f"🆔 ID: `{lot_id}`\n"
        response += f"📦 Название: {lot_data.get('lot_name')}\n"
        response += f"🎯 Реклама: {'✅ Подходит' if eligible else '❌ Не подходит'}\n\n"

        if lot_data.get("presentation") == "NONE":
            response += "⚠️ Нет презентации — нужен сбор фактуры"

        await message.answer(response, parse_mode="Markdown")
        await state.finish()

    except Exception as e:
        await message.answer(f"❌ Ошибка парсинга: {str(e)}")


def parse_lot_input(text: str) -> dict:
    """Парсинг входных данных лота"""
    lines = text.split("\n")
    data = {}

    for line in lines:
        line = line.strip()
        if line.startswith("CLIENT:"):
            data["client_slug"] = line.split(":", 1)[1].strip()
        elif line.startswith("LOT_NAME:"):
            data["lot_name"] = line.split(":", 1)[1].strip()
        elif line.startswith("LOT_LINK:"):
            data["lot_link"] = line.split(":", 1)[1].strip()
        elif line.startswith("COMMENT_FROM_CLIENT:"):
            data["comment"] = line.split(":", 1)[1].strip()
        elif line.startswith("PRESENTATION:"):
            data["presentation"] = line.split(":", 1)[1].strip()
        elif line.startswith("DOWNPAYMENT:"):
            val = line.split(":", 1)[1].strip()
            data["downpayment"] = int(val) if val.isdigit() else None
        elif line.startswith("MONTHLY_PAYMENT:"):
            val = line.split(":", 1)[1].strip()
            data["monthly_payment"] = int(val) if val.isdigit() else None
        elif line.startswith("DISCOUNT:"):
            val = line.split(":", 1)[1].strip()
            data["discount"] = int(val) if val.isdigit() else None
        elif line.startswith("SALES_START:"):
            val = line.split(":", 1)[1].strip()
            data["sales_start"] = val.upper() == "YES"
        elif line.startswith("REQUEST:"):
            data["request"] = line.split(":", 1)[1].strip()

    return data


def save_lot(lot_data: dict) -> str:
    """Сохранение лота в JSON"""
    client_slug = lot_data["client_slug"]
    client_dir = os.path.join(config.CLIENTS_DIR, client_slug)
    os.makedirs(client_dir, exist_ok=True)

    # Генерация lot_id
    date_str = datetime.now().strftime("%Y%m%d")
    lots_file = os.path.join(client_dir, "lots.json")

    # Загрузка существующих лотов
    if os.path.exists(lots_file):
        with open(lots_file, "r", encoding="utf-8") as f:
            lots = json.load(f)
    else:
        lots = []

    # Определение seq
    today_lots = [l for l in lots if l["lot_id"].startswith(f"{client_slug}-{date_str}")]
    seq = len(today_lots) + 1

    lot_id = f"{client_slug}-{date_str}-{seq:02d}"
    lot_data["lot_id"] = lot_id
    lot_data["status"] = "READY_FOR_CONTENT" if lot_data.get("presentation") != "NONE" else "NEED_FACTS"
    lot_data["created_at"] = datetime.now().isoformat()

    lots.append(lot_data)

    with open(lots_file, "w", encoding="utf-8") as f:
        json.dump(lots, f, ensure_ascii=False, indent=2)

    return lot_id


def check_ad_eligibility(lot_data: dict) -> bool:
    """Проверка условий для Telegram Ads"""
    rules = config.AD_ELIGIBILITY_RULES

    if lot_data.get("downpayment") and lot_data["downpayment"] < rules["downpayment_max"]:
        return True
    if lot_data.get("monthly_payment") and lot_data["monthly_payment"] < rules["monthly_payment_max"]:
        return True
    if lot_data.get("discount") and lot_data["discount"] > rules["discount_min"]:
        return True
    if lot_data.get("sales_start"):
        return True

    return False


def register_handlers(dp: Dispatcher):
    """Регистрация обработчиков"""
    dp.register_message_handler(cmd_lot, commands=['lot'], state='*')
    dp.register_message_handler(process_lot_data, state=LotStates.waiting_for_lot_data)
