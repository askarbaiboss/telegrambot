import os
import sys
import json
import sqlite3
from dotenv import load_dotenv
from datetime import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================= LOAD ENV =================
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ BOT_TOKEN not set.")
    sys.exit(1)

ADMIN_ID = 165665465
DB_NAME = "orders.db"
user_data_store = {}

# ================= LOAD PRODUCTS =================
PRODUCTS_FILE = "products.json"

def load_products():
    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {PRODUCTS_FILE}: {e}")
        sys.exit(1)

def save_products():
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=4)

products = load_products()

# ================= DATABASE =================
def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_name TEXT,
                product_link TEXT,
                quantity INTEGER,
                customer_name TEXT,
                order_number TEXT,
                payment_method TEXT,
                payment_info TEXT,
                review_sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def save_order(user_id, data):
    product = next((p for p in products if p["name"] == data["product_name"]), None)
    if not product:
        raise ValueError("Продукт не найден при сохранении заказа.")

    # Check stock again just before saving
    if data["quantity"] > product.get("stock", 0):
        raise ValueError(f"Недостаточно товара на складе. Доступно: {product['stock']} шт.")

    # Subtract ordered quantity from stock
    product["stock"] -= data["quantity"]

    # Save back to JSON file
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=4)

    # Save order in DB
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders 
            (user_id, product_name, product_link, quantity, customer_name, order_number)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            data["product_name"],
            data["product_link"],
            data["quantity"],
            data["customer_name"],
            data["order_number"]
        ))
        conn.commit()
        return cursor.lastrowid

def update_payment(order_id, method, info):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET payment_method=?, payment_info=? 
            WHERE id=?
        """, (method, info, order_id))
        conn.commit()

def mark_review_sent(order_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET review_sent=1 WHERE id=?", (order_id,))
        conn.commit()

def get_user_orders(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, product_name, quantity, created_at
            FROM orders
            WHERE user_id=?
            ORDER BY created_at DESC
        """, (user_id,))
        return cursor.fetchall()

def get_orders_pending_review():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, product_name FROM orders WHERE review_sent=0")
        return cursor.fetchall()

def get_all_orders():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, product_name, product_link, quantity, customer_name, order_number, payment_method, payment_info, review_sent, created_at
            FROM orders
            ORDER BY created_at DESC
        """)
        return cursor.fetchall()

import csv

def save_all_orders_to_csv():
    orders = get_all_orders()
    if not orders:
        return None
    
    filename = "all_orders.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Header row with Product Name and Link at the end
        writer.writerow([
            "ID", "User ID", "Quantity", "Customer Name", "Order Number",
            "Payment Method", "Payment Info", "Review Sent", "Created At",
            "Product Name", "Product Link"
        ])
        
        # Write each order with reordered columns
        for order in orders:
            writer.writerow([
                order[0],  # ID
                order[1],  # User ID
                order[4],  # Quantity
                order[5] or "—",  # Customer Name
                order[6] or "—",  # Order Number
                order[7] or "—",  # Payment Method
                order[8] or "—",  # Payment Info
                "✅" if order[9] else "❌",  # Review Sent
                order[10],  # Created At
                order[2],  # Product Name
                order[3],  # Product Link
            ])
    return filename

def get_stats():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM orders")
        total_orders = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(quantity) FROM orders")
        total_quantity = cursor.fetchone()[0] or 0

        return total_orders, total_quantity

init_db()

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {}

    # Only show products with stock > 0
    available_products = [p for p in products if p.get("stock", 0) > 0]
    if not available_products:
        await update.message.reply_text("Все товары распроданы 😢")
        return

    keyboard = [[InlineKeyboardButton(p["name"], callback_data=f"product_{p['name']}")] for p in available_products]
    await update.message.reply_text("Здравствуйте! Выберите ваш заказ:", reply_markup=InlineKeyboardMarkup(keyboard))

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    orders = get_user_orders(user_id)
    if not orders:
        await update.message.reply_text("У вас пока нет заказов.")
        return

    message = "📦 Ваши заказы:\n\n"
    for order in orders:
        message += f"ID: {order[0]}\nТовар: {order[1]}\nКоличество: {order[2]}\nДата: {order[3]}\n\n"
    await update.message.reply_text(message)

async def all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет доступа.")
        return

    filename = save_all_orders_to_csv()
    if not filename:
        await update.message.reply_text("Нет заказов для экспорта.")
        return

    # Send the CSV file to the admin
    with open(filename, "rb") as f:
        await update.message.reply_document(f, filename=filename)

    await update.message.reply_text("📊 Все заказы экспортированы в CSV и отправлены ✅")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет доступа.")
        return

    total_orders, total_quantity = get_stats()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT payment_method, COUNT(*) FROM orders
            WHERE payment_method IS NOT NULL
            GROUP BY payment_method
        """)
        payment_counts = cursor.fetchall()
    payment_summary = "\n".join([f"{row[0]}: {row[1]}" for row in payment_counts]) or "Нет данных об оплате."

    await update.message.reply_text(
        f"📈 Статистика:\nВсего заказов: {total_orders}\nВсего продано товаров: {total_quantity}\nОплаты:\n{payment_summary}"
    )

