import asyncio
import logging
import os
import sqlite3
from html import escape
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder


BOT_TOKEN = os.getenv("8797408746:AAE-3uzRrIEo9kv2pB1OzzLD6pmO7xe1NQI", "PASTE_BOT_TOKEN_HERE")

ADMIN_IDS = {7543852010, 418350122}
PRIMARY_ADMIN_USERNAME = "@Fast_gamer_uz"

PREVIEW_COST = 5
REF_REWARD = 5

GAME_URL = "https://t.me/FastPrevyuBotShashkaGame.Replit.app"
GROUP_URL = "https://t.me/Fast_prevyu_bot?startgroup=true"
BOT_USERNAME = "Fast_Prevyu_Bot"

PROMO_CODES = {
    "FAST",
    "FAST_GAMER_UZ",
    "FAST_GAMER",
    "PREVYU",
    "FAST_PREVYU_BOT",
    "FAST_PREVYU",
    "FASTZO'R",
    "FASTGAOBUNABOL",
}

DB_PATH = "fastbot.sqlite3"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)



class UserStates(StatesGroup):
    waiting_preview = State()
    waiting_promo = State()



def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            stars INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER,
            referred_rewarded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_used (
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            used_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS preview_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER PRIMARY KEY,
            rating INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            row INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0,
            function TEXT,
            color TEXT
        )
    """)

    for admin_id in ADMIN_IDS:
        username = PRIMARY_ADMIN_USERNAME if admin_id == 7543852010 else ""
        cur.execute(
            "INSERT OR IGNORE INTO admins(user_id, username) VALUES (?, ?)",
            (admin_id, username),
        )

    conn.commit()
    conn.close()


def ensure_user(tg_user):
    conn = db()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (tg_user.id,),
    ).fetchone()

    if not row:
        cur.execute(
            """
            INSERT INTO users(user_id, username, first_name)
            VALUES (?, ?, ?)
            """,
            (
                tg_user.id,
                tg_user.username or "",
                tg_user.first_name or "",
            ),
        )
    else:
        cur.execute(
            """
            UPDATE users
            SET username=?, first_name=?
            WHERE user_id=?
            """,
            (
                tg_user.username or "",
                tg_user.first_name or "",
                tg_user.id,
            ),
        )

    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = db()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def get_all_user_ids():
    conn = db()
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True

    conn = db()
    row = conn.execute(
        "SELECT 1 FROM admins WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()

    return bool(row)


def add_balance(user_id: int, amount: int):
    conn = db()
    conn.execute(
        "UPDATE users SET balance=MAX(0, balance+?) WHERE user_id=?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


def set_balance(user_id: int, amount: int):
    conn = db()
    conn.execute(
        "UPDATE users SET balance=? WHERE user_id=?",
        (max(0, amount), user_id),
    )
    conn.commit()
    conn.close()


def deduct_balance(user_id: int, amount: int) -> bool:
    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET balance=balance-?
        WHERE user_id=? AND balance>=?
        """,
        (amount, user_id, amount),
    )

    ok = cur.rowcount == 1
    conn.commit()
    conn.close()

    return ok


