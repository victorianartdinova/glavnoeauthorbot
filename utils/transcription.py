"""
Транскрипция аудио через локальный Whisper
"""
import whisper
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

# Загружаем модель один раз при старте (base ~150MB, ~1GB RAM)
_model = None

def get_model():
    """Ленивая загрузка модели Whisper"""
    global _model
    if _model is None:
        logger.info("Загружаю модель Whisper base...")
        _model = whisper.load_model("base")
        logger.info("Модель Whisper загружена")
    return _model


async def transcribe_audio(file_path: str) -> str:
    """
    Транскрибирует аудиофайл в текст.

    Args:
        file_path: Путь к аудиофайлу (.ogg, .mp3, .wav и др.)

    Returns:
        Текст транскрипции
    """
    try:
        model = get_model()
        result = model.transcribe(file_path, language="ru")
        return result["text"].strip()
    except Exception as e:
        logger.error(f"Ошибка транскрипции: {e}")
        raise


async def transcribe_telegram_voice(bot, voice) -> str:
    """
    Скачивает и транскрибирует голосовое сообщение из Telegram.

    Args:
        bot: Экземпляр aiogram Bot
        voice: Объект Voice или VideoNote из Telegram

    Returns:
        Текст транскрипции
    """
    # Создаём временный файл
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Скачиваем файл
        file = await bot.get_file(voice.file_id)
        await bot.download_file(file.file_path, tmp_path)

        # Транскрибируем
        text = await transcribe_audio(tmp_path)
        return text
    finally:
        # Удаляем временный файл
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
