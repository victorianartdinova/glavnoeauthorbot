"""
Обработчик голосовых сообщений и кружков
"""
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from utils.transcription import transcribe_telegram_voice

router = Router()


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot, state: FSMContext):
    """Обработка голосовых сообщений"""
    data = await state.get_data()
    client_slug = data.get("current_client")

    if not client_slug:
        await message.answer("Сначала выбери клиента")
        return

    status_msg = await message.answer("Транскрибирую голосовое...")

    try:
        text = await transcribe_telegram_voice(bot, message.voice)

        if not text:
            await status_msg.edit_text("Не удалось распознать речь")
            return

        # Показываем транскрипцию и кнопки действий
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Подводка", callback_data="voice_intro"),
                InlineKeyboardButton(text="Копировать", callback_data="voice_copy"),
            ]
        ])

        await status_msg.edit_text(
            f"**Транскрипция:**\n\n{text}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        # Сохраняем транскрипцию в state для дальнейших действий
        await state.update_data(last_transcription=text)

    except Exception as e:
        await status_msg.edit_text(f"Ошибка транскрипции: {e}")


@router.message(F.video_note)
async def handle_video_note(message: types.Message, bot: Bot, state: FSMContext):
    """Обработка кружков (video notes)"""
    data = await state.get_data()
    client_slug = data.get("current_client")

    if not client_slug:
        await message.answer("Сначала выбери клиента")
        return

    status_msg = await message.answer("Транскрибирую кружок...")

    try:
        text = await transcribe_telegram_voice(bot, message.video_note)

        if not text:
            await status_msg.edit_text("Не удалось распознать речь")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Подводка", callback_data="voice_intro"),
                InlineKeyboardButton(text="Копировать", callback_data="voice_copy"),
            ]
        ])

        await status_msg.edit_text(
            f"**Транскрипция кружка:**\n\n{text}",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

        await state.update_data(last_transcription=text)

    except Exception as e:
        await status_msg.edit_text(f"Ошибка транскрипции: {e}")


def register_handlers(dp):
    """Регистрация handlers в dispatcher"""
    dp.include_router(router)