def set_referrer_if_empty(user_id: int, referrer_id: int):
    conn = db()

    row = conn.execute(
        "SELECT referred_by FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()

    if row and row["referred_by"] is None and user_id != referrer_id:
        conn.execute(
            "UPDATE users SET referred_by=? WHERE user_id=?",
            (referrer_id, user_id),
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


def reward_referrer_if_needed(user_id: int):
    conn = db()

    row = conn.execute(
        """
        SELECT referred_by, referred_rewarded
        FROM users
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchone()

    if (
        not row
        or not row["referred_by"]
        or row["referred_rewarded"]
    ):
        conn.close()
        return None

    referrer_id = row["referred_by"]

    conn.execute(
        """
        UPDATE users
        SET balance=balance+?, referred_rewarded=1
        WHERE user_id=?
        """,
        (REF_REWARD, user_id),
    )

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE user_id=?",
        (REF_REWARD, referrer_id),
    )

    conn.commit()
    conn.close()

    return referrer_id



def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.add(
        KeyboardButton(text="⭐ Prevyu yasash ⭐")
    )

    kb.row(
        KeyboardButton(text="🎁 Promo kod 🎁"),
        KeyboardButton(text="💳 Balans to‘ldirish 💳"),
    )

    kb.row(
        KeyboardButton(text="🎮 O‘yinlar"),
        KeyboardButton(text="➕ Guruhga qo‘shish ➕"),
    )

    if is_admin(user_id):
        kb.row(
            KeyboardButton(text="⛓️‍💥 Admin Sozlamalar ⚙️")
        )

    return kb.as_markup(resize_keyboard=True)


def games_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="♟️ Shashka"),
        KeyboardButton(text="🎲 Minecraft"),
        KeyboardButton(text="🔘 Omad doirasi"),
    )

    kb.row(KeyboardButton(text="⬅️ Menyu"))

    return kb.as_markup(resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="/users"),
        KeyboardButton(text="/Admin user"),
    )
    kb.row(
        KeyboardButton(text="/NewAdmins"),
        KeyboardButton(text="/DeleteAdmin"),
    )
    kb.row(
        KeyboardButton(text="/Rating"),
        KeyboardButton(text="/broadcast"),
    )
    kb.row(
        KeyboardButton(text="/Onemessage"),
        KeyboardButton(text="/Userprofile"),
    )
    kb.row(
        KeyboardButton(text="/UserUsername"),
        KeyboardButton(text="/Buttoneditor"),
    )
    kb.row(
        KeyboardButton(text="/ButtonsName"),
        KeyboardButton(text="/NewButton"),
    )
    kb.row(
        KeyboardButton(text="/ButtonColor"),
        KeyboardButton(text="/DaletButton"),
    )
    kb.row(
        KeyboardButton(text="/ButtonFunction"),
        KeyboardButton(text="/ButtonFunctionDalet"),
    )
    kb.row(
        KeyboardButton(text="/BalanceDeleteAll"),
        KeyboardButton(text="/BalanceDalete1"),
    )
    kb.row(
        KeyboardButton(text="/Balancing"),
        KeyboardButton(text="/AllHumansBalans1"),
    )
    kb.row(
        KeyboardButton(text="/NewWindowButton"),
        KeyboardButton(text="/IdendUser"),
    )
    kb.row(KeyboardButton(text="/RandomHuman"))
    kb.row(KeyboardButton(text="⬅️ Menyu"))

    return kb.as_markup(resize_keyboard=True)



def display_username(row) -> str:
    if row["username"]:
        return "@" + row["username"].lstrip("@")
    return row["first_name"] or str(row["user_id"])


def start_text(user_id: int) -> str:
    row = get_user(user_id)
    username = display_username(row)

    return (
        f"👋 💎 <b>Salom {escape(username)} 💎</b>\n\n"
        f"🔥 <b>@Fast_prevyu_bot ga xush kelibsiz</b> 🔥\n\n"
        f"⭐ <b>Iltimos menyudan foydalaning va "
        f"o‘z prevyuyingizni tayyorlang</b> ⭐"
    )


async def resolve_user(arg: str) -> Optional[int]:
    arg = arg.strip()

    if not arg:
        return None

    if arg.startswith("@"):
        username = arg[1:].lower()

        conn = db()
        row = conn.execute(
            "SELECT user_id FROM users WHERE lower(username)=?",
            (username,),
        ).fetchone()
        conn.close()

        return row["user_id"] if row else None

    try:
        return int(arg)
    except ValueError:
        return None



@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    ensure_user(message.from_user)

    if command.args:
        try:
            referrer_id = int(command.args.strip())

            if (
                referrer_id != message.from_user.id
                and get_user(referrer_id)
            ):
                set_referrer_if_empty(
                    message.from_user.id,
                    referrer_id,
                )

        except ValueError:
            pass

    rewarded = reward_referrer_if_needed(message.from_user.id)

    if rewarded:
        try:
            await bot.send_message(
                rewarded,
                "🎉 Sizning taklif havolangiz orqali yangi "
                "foydalanuvchi kirdi!\n"
                "💎 <b>+5 Balans</b> berildi.",
            )
        except Exception:
            pass

    await message.answer(
        start_text(message.from_user.id),
        reply_markup=main_keyboard(message.from_user.id),
    )



@router.message(F.text == "⭐ Prevyu yasash ⭐")
async def preview_start(message: Message, state: FSMContext):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    if row["balance"] < PREVIEW_COST:
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    await state.set_state(UserStates.waiting_preview)

    await message.answer(
        "⭐ <b>Minecraft skiningizni PNG tarzda yuboring.</b>\n\n"
        "💵 Narxi: <b>1000 balans</b>"
    )


@router.message(F.text == "🎁 Promo kod 🎁")
async def promo_start(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_promo)
    await message.answer("🎁 <b>Promo kodni yozing:</b>")


@router.message(F.text == "💳 Balans to‘ldirish 💳")
async def balance_topup(message: Message):
    await message.answer(
        "💳 <b>Balans to‘ldirish</b> 💳\n\n"
        f"Admin: <b>{PRIMARY_ADMIN_USERNAME}</b> ga yozing — "
        "pulga balans beradi yoki star ga beradi.\n\n"
        "⭐ Quyida Telegram Stars orqali to‘g‘ridan-to‘g‘ri "
        "star yuborishingiz mumkin:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ 1 Star yuborish",
                    callback_data="star_1",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐⭐ 2 Star yuborish",
                    callback_data="star_2",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐⭐⭐ 3 Star yuborish",
                    callback_data="star_3",
                )
            ],
        ]
    )

    await message.answer(
        "⭐ <b>Star yuborish</b>:",
        reply_markup=kb,
    )


@router.message(F.text == "🎮 O‘yinlar")
async def games(message: Message):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    playing = 0

    await message.answer(
        f"🎮 <b>O'yinlar</b>\n\n"
        f"{escape(display_username(row))}!✅ "
        f"Balansingiz: <b>{row['balance']}</b>\n\n"
        f"✅ <b>O'yinlar nomi:</b>\n"
        f"1. Minecraft\n"
        f"2. Shashka\n"
        f"3. Omad doirasi\n\n"
        f"🟢 Hozir o'ynalmoqda: "
        f"( O'yin o'ynayotgan odamlar soni: "
        f"<b>{playing}</b> kishi )\n\n"
        f"<b>O'yin tanlang: 👇</b>",
        reply_markup=games_keyboard(),
    )


@router.message(F.text == "➕ Guruhga qo‘shish ➕")
async def add_group(message: Message):
    await message.answer(
        "➕ <b>Botni guruhga qo'shish:</b>\n"
        f"{GROUP_URL}"
    )


@router.message(F.text == "⛓️‍💥 Admin Sozlamalar ⚙️")
async def admin_settings(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz.")
        return

    await message.answer(
        "⛓️‍💥 <b>Admin Sozlamalari</b>\n\n"
        "/users — Foydalanuvchilar soni\n"
        "/Admin user — Adminlar soni\n"
        "/NewAdmins — Yangi adminlar\n"
        "/DeleteAdmin — Adminlarni o'chirish\n"
        "/Rating — Reyting\n"
        "/broadcast — Hammaga xabar yuborish\n"
        "/Onemessage — Bitta odamga xabar\n"
        "/Userprofile — Foydalanuvchi profili\n"
        "/UserUsername — Foydalanuvchi usernamesi\n"
        "/Buttoneditor — Tugmalar joyi\n"
        "/ButtonsName — Tugmalar nomi\n"
        "/NewButton — Yangi tugma\n"
        "/ButtonColor — Tugmalar rangi\n"
        "/DaletButton — Tugmalar o'chirish\n"
        "/ButtonFunction — Tugmalar funksiyalari\n"
        "/ButtonFunction — Tugmalar funksiyalarimi o'chirish
        "/BalanceDeleteAll — Hammani balansini o'chirish\n"
        "/BalanceDalete1 — Bitta odam balansini o'chirish\n"
        "/Balancing — 1 ta odamga balans berish\n"
        "/AllHumansBalans1 — Hammaga balans berish\n"
        "/NewWindowButton — Yangi oyna\n"
        "/IdendUser — ID orqali foydalanuvchini topish\n"
        "/RandomHuman — Random odam tanlash",
        reply_markup=admin_keyboard(),
    )


@router.message(F.text == "⬅️ Menyu")
async def back_menu(message: Message):
    await message.answer(
        "🏠 <b>Asosiy menyu</b>",
        reply_markup=main_keyboard(message.from_user.id),
    )



@router.message(UserStates.waiting_promo, F.text)
async def promo_text_router(
    message: Message,
    state: FSMContext,
):
    ensure_user(message.from_user)

    text = message.text.strip()

    if text.startswith("/"):
        await state.clear()
        return

    code = text.upper().strip()
    code = (
        code.replace("’", "'")
        .replace("‘", "'")
        .replace("ʻ", "'")
    )

    if code in PROMO_CODES:
        conn = db()

        already = conn.execute(
            """
            SELECT 1 FROM promo_used
            WHERE user_id=? AND code=?
            """,
            (message.from_user.id, code),
        ).fetchone()

        if already:
            conn.close()
            await state.clear()

            await message.answer(
                "❌ Bu promokoddan siz avval foydalanib bo'lgansiz."
            )
            return

        conn.execute(
            "INSERT INTO promo_used(user_id, code) VALUES (?, ?)",
            (message.from_user.id, code),
        )

        conn.execute(
            "UPDATE users SET balance=balance+5 WHERE user_id=?",
            (message.from_user.id,),
        )

        conn.commit()
        conn.close()

        await state.clear()

        await message.answer(
            "🎉 Promokod qabul qilindi!\n"
            "💎 <b>+5 Balans</b> berildi."
        )
        return

    row = get_user(message.from_user.id)
    username = escape(display_username(row))

    await state.clear()

    await message.answer(
        f"Kechiring {username} brodar siz yozgan "
        f"<b>{escape(text)}</b> bu promokod afsuski 😔 yo'q ❌\n"
        "Boshidan harakat qling."
    )


@router.message(UserStates.waiting_preview, F.text)
async def preview_text_router(
    message: Message,
    state: FSMContext,
):
    await state.clear()
    await message.answer("Bu PNG emas ❌")


@router.message(F.text)
async def text_router(message: Message):
    ensure_user(message.from_user)

    text = message.text.strip()

    if text.startswith("/"):
        return

    if text == "♟️ Shashka":
        await message.answer(
            "♟️ <b>Shashka o'ynash uchun:</b>\n"
            f"{GAME_URL}"
        )
        return

    if text == "🎲 Minecraft":
        await message.answer(
            "🎲 <b>Minecraft</b> o'yini tez orada qo'shiladi."
        )
        return

    if text == "🔘 Omad doirasi":
        await message.answer(
            "🔘 <b>Omad doirasi</b> tez orada qo'shiladi."
        )
        return

    await message.answer(
        "❓ Tushunmadim. Iltimos, menyudagi tugmalardan foydalaning."
    )



@router.message(F.photo)
async def receive_photo(
    message: Message,
    state: FSMContext,
):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    if row["balance"] < PREVIEW_COST:
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    await state.clear()

    await message.answer(
        "⏳ <b>Prevyu tayyorlanmoqda...</b>"
    )

    if not deduct_balance(
        message.from_user.id,
        PREVIEW_COST,
    ):
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    photo = message.photo[-1]

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO preview_orders(user_id, file_id)
        VALUES (?, ?)
        """,
        (message.from_user.id, photo.file_id),
    )

    order_id = cur.lastrowid

    conn.commit()
    conn.close()

    user = get_user(message.from_user.id)
    username = display_username(user)

    caption = (
        "🎮 <b>Yangi Skin</b>\n\n"
        f"<b>Foydalanuvchi Nomi:</b> "
        f"{escape(user['first_name'] or 'Nomaʼlum')}\n"
        f"👤 <b>User:</b> {escape(username)}\n"
        f"🆔 <b>Foydalanuvchi ID:</b> "
        f"<code>{user['user_id']}</code>\n"
        f"💵 <b>Balans:</b> {user['balance']}\n"
        f"🔢 <b>Buyurtma:</b> #{order_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo.file_id,
                caption=caption,
            )
        except Exception as e:
            logger.warning(
                "Could not send preview to admin %s: %s",
                admin_id,
                e,
            )


@router.message(F.document)
async def receive_document(
    message: Message,
    state: FSMContext,
):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    if row["balance"] < PREVIEW_COST:
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    document = message.document

    if not document.file_name:
        await state.clear()
        await message.answer("Bu PNG emas ❌")
        return

    if not document.file_name.lower().endswith(".png"):
        await state.clear()
        await message.answer("Bu PNG emas ❌")
        return

    await state.clear()

    await message.answer(
        "⏳ <b>Prevyu tayyorlanmoqda...</b>"
    )

    if not deduct_balance(
        message.from_user.id,
        PREVIEW_COST,
    ):
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO preview_orders(user_id, file_id)
        VALUES (?, ?)
        """,
        (message.from_user.id, document.file_id),
    )

    order_id = cur.lastrowid

    conn.commit()
    conn.close()

    user = get_user(message.from_user.id)
    username = display_username(user)

    caption = (
        "🎮 <b>Yangi Skin</b>\n\n"
        f"<b>Foydalanuvchi Nomi:</b> "
        f"{escape(user['first_name'] or 'Nomaʼlum')}\n"
        f"👤 <b>User:</b> {escape(username)}\n"
        f"🆔 <b>Foydalanuvchi ID:</b> "
        f"<code>{user['user_id']}</code>\n"
        f"💵 <b>Balans:</b> {user['balance']}\n"
        f"🔢 <b>Buyurtma:</b> #{order_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                admin_id,
                document.file_id,
                caption=caption,
            )
        except Exception as e:
            logger.warning(
                "Could not send preview document to admin %s: %s",
                admin_id,
                e,
            )


@router.callback_query(F.data.startswith("star_"))
async def star_payment(
    callback: CallbackQuery,
):
    try:
        stars = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer(
            "Xatolik ❌",
            show_alert=True,
        )
        return

    prices = [
        LabeledPrice(
            label=f"{stars} Telegram Star",
            amount=stars,
        )
    ]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"{stars} Star",
        description=f"{stars} ta Telegram Star yuborish",
        payload=f"star_{stars}",
        currency="XTR",
        prices=prices,
    )

    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout(
    query,
):
    await bot.answer_pre_checkout_query(
        query.id,
        ok=True,
    )


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
):
    payment = message.successful_payment

    if not payment:
        return

    try:
        stars = int(
            payment.invoice_payload.split("_")[1]
        )
    except (ValueError, IndexError):
        stars = payment.total_amount

    conn = db()

    conn.execute(
        """
        UPDATE users
        SET stars=stars+?, balance=balance+?
        WHERE user_id=?
        """,
        (
            stars,
            stars,
            message.from_user.id,
        ),
    )

    conn.commit()
    conn.close()

    await message.answer(
        f"✅ To'lov muvaffaqiyatli!\n\n"
        f"⭐ <b>+{stars} Star</b>\n"
        f"💎 <b>+{stars} Balans</b> qo'shildi."
    )


@router.message(Command("yordam"))
async def help_command(message: Message):
    await message.answer(
        "🆘 <b>Yordam</b>\n\n"
        "⭐ <b>Prevyu yasash</b> — Minecraft skiningizni "
        "PNG qilib yuboring.\n"
        "🎁 <b>Promo kod</b> — promo kod orqali balans oling.\n"
        "💳 <b>Balans</b> — balansni to'ldiring.\n"
        "🎮 <b>O'yinlar</b> — mavjud o'yinlarni tanlang.\n"
        "➕ <b>Guruhga qo'shish</b> — botni guruhga qo'shing.\n\n"
        f"👨‍💻 Admin: <b>{PRIMARY_ADMIN_USERNAME}</b>"
    )


@router.message(Command("profil"))
async def profile_command(message: Message):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    username = escape(display_username(row))

    await message.answer(
        "👤 <b>Sizning profilingiz</b>\n\n"
        f"👤 Username: <b>{username}</b>\n"
        f"🆔 ID: <code>{row['user_id']}</code>\n"
        f"💎 Balans: <b>{row['balance']}</b>\n"
        f"⭐ Stars: <b>{row['stars']}</b>"
    )


@router.message(Command("ref"))
async def referral_command(message: Message):
    ensure_user(message.from_user)

    link = (
        f"https://t.me/{BOT_USERNAME}"
        f"?start={message.from_user.id}"
    )

    await message.answer(
        "👥 <b>Referal tizimi</b>\n\n"
        "Do'stingizni quyidagi havola orqali taklif qiling:\n\n"
        f"<code>{link}</code>\n\n"
        "🎁 Har bir yangi foydalanuvchi uchun "
        "<b>+5 balans</b> beriladi."
    )


@router.message(Command("users"))
async def users_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    conn = db()
    count = conn.execute(
        "SELECT COUNT(*) AS count FROM users"
    ).fetchone()["count"]
    conn.close()

    await message.answer(
        f"👥 <b>Foydalanuvchilar:</b> {count} ta"
    )


@router.message(Command("Admin"))
async def admin_command(message: Message):
    if not is_admin(message.from_user.id):
        return

    conn = db()
    rows = conn.execute(
        "SELECT user_id, username FROM admins"
    ).fetchall()
    conn.close()

    text = "👑 <b>Adminlar</b>\n\n"

    for i, row in enumerate(rows, 1):
        username = (
            "@" + row["username"]
            if row["username"]
            else "Username yo'q"
        )

        text += (
            f"{i}. {username}\n"
            f"🆔 <code>{row['user_id']}</code>\n\n"
        )

    await message.answer(text)


@router.message(Command("NewAdmins"))
async def new_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=2)

    if len(args) < 2:
        await message.answer(
            "➕ <b>Yangi admin qo'shish</b>\n\n"
            "Misol:\n"
            "<code>/NewAdmins 123456789</code>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID noto'g'ri.")
        return

    username = ""

    if len(args) >= 3:
        username = args[2].lstrip("@")

    conn = db()

    conn.execute(
        """
        INSERT OR REPLACE INTO admins(user_id, username)
        VALUES (?, ?)
        """,
        (user_id, username),
    )

    conn.commit()
    conn.close()

    await message.answer(
        f"✅ <b>{user_id}</b> admin qilindi."
    )


@router.message(Command("DeleteAdmin"))
async def delete_admin(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "❌ Misol:\n"
            "<code>/DeleteAdmin 123456789</code>"
        )
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID noto'g'ri.")
        return

    if user_id in ADMIN_IDS:
        await message.answer(
            "❌ Asosiy adminni o'chirib bo'lmaydi."
        )
        return

    conn = db()

    cur = conn.execute(
        "DELETE FROM admins WHERE user_id=?",
        (user_id,),
    )

    conn.commit()
    conn.close()

    if cur.rowcount:
        await message.answer(
            f"✅ <b>{user_id}</b> adminlikdan olib tashlandi."
        )
    else:
        await message.answer(
            "❌ Bunday admin topilmadi."
        )


async def main():
    init_db()

    logger.info("Fast Prevyu Bot ishga tushmoqda...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())