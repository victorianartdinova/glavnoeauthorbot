"""Скрипт для получения ID веток в группе"""
import asyncio
import socket

# IPv4 only
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4_only

from aiogram import Bot, Dispatcher, types
import config

bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

@dp.message()
async def any_message(message: types.Message):
    """Показать thread_id любого сообщения"""
    thread_id = message.message_thread_id
    chat_id = message.chat.id
    print(f"\n📩 Сообщение от: {message.from_user.first_name}")
    print(f"   Chat ID: {chat_id}")
    print(f"   Thread ID: {thread_id}")
    print(f"   Текст: {message.text[:50] if message.text else '(нет текста)'}")

async def main():
    print("🔍 Слушаю сообщения... Напиши что-нибудь в ветке.")
    print("   Нажми Ctrl+C чтобы остановить.\n")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