# ================= CALLBACK HANDLER =================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_data_store.setdefault(user_id, {})

    try:
        if query.data.startswith("product_"):
            await handle_product_selection(update, data)
        elif query.data in ["zelle", "venmo"]:
            await handle_payment_selection(update, data)
        elif query.data == "cancel":
            await handle_cancel(update, user_id)
        else:
            await query.edit_message_text("Неизвестная команда.")
    except Exception as e:
        print(f"Ошибка в button_handler: {e}")
        await query.edit_message_text("Произошла ошибка при обработке кнопки.")

# ================= PRODUCT SELECTION =================
async def handle_product_selection(update: Update, data: dict):
    product_name = update.callback_query.data.replace("product_", "")
    product = next((p for p in products if p["name"] == product_name), None)

    if not product or product.get("stock", 0) <= 0:
        await update.callback_query.edit_message_text("Продукт недоступен или распродан.")
        return

    data["product_name"] = product["name"]
    data["product_link"] = product["link"]

    await update.callback_query.message.reply_text(f"🔗 Ссылка на товар:\n{product['link']}")
    await update.callback_query.message.reply_text(f"Вы выбрали: {product_name}\nВведите количество:")

async def handle_payment_selection(update: Update, data: dict):
    data["payment_method"] = update.callback_query.data.capitalize()
    data["awaiting_payment_info"] = True
    await update.callback_query.edit_message_text(
        f"Вы выбрали {data['payment_method']}.\nВведите данные для оплаты:"
    )

async def handle_cancel(update: Update, user_id: int):
    user_data_store[user_id] = {}
    await update.callback_query.edit_message_text("❌ Заказ отменён.")

# ================= MESSAGE HANDLER =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store.setdefault(user_id, {})

    if update.message.photo:
        await handle_photo(update, user_id)
        return

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Пожалуйста, введите текстовое сообщение.")
        return

    if "product_name" not in data:
        await update.message.reply_text("Используйте /start, чтобы выбрать товар.")
        return
    if "quantity" not in data:
        await handle_quantity(update, data, text)
        return
    if "customer_name" not in data:
        await handle_customer_name(update, data, text)
        return
    if "order_number" not in data:
        await handle_order_number(update, context, data, text)
        return
    if data.get("awaiting_payment_info"):
        await handle_payment(update, context, data, text)
        return

# ================= HANDLE QUANTITY =================
async def handle_quantity(update: Update, data: dict, text: str):
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("Введите положительное число.")
        return
    
    requested_qty = int(text)
    product = next((p for p in products if p["name"] == data["product_name"]), None)
    
    if not product:
        await update.message.reply_text("Ошибка: продукт не найден.")
        return
    
    if requested_qty > product.get("stock", 0):
        await update.message.reply_text(f"Извините, на складе доступно только {product['stock']} шт.")
        return

    # Deduct stock
    product["stock"] -= requested_qty
    save_products()

    data["quantity"] = requested_qty
    await update.message.reply_text("Введите ваше полное имя:")

# ================= HANDLE CUSTOMER INFO =================
async def handle_customer_name(update: Update, data: dict, text: str):
    data["customer_name"] = text
    await update.message.reply_text("Введите номер заказа Amazon:")

