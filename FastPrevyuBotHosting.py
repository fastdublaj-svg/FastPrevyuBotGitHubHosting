import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

TOKEN = "8797408746:AAE-3uzRrIEo9kv2pB1OzzLD6pmO7xe1NQI"

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    ism = message.from_user.first_name

    await message.answer(
        f"👋 Salom {ism}!\n"
        f"🤖 Botga xush kelibsiz!"
    )


async def main():
    print("Bot ishga tushdi ✅")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())