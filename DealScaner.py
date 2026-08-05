import re
import time
import random
import sqlite3
import threading
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.parse

import tkinter as tk
from tkinter import ttk, messagebox

# КОНФИГУРАЦИЯ ПОЧТЫ
EMAIL_SETTINGS = {

    "smtp_server": "smtp.yandex.ru",

    "smtp_port": 465,

    "sender_email": "Bezzy69@yandex.ru",

    "sender_password": "bmcxaxdduyxiivyu",

}


# КЛАСС БАЗЫ ДАННЫХ
class SteamPriceDatabase:
    def __init__(self, db_name="steam_monitor_base.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_hash_name TEXT NOT NULL UNIQUE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    error_message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    current_price REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_searches (
                    search_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def save_error(self, email, item_name, error_message):

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ищем предмет
            cursor.execute(
                """
                SELECT item_id 
                FROM items 
                WHERE market_hash_name = ?
                """,
                (item_name,)
            )

            row = cursor.fetchone()

            # если предмета ещё нет — создаём
            if row:
                item_id = row[0]

            else:
                cursor.execute(
                    """
                    INSERT INTO items(market_hash_name)
                    VALUES(?)
                    """,
                    (item_name,)
                )

                item_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO error_logs
                (email, item_id, error_message, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    email,
                    item_id,
                    error_message,
                    now
                )
            )

            conn.commit()
    def save_user_search(self, email, item_name):

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                """
                SELECT item_id 
                FROM items 
                WHERE market_hash_name = ?
                """,
                (item_name,)
            )

            row = cursor.fetchone()

            if row:
                item_id = row[0]

            else:
                cursor.execute(
                    """
                    INSERT INTO items(market_hash_name)
                    VALUES(?)
                    """,
                    (item_name,)
                )

                item_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO user_searches
                (email, item_id, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    email,
                    item_id,
                    now
                )
            )

            conn.commit()
    def save_price(self, item_name, price):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("SELECT item_id FROM items WHERE market_hash_name = ?", (item_name,))
            row = cursor.fetchone()

            if row:
                item_id = row[0]
            else:
                cursor.execute("INSERT INTO items (market_hash_name) VALUES (?)", (item_name,))
                item_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO price_log (item_id, current_price, timestamp) VALUES (?, ?, ?)",
                (item_id, price, now)
            )
            conn.commit()