async def handle_order_number(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict, text: str):
    data["order_number"] = text
    order_id = save_order(update.effective_user.id, data)
    data["order_id"] = order_id

    await context.bot.send_message(
        ADMIN_ID,
        f"📦 Новый заказ\nID: {order_id}\nПродукт: {data['product_name']}\nКол-во: {data['quantity']}"
    )

    keyboard = [
        [InlineKeyboardButton("Zelle", callback_data="zelle"), InlineKeyboardButton("Venmo", callback_data="venmo")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
    ]
    await update.message.reply_text(
        "Как хотите получить оплату?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= HANDLE PAYMENT =================
async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict, text: str):
    order_id = data.get("order_id")
    method = data.get("payment_method")
    if not order_id or not method:
        await update.message.reply_text("Ошибка обработки оплаты. Пожалуйста, попробуйте снова.")
        return

    update_payment(order_id, method, text)
    await context.bot.send_message(
        ADMIN_ID,
        f"💰 Оплата добавлена\nID: {order_id}\nМетод: {method}\nДанные: {text}"
    )
    await update.message.reply_text("✅ Оплата сохранена.")

    user_data_store[update.effective_user.id] = {}

    await update.message.reply_text(
        f"Пожалуйста, пришлите скриншот вашего отзыва для товара: {data.get('product_name', '—')} ✅"
    )

# ================= HANDLE PHOTO =================
async def handle_photo(update: Update, user_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM orders
            WHERE user_id=? AND review_sent=0
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        order = cursor.fetchone()

    if not order:
        await update.message.reply_text("Нет активного заказа для добавления скриншота.")
        return

    order_id = order[0]
    os.makedirs("reviews", exist_ok=True)

    try:
        file = await update.message.photo[-1].get_file()
        file_path = f"reviews/review_{user_id}_{order_id}.jpg"
        await file.download_to_drive(file_path)
        mark_review_sent(order_id)
        await update.message.reply_text("Спасибо за ваш отзыв! ✅")
        print(f"Сохранён скриншот: {file_path}")
    except Exception as e:
        await update.message.reply_text("Ошибка при сохранении скриншота.")
        print(f"Ошибка при сохранении скриншота: {e}")

# ================= DAILY REMINDERS =================
async def review_reminder(context: ContextTypes.DEFAULT_TYPE):
    orders = get_orders_pending_review()
    for order_id, user_id, product_name in orders:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Здравствуйте! Пожалуйста, пришлите скриншот вашего отзыва для товара: {product_name} ✅"
            )
        except Exception as e:
            print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")

# ================= RUN BOT =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myorders", my_orders))
    app.add_handler(CommandHandler("allorders", all_orders))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_message))

    # Daily reminders
    app.job_queue.run_daily(review_reminder, time=time(10, 0))
    app.job_queue.run_daily(review_reminder, time=time(18, 0))

    print("✅ Bot running...")
    app.run_polling()
    
# import os
# import sys
# import json
# import sqlite3
# from dotenv import load_dotenv
# from datetime import time

# from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# from telegram.ext import (
#     ApplicationBuilder,
#     CommandHandler,
#     MessageHandler,
#     CallbackQueryHandler,
#     ContextTypes,
#     filters,
# )

# # ================= LOAD ENV =================
# load_dotenv()
# TOKEN = os.getenv("BOT_TOKEN")
# if not TOKEN:
#     print("❌ BOT_TOKEN not set.")
#     sys.exit(1)

# ADMIN_ID = 165665465
# DB_NAME = "orders.db"
# user_data_store = {}

# # ================= LOAD PRODUCTS =================
# def load_products():
#     try:
#         with open("products.json", "r", encoding="utf-8") as f:
#             return json.load(f)
#     except Exception as e:
#         print(f"❌ Error loading products.json: {e}")
#         sys.exit(1)

# products = load_products()

# # ================= DATABASE =================
# def get_connection():
#     return sqlite3.connect(DB_NAME)

