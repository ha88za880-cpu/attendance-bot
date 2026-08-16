import os
import sqlite3
import csv
import time
from datetime import datetime
import telebot
from telebot import types

# ================= البيانات الأساسية =================
BOT_TOKEN = "8764423533:AAFRwaQPHQ85ElqNBkXvCbNB-6be6jjmAm4"
ENGINEER_ID = 1077265756

bot = telebot.TeleBot(BOT_TOKEN)

# ================= قاعدة البيانات =================
def init_db():
    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_name TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            time TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        sample_employees = [
            ("أحمد محمود",),
            ("محمد علي",),
            ("سارة حسن",),
            ("خالد إبراهيم",),
            ("محمود السيد",)
        ]
        cursor.executemany("INSERT INTO employees (name) VALUES (?)", sample_employees)
    conn.commit()
    conn.close()

init_db()
active_sessions = {}

# ================= لوحة الأزرار الرئيسية =================
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📝 تسجيل الحضور اليومي")
    markup.row("📊 استخراج تقرير الإكسيل")
    return markup

# ================= استقبال الأوامر =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "👋 مرحباً يا باشمهندس!\n\n"
        "استخدم الأزرار بالأسفل للبدء:",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda msg: msg.text in ["📝 تسجيل الحضور اليومي", "/take_attendance"])
def start_attendance(message):
    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM employees")
    employees = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not employees:
        bot.send_message(message.chat.id, "⚠️ لا يوجد موظفين مسجلين.")
        return

    active_sessions[message.chat.id] = {
        "employees": employees,
        "current_index": 0
    }
    ask_employee_status(message.chat.id)

def ask_employee_status(chat_id):
    session = active_sessions.get(chat_id)
    if not session:
        return

    idx = session["current_index"]
    if idx < len(session["employees"]):
        emp_name = session["employees"][idx]
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("حاضر ✅", callback_data=f"status|{emp_name}|حاضر"),
            types.InlineKeyboardButton("متأخر ⏳", callback_data=f"status|{emp_name}|متأخر"),
            types.InlineKeyboardButton("غائب ❌", callback_data=f"status|{emp_name}|غائب")
        )
        bot.send_message(
            chat_id, 
            f"تسجيل الموظف ({idx + 1}/{len(session['employees'])}):\n👤 **{emp_name}**", 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
    else:
        bot.send_message(chat_id, "🎉 تم تسجيل حضور جميع الموظفين بنجاح!", reply_markup=main_menu())
        del active_sessions[chat_id]

# ================= معالجة أزرار الحضور =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("status|"))
def handle_attendance_callback(call):
    _, emp_name, status = call.data.split("|")
    today_date = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M:%S")

    conn = sqlite3.connect("attendance.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM attendance WHERE emp_name = ? AND date = ?", (emp_name, today_date))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute("UPDATE attendance SET status = ?, time = ? WHERE id = ?", (status, current_time, existing[0]))
    else:
        cursor.execute("INSERT INTO attendance (emp_name, date, status, time) VALUES (?, ?, ?, ?)", (emp_name, today_date, status, current_time))
    
    conn.commit()
    conn.close()

    bot.answer_callback_query(call.id, text=f"تم تسجيل {emp_name}: {status}")
    bot.edit_message_text(f"👤 {emp_name}: **{status}**", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")

    if call.message.chat.id in active_sessions:
        active_sessions[call.message.chat.id]["current_index"] += 1
        ask_employee_status(call.message.chat.id)

# ================= استخراج التقرير =================
@bot.message_handler(func=lambda msg: msg.text in ["📊 استخراج تقرير الإكسيل", "/send_report", "send report", "تقرير"])
def handle_report(message):
    try:
        bot.send_message(message.chat.id, "⏳ جاري استخراج ملف الإكسيل...")
        
        conn = sqlite3.connect("attendance.db")
        cursor = conn.cursor()
        cursor.execute("SELECT emp_name, date, status, time FROM attendance")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            bot.send_message(message.chat.id, "⚠️ لا توجد سجلات حضور مسجلة حتى الآن.")
            return

        file_path = f"Attendance_{datetime.now().strftime('%Y%m%d')}.csv"
        with open(file_path, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            writer.writerow(["اسم الموظف", "التاريخ", "الحالة", "الوقت"])
            writer.writerows(rows)

        with open(file_path, "rb") as doc:
            bot.send_document(message.chat.id, doc, caption="📊 تقرير الحضور والانصراف (ملف إكسيل جاهز)")

        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        bot.send_message(message.chat.id, f"حدث خطأ أثناء استخراج التقرير: {e}")

# ================= التشغيل المستمر ومقاومة الانقطاع =================
if __name__ == "__main__":
    print("Bot is running and protected against disconnections...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Connection lost, retrying in 5 seconds... Error: {e}")
            time.sleep(5)