# ГРАФИЧЕСКИЙ ИНТЕРФЕЙС И ЛОГИКА БОТА
class SteamBotGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Deal scaner v2.0")
        self.root.geometry("500x640")
        self.root.resizable(False, False)

        # Цветовая палитра в стиле Steam
        self.bg_dark = "#171a21"
        self.bg_panel = "#1b2838"
        self.fg_light = "#c7d5e0"
        self.accent_blue = "#66c0f4"
        self.btn_green = "#5c7e10"
        self.btn_red = "#a33a3a"

        self.root.configure(bg=self.bg_dark)

        self.db = SteamPriceDatabase()
        self.is_monitoring = False
        self.monitor_thread = None

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        self.setup_styles()
        self.create_widgets()

    def setup_styles(self):

        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Настройка фреймов
        self.style.configure("TFrame", background=self.bg_dark)
        self.style.configure("Card.TLabelframe", background=self.bg_dark, bordercolor="#2a475e", borderwidth=1)
        self.style.configure("Card.TLabelframe.Label", background=self.bg_dark, foreground=self.accent_blue,
                             font=("Helvetica", 10, "bold"))

        # Настройка надписей
        self.style.configure("TLabel", background=self.bg_dark, foreground=self.fg_light, font=("Helvetica", 10))
        self.style.configure("Header.TLabel", background=self.bg_dark, foreground=self.accent_blue,
                             font=("Helvetica", 15, "bold"))
        self.style.configure("Price.TLabel", background=self.bg_panel, foreground="#90ba3c",
                             font=("Helvetica", 14, "bold"))
        self.style.configure("Sub.TLabel", background=self.bg_dark, foreground="#66c0f4",
                             font=("Helvetica", 9, "italic"))

        # Настройка полей ввода
        self.style.configure("TEntry", fieldbackground=self.bg_panel, foreground="#ffffff", bordercolor="#2a475e",
                             lightcolor="#2a475e", darkcolor="#2a475e")

        # Настройка кнопок
        self.style.configure("Start.TButton", background=self.btn_green, foreground="#ffffff",
                             font=("Helvetica", 11, "bold"), borderwidth=0)
        self.style.map("Start.TButton", background=[("active", "#7a9b1c"), ("pressed", "#47620c")])

        self.style.configure("Stop.TButton", background=self.btn_red, foreground="#ffffff",
                             font=("Helvetica", 11, "bold"), borderwidth=0)
        self.style.map("Stop.TButton", background=[("active", "#c24a4a"), ("pressed", "#822d2d")])

    def create_widgets(self):

        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(main_frame, text="🛒 DEAL SCANER", style="Header.TLabel")
        title_label.pack(pady=(0, 5), anchor=tk.CENTER)

        sub_title = ttk.Label(main_frame, text="Поиск сделок в реальном времени", style="Sub.TLabel")
        sub_title.pack(pady=(0, 20), anchor=tk.CENTER)

        # Панель параметров (Инпуты)
        input_frame = ttk.LabelFrame(main_frame, text=" НАСТРОЙКИ ОТСЛЕЖИВАНИЯ", style="Card.TLabelframe", padding="15")
        input_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(input_frame, text="App ID игры (CS2 = 730):").pack(anchor=tk.W, pady=(0, 2))
        self.entry_appid = ttk.Entry(input_frame, font=("Helvetica", 10))
        self.entry_appid.insert(0, "730")
        self.entry_appid.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="Название предмета (ID):").pack(anchor=tk.W, pady=(0, 2))
        self.entry_item = ttk.Entry(input_frame, font=("Helvetica", 10))
        self.entry_item.insert(0, "G18DF363004")
        self.entry_item.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(input_frame, text="Целевая цена выкупа (руб.):").pack(anchor=tk.W, pady=(0, 2))
        self.entry_target = ttk.Entry(input_frame, font=("Helvetica", 10))
        self.entry_target.insert(0, "1000.0")
        self.entry_target.pack(fill=tk.X, pady=(0, 5))



        ttk.Label(input_frame, text="Email для уведомлений:").pack(anchor=tk.W, pady=(10, 2))
        self.entry_email = ttk.Entry(input_frame, font=("Helvetica", 10))
        self.entry_email.pack(fill=tk.X, pady=(0, 10))

        # Информационное табло с ценой
        self.price_frame = ttk.Frame(main_frame, padding="10")
        self.price_frame.pack(fill=tk.X, pady=(0, 15))
        self.price_frame.configure(style="TFrame")

        self.lbl_live_price = tk.Label(
            self.price_frame,
            text="Текущая цена: — руб.",
            font=("Helvetica", 12, "bold"),
            bg=self.bg_panel,
            fg="#90ba3c",
            bd=1,
            relief="solid",
            highlightbackground="#2a475e",
            pady=8
        )
        self.lbl_live_price.pack(fill=tk.X)

        # Кнопка управления
        self.btn_toggle = ttk.Button(main_frame, text="▶ Запустить мониторинг", style="Start.TButton",
                                     command=self.toggle_monitoring)
        self.btn_toggle.pack(fill=tk.X, ipady=6, pady=(0, 15))

        # Консоль логов
        ttk.Label(main_frame, text="ЛОГ РАБОТЫ СИСТЕМЫ:", font=("Helvetica", 9, "bold"), foreground="#567287").pack(
            anchor=tk.W)

        self.log_box = tk.Text(
            main_frame,
            height=10,
            font=("Consolas", 9),
            bg="#101822",
            fg="#8bf5fa",
            insertbackground="white",
            bd=1,
            relief="solid",
            highlightcolor="#2a475e"
        )

        self.log_box.bind("<Key>", lambda e: "break")
        self.log_box.bind("<Control-c>", lambda e: self.log_box.event_generate("<<Copy>>"))
        self.log_box.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

    def log(self, message):

        now = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{now}] {message}\n"

        self.log_box.insert(tk.END, full_msg)
        self.log_box.see(tk.END)

    def send_email(self, item_name, current_price, target_price, receiver_email):
        """Отправка красивого уведомления на почту."""
        self.log("[SMTP] Формирование графического HTML-уведомления...")

        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_SETTINGS['sender_email']
        msg['To'] = receiver_email
        msg['Subject'] = f"🎯 Снайпер сработал: {item_name} подешевел!"

        # Формируем прямую ссылку на предмет на Торговой Площадке Steam
        url_encoded_name = urllib.parse.quote(item_name)
        app_id = self.entry_appid.get().strip()
        item_link = f"https://steamcommunity.com/market/listings/{app_id}/{url_encoded_name}"

        img_url = "https://community.cloudflare.steamstatic.com/public/images/signin_steam_logo.png"

        html_body = f"""
        <html>
        <body style="background-color: #171a21; margin: 0; padding: 20px; font-family: Arial, sans-serif; color: #c7d5e0;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #1b2838; border: 1px solid #2a475e; border-radius: 4px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.5);">

                <!-- Шапка карточки -->
                <div style="background-color: #101822; padding: 15px; text-align: center; border-bottom: 2px solid #66c0f4;">
                    <h2 style="color: #66c0f4; margin: 0; font-size: 20px; letter-spacing: 1px;">🛒 ТРИГГЕР DEAL SCANER </h2>
                </div>

                <!-- Контентная часть -->
                <div style="padding: 20px; text-align: center;">
                    <span style="display: inline-block; background-color: #2a475e; color: #66c0f4; font-size: 11px; padding: 3px 8px; border-radius: 3px; margin-bottom: 10px; font-weight: bold; text-transform: uppercase;">
                        Предмет отслеживания
                    </span>
                    <h3 style="color: #ffffff; margin: 0 0 15px 0; font-size: 18px;">{item_name}</h3>

                    <!-- Декоративный бокс с логотипом -->
                    <div style="background: radial-gradient(circle, #2a475e 0%, #171a21 100%); border: 1px solid #2a475e; border-radius: 4px; padding: 25px; margin-bottom: 20px; display: inline-block; width: 80%;">
                        <img src="{img_url}" alt="Steam" style="max-width: 140px; height: auto; display: block; margin: 0 auto;" />
                    </div>

                    <!-- Финансовая таблица параметров -->
                    <table style="width: 100%; margin-bottom: 20px; border-collapse: collapse; background-color: #121a24; border-radius: 4px;">
                        <tr>
                            <td style="padding: 12px; text-align: left; color: #8a9eaf; border-bottom: 1px solid #1b2838;">Живая цена лота:</td>
                            <td style="padding: 12px; text-align: right; color: #a4d007; font-weight: bold; font-size: 18px; border-bottom: 1px solid #1b2838;">{current_price} руб.</td>
                        </tr>
                        <tr>
                            <td style="padding: 12px; text-align: left; color: #8a9eaf;">Твоя цель выкупа:</td>
                            <td style="padding: 12px; text-align: right; color: #ffffff; font-weight: bold;">{target_price} руб.</td>
                        </tr>
                    </table>

                    <!-- Большая зеленая кнопка быстрого перехода к выкупу -->
                    <a href="{item_link}" target="_blank" style="display: block; background-color: #a4d007; color: #171a21; text-decoration: none; padding: 13px 20px; font-weight: bold; border-radius: 3px; font-size: 15px; margin-top: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.3);">
                        ОТКРЫТЬ НА ТОРГОВОЙ ПЛОЩАДКЕ →
                    </a>
                </div>

                <!-- Подвал -->
                <div style="background-color: #101822; padding: 10px; text-align: center; font-size: 11px; color: #567287;">
                    Система мониторинга цен • {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        try:
            server = smtplib.SMTP_SSL(EMAIL_SETTINGS['smtp_server'], EMAIL_SETTINGS['smtp_port'])
            server.login(EMAIL_SETTINGS['sender_email'], EMAIL_SETTINGS['sender_password'])
            server.sendmail(
                EMAIL_SETTINGS['sender_email'],
                receiver_email,
                msg.as_string()
            )
            server.quit()
            self.log("[SMTP] Красивое HTML-уведомление успешно доставлено на Email!")
        except Exception as e:
            self.log(f"[SMTP ERROR] Ошибка отправки: {e}")

    def fetch_price(self, app_id, item_name):
        url_encoded_name = urllib.parse.quote(item_name)
        url = "https://steamcommunity.com/market/priceoverview/"
        params = {"country": "RU", "currency": "5", "appid": app_id, "market_hash_name": url_encoded_name}

        try:
            res = requests.get(url, params=params, headers=self.headers, timeout=12)

            if res.status_code == 200:
                data = res.json()
                self.log(f"[STEAM RESPONSE] {data}")
                if data.get("success"):

                    raw_price = data.get("lowest_price") or data.get("median_price")

                    if not raw_price:
                        self.log("[API] Цена отсутствует в ответе Steam")
                        return None

                    clean_price = (
                        raw_price
                        .replace("руб.", "")
                        .replace(" ", "")
                        .replace("\xa0", "")
                    )

                    clean_price = clean_price.replace(",", ".")

                    price_float = float(
                        ''.join(
                            c for c in clean_price
                            if c.isdigit() or c == '.'
                        )
                    )

                    return price_float
                else:
                    self.log("[API] Steam ответил success: false.")
                    return None


            elif res.status_code == 429:

                self.db.save_error(

                    self.entry_email.get().strip(),

                    item_name,

                    "Steam API: превышен лимит запросов"

                )

                self.log("[API Ошибка] Код 429")

                return None
            elif res.status_code == 403:

                self.db.save_error(
                    self.entry_email.get().strip(),
                    item_name,
                    "Steam API: 403 доступ заблокирован"
                )

                self.log("[API Ошибка] Код 403: Доступ заблокирован СТИМом.")
                return None
            else:
                self.db.save_error(
                    self.entry_email.get().strip(),
                    item_name,
                    "Steam API: success=false, цена не найдена"
                )

                self.log("[API] Steam ответил success: false.")
                return None

        except requests.exceptions.JSONDecodeError:
            self.log("[API Критическая ошибка] Вместо JSON прилетел HTML (капча/блок).")
            return None
        except Exception as e:
            self.log(f"[ERROR] Ошибка сети: {e}")
            return None

    def update_live_price_label(self, price_text):
        """Безопасное обновление плашки цены из основного потока."""
        self.lbl_live_price.config(text=price_text)

    def monitoring_loop(self, app_id, item_name, target_price, receiver_email):
        while self.is_monitoring:
            price = self.fetch_price(app_id, item_name)

            if price is not None:
                # Обновляем ценник на красивой панели
                self.root.after(0, self.update_live_price_label, f"Текущая цена: {price:.2f} руб.")
                self.log(f"Парсинг успешен. Цена: {price} руб.")
                self.db.save_price(item_name, price)

                if price <= target_price:
                    self.log("🎯 ТРИГГЕР СРАБОТАЛ! Цена упала ниже целевой.")
                    self.send_email(
                        item_name,
                        price,
                        target_price,
                        receiver_email
                    )

                    self.is_monitoring = False
                    self.root.after(0, self.reset_gui_button)
                    break
            else:
                self.root.after(0, self.update_live_price_label, "Текущая цена: Ошибка запроса ⚠️")
                self.log("[Ожидание] Сессия занята. Повтор через 30 сек...")

            if self.is_monitoring:
                time.sleep(30 + random.uniform(1.0, 5.0))

    def reset_gui_button(self):
        self.btn_toggle.config(text="▶ Запустить мониторинг", style="Start.TButton")
        messagebox.showinfo("Успех", "Целевая цена достигнута! Проверьте почту.")

    def toggle_monitoring(self):
        if not self.is_monitoring:
            app_id = self.entry_appid.get().strip()
            item_name = self.entry_item.get().strip()
            receiver_email = self.entry_email.get().strip()
            raw_id = self.entry_item.get().strip()
            self.log(f"[API] Запрашиваем у Steam имя для ID: {raw_id}...")
            try:
                target_price = float(self.entry_target.get().strip())
            except ValueError:
                self.db.save_error(
                    receiver_email if receiver_email else "unknown",
                    item_name if item_name else "unknown",
                    "Некорректное значение целевой цены"
                )
                messagebox.showerror("Ошибка", "Введите число в поле желаемой суммы!")
                return

            if not app_id or not item_name:
                self.db.save_error(
                    receiver_email if receiver_email else "unknown",
                    item_name if item_name else "unknown",
                    "Не заполнены обязательные поля"
                )
                messagebox.showerror("Ошибка", "Заполните все поля!")
                return

            if not receiver_email:
                self.db.save_error(
                    "unknown",
                    item_name if item_name else "unknown",
                    "Email не указан"
                )
                messagebox.showerror("Ошибка", "Введите Email для уведомлений!")
                return

            if not re.match(r"[^@]+@[^@]+\.[^@]+", receiver_email):
                self.db.save_error(
                    receiver_email,
                    item_name if item_name else "unknown",
                    "Некорректный формат Email"
                )
                messagebox.showerror(
                    "Ошибка",
                    "Введите корректный Email!"
                )
                return
            self.db.save_user_search(
                    receiver_email,
                    item_name
                )
            self.is_monitoring = True
            self.btn_toggle.config(text="⏹ Остановить мониторинг", style="Stop.TButton")
            self.log(f"Старт мониторинга: {item_name}")

            self.monitor_thread = threading.Thread(
                target=self.monitoring_loop,
                args=(app_id, item_name, target_price, receiver_email),
                daemon=True
            )
            self.monitor_thread.start()
        else:
            self.is_monitoring = False
            self.btn_toggle.config(text="▶ Запустить мониторинг", style="Start.TButton")
            self.log("Мониторинг остановлен пользователем.")


if __name__ == "__main__":
    root_window = tk.Tk()
    app = SteamBotGUI(root_window)
    root_window.mainloop()