# def init_db():
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             CREATE TABLE IF NOT EXISTS orders (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 user_id INTEGER,
#                 product_name TEXT,
#                 product_link TEXT,
#                 quantity INTEGER,
#                 customer_name TEXT,
#                 order_number TEXT,
#                 payment_method TEXT,
#                 payment_info TEXT,
#                 review_sent INTEGER DEFAULT 0,
#                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#             )
#         """)
#         conn.commit()

# def save_order(user_id, data):
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             INSERT INTO orders 
#             (user_id, product_name, product_link, quantity, customer_name, order_number)
#             VALUES (?, ?, ?, ?, ?, ?)
#         """, (
#             user_id,
#             data["product_name"],
#             data["product_link"],
#             data["quantity"],
#             data["customer_name"],
#             data["order_number"]
#         ))
#         conn.commit()
#         return cursor.lastrowid

# def update_payment(order_id, method, info):
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             UPDATE orders 
#             SET payment_method=?, payment_info=? 
#             WHERE id=?
#         """, (method, info, order_id))
#         conn.commit()

# def mark_review_sent(order_id):
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("UPDATE orders SET review_sent=1 WHERE id=?", (order_id,))
#         conn.commit()

# def get_user_orders(user_id):
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             SELECT id, product_name, quantity, created_at
#             FROM orders
#             WHERE user_id=?
#             ORDER BY created_at DESC
#         """, (user_id,))
#         return cursor.fetchall()

# def get_orders_pending_review():
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("SELECT id, user_id, product_name FROM orders WHERE review_sent=0")
#         return cursor.fetchall()

# def get_all_orders():
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             SELECT id, user_id, product_name, product_link, quantity, customer_name, order_number, payment_method, payment_info, review_sent, created_at
#             FROM orders
#             ORDER BY created_at DESC
#         """)
#         return cursor.fetchall()

# def get_stats():
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("SELECT COUNT(*) FROM orders")
#         total_orders = cursor.fetchone()[0]

#         cursor.execute("SELECT SUM(quantity) FROM orders")
#         total_quantity = cursor.fetchone()[0] or 0

#         return total_orders, total_quantity

# init_db()

# # ================= COMMANDS =================
# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = update.effective_user.id
#     user_data_store[user_id] = {}

#     keyboard = [[InlineKeyboardButton(p["name"], callback_data=f"product_{p['name']}")] for p in products]
#     await update.message.reply_text("Здравствуйте! Выберите ваш заказ:", reply_markup=InlineKeyboardMarkup(keyboard))

# async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = update.effective_user.id
#     orders = get_user_orders(user_id)
#     if not orders:
#         await update.message.reply_text("У вас пока нет заказов.")
#         return

#     message = "📦 Ваши заказы:\n\n"
#     for order in orders:
#         message += f"ID: {order[0]}\nТовар: {order[1]}\nКоличество: {order[2]}\nДата: {order[3]}\n\n"
#     await update.message.reply_text(message)

# async def all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if update.effective_user.id != ADMIN_ID:
#         await update.message.reply_text("Нет доступа.")
#         return

#     orders = get_all_orders()
#     if not orders:
#         await update.message.reply_text("Нет заказов.")
#         return

#     message = "📊 Все заказы с полными данными клиентов:\n\n"
#     for order in orders:
#         message += (
#             f"ID: {order[0]}\nUser ID: {order[1]}\nТовар: {order[2]}\nСсылка: {order[3]}\n"
#             f"Количество: {order[4]}\nИмя клиента: {order[5] or '—'}\nНомер заказа: {order[6] or '—'}\n"
#             f"Метод оплаты: {order[7] or '—'}\nДанные оплаты: {order[8] or '—'}\n"
#             f"Отзыв получен: {'✅' if order[9] else '❌'}\nДата: {order[10]}\n\n"
#         )

#     for chunk in [message[i:i+4000] for i in range(0, len(message), 4000)]:
#         await update.message.reply_text(chunk)

# async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     if update.effective_user.id != ADMIN_ID:
#         await update.message.reply_text("Нет доступа.")
#         return

#     total_orders, total_quantity = get_stats()
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             SELECT payment_method, COUNT(*) FROM orders
#             WHERE payment_method IS NOT NULL
#             GROUP BY payment_method
#         """)
#         payment_counts = cursor.fetchall()
#     payment_summary = "\n".join([f"{row[0]}: {row[1]}" for row in payment_counts]) or "Нет данных об оплате."

#     await update.message.reply_text(
#         f"📈 Статистика:\nВсего заказов: {total_orders}\nВсего продано товаров: {total_quantity}\nОплаты:\n{payment_summary}"
#     )

# # ================= CALLBACK =================
# # ================= CALLBACK HANDLER =================
# async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
#     user_id = query.from_user.id
#     data = user_data_store.setdefault(user_id, {})

#     try:
#         if query.data.startswith("product_"):
#             await handle_product_selection(update, data)
#         elif query.data in ["zelle", "venmo"]:
#             await handle_payment_selection(update, data)
#         elif query.data == "cancel":
#             await handle_cancel(update, user_id)
#         else:
#             await query.edit_message_text("Неизвестная команда.")
#     except Exception as e:
#         print(f"Ошибка в button_handler: {e}")
#         await query.edit_message_text("Произошла ошибка при обработке кнопки.")


# # ---------------- HELPER FUNCTIONS ----------------
# async def handle_product_selection(update: Update, data: dict):
#     """Handle product selection from inline keyboard."""
#     product_name = update.callback_query.data.replace("product_", "")
#     product = next((p for p in products if p["name"] == product_name), None)

#     if not product:
#         await update.callback_query.edit_message_text("Продукт не найден.")
#         return

#     data["product_name"] = product["name"]
#     data["product_link"] = product["link"]

#     await update.callback_query.message.reply_text(f"🔗 Ссылка на товар:\n{product['link']}")
#     await update.callback_query.message.reply_text(f"Вы выбрали: {product_name}\nВведите количество:")


# async def handle_payment_selection(update: Update, data: dict):
#     """Handle Zelle or Venmo payment selection."""
#     data["payment_method"] = update.callback_query.data.capitalize()
#     data["awaiting_payment_info"] = True
#     await update.callback_query.edit_message_text(
#         f"Вы выбрали {data['payment_method']}.\nВведите данные для оплаты:"
#     )


# async def handle_cancel(update: Update, user_id: int):
#     """Handle order cancellation."""
#     user_data_store[user_id] = {}
#     await update.callback_query.edit_message_text("❌ Заказ отменён.")

# # ================= MESSAGE HANDLER =================
# async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = update.effective_user.id
#     data = user_data_store.setdefault(user_id, {})

#     # ===== PHOTO HANDLING =====
#     if update.message.photo:
#         await handle_photo(update, user_id)
#         return

#     # ===== TEXT HANDLING =====
#     text = (update.message.text or "").strip()
#     if not text:
#         await update.message.reply_text("Пожалуйста, введите текстовое сообщение.")
#         return

#     # Step-by-step order flow
#     if "product_name" not in data:
#         await update.message.reply_text("Используйте /start, чтобы выбрать товар.")
#         return

#     if "quantity" not in data:
#         await handle_quantity(update, data, text)
#         return

#     if "customer_name" not in data:
#         await handle_customer_name(update, data, text)
#         return

#     if "order_number" not in data:
#         await handle_order_number(update, context, data, text)
#         return

#     if data.get("awaiting_payment_info"):
#         await handle_payment(update, context, data, text)
#         return


# # ================= HELPER FUNCTIONS =================
# async def handle_photo(update: Update, user_id: int):
#     """Save review screenshot and mark review sent."""
#     with get_connection() as conn:
#         cursor = conn.cursor()
#         cursor.execute("""
#             SELECT id FROM orders
#             WHERE user_id=? AND review_sent=0
#             ORDER BY created_at DESC LIMIT 1
#         """, (user_id,))
#         order = cursor.fetchone()

#     if not order:
#         await update.message.reply_text("Нет активного заказа для добавления скриншота.")
#         return

#     order_id = order[0]
#     os.makedirs("reviews", exist_ok=True)

#     try:
#         file = await update.message.photo[-1].get_file()
#         file_path = f"reviews/review_{user_id}_{order_id}.jpg"
#         await file.download_to_drive(file_path)
#         mark_review_sent(order_id)
#         await update.message.reply_text("Спасибо за ваш отзыв! ✅")
#         print(f"Сохранён скриншот: {file_path}")
#     except Exception as e:
#         await update.message.reply_text("Ошибка при сохранении скриншота.")
#         print(f"Ошибка при сохранении скриншота: {e}")


# async def handle_quantity(update: Update, data: dict, text: str):
#     if not text.isdigit() or int(text) <= 0:
#         await update.message.reply_text("Введите положительное число.")
#         return
#     data["quantity"] = int(text)
#     await update.message.reply_text("Введите ваше полное имя:")


# async def handle_quantity(update: Update, data: dict, text: str):
#     if not text.isdigit() or int(text) <= 0:
#         await update.message.reply_text("Введите положительное число.")
#         return
    
#     requested_qty = int(text)
#     product = next((p for p in products if p["name"] == data["product_name"]), None)
    
#     if not product:
#         await update.message.reply_text("Ошибка: продукт не найден.")
#         return
    
#     if requested_qty > product.get("stock", 0):
#         await update.message.reply_text(f"Извините, на складе доступно только {product['stock']} шт.")
#         return
    
#     data["quantity"] = requested_qty
#     await update.message.reply_text("Введите ваше полное имя:")

# async def handle_order_number(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict, text: str):
#     data["order_number"] = text
#     order_id = save_order(update.effective_user.id, data)
#     data["order_id"] = order_id

#     await context.bot.send_message(
#         ADMIN_ID,
#         f"📦 Новый заказ\nID: {order_id}\nПродукт: {data['product_name']}\nКол-во: {data['quantity']}"
#     )

#     # Ask for review immediately
#     await update.message.reply_text(
#         f"Спасибо за заказ! Пожалуйста, будьте готовы пришлить скриншот вашего отзыва для товара: {data['product_name']} ✅"
#     )

#     # Payment buttons
#     keyboard = [
#         [InlineKeyboardButton("Zelle", callback_data="zelle"), InlineKeyboardButton("Venmo", callback_data="venmo")],
#         [InlineKeyboardButton("❌ Отменить", callback_data="cancel")]
#     ]
#     await update.message.reply_text(
#         "Как хотите получить оплату?",
#         reply_markup=InlineKeyboardMarkup(keyboard)
#     )


# async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict, text: str):
#     order_id = data.get("order_id")
#     method = data.get("payment_method")
#     if not order_id or not method:
#         await update.message.reply_text("Ошибка обработки оплаты. Пожалуйста, попробуйте снова.")
#         return

#     update_payment(order_id, method, text)
#     await context.bot.send_message(
#         ADMIN_ID,
#         f"💰 Оплата добавлена\nID: {order_id}\nМетод: {method}\nДанные: {text}"
#     )
#     await update.message.reply_text("✅ Оплата сохранена.")

#     # Reset user session
#     user_data_store[update.effective_user.id] = {}

#     # Ask for review immediately if not already done
#     await update.message.reply_text(
#         f"Пожалуйста, пришлите скриншот вашего отзыва для товара: {data.get('product_name', '—')} ✅"
#     )
# # ================= DAILY REVIEW REMINDER =================
# async def review_reminder(context: ContextTypes.DEFAULT_TYPE):
#     orders = get_orders_pending_review()
#     for order_id, user_id, product_name in orders:
#         try:
#             await context.bot.send_message(
#                 chat_id=user_id,
#                 text=f"Здравствуйте! Пожалуйста, пришлите скриншот вашего отзыва для товара: {product_name} ✅"
#             )
#         except Exception as e:
#             print(f"Не удалось отправить напоминание пользователю {user_id}: {e}")

# # ================= RUN =================
# if __name__ == "__main__":
#     app = ApplicationBuilder().token(TOKEN).build()

#     app.add_handler(CommandHandler("start", start))
#     app.add_handler(CommandHandler("myorders", my_orders))
#     app.add_handler(CommandHandler("allorders", all_orders))
#     app.add_handler(CommandHandler("stats", stats))
#     app.add_handler(CallbackQueryHandler(button_handler))
#     app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
#     app.add_handler(MessageHandler(filters.PHOTO, handle_message))

#     # Daily reminders
#     app.job_queue.run_daily(review_reminder, time=time(10, 0))
#     app.job_queue.run_daily(review_reminder, time=time(18, 0))

#     print("✅ Bot running...")
#     app.run_polling()