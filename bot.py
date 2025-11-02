import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора
FIO, UNIT, EQUIPMENT, DATES, TIME_SELECTION, CONFIRMATION = range(6)

# ID администраторов для уведомлений
ADMIN_CHAT_IDS = [730691574, 2114604500]  # ЗАМЕНИ НА РЕАЛЬНЫЕ ID

# ID Google таблицы (можно получить из URL)
SPREADSHEET_ID = "1IhI_3WR2y8iBLQa9X_-0Vjn0RGnuTVpghNSurkmnlRk"  # ЗАМЕНИ НА РЕАЛЬНЫЙ ID

# Список доступного оборудования
AVAILABLE_EQUIPMENT = """
📹 Камеры:
- Sony FX6 (2 шт.)
- Canon C70 (3 шт.)

🎤 Аудио оборудование:
- Rode Wireless Go II (4 шт.)
- Zoom H6 Recorder (2 шт.)

💡 Свет:
- Aputure 300D (2 шт.)
- Godox SL60W (3 шт.)

🎬 Стабилизация:
- DJI Ronin RS2 (2 шт.)
- Триподы Manfrotto (5 шт.)
"""

class GoogleSheetsManager:
    def __init__(self, creds_file: str, spreadsheet_id: str):
        self.creds_file = creds_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None
        self._connect()
    
    def _connect(self):
        """Подключение к Google Таблицам по ID"""
        try:
            # Область доступа
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            
            # Авторизация
            creds = Credentials.from_service_account_file(self.creds_file, scopes=scopes)
            self.client = gspread.authorize(creds)
            
            # Открытие таблицы по ID
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            logger.info("✅ Успешно подключено к Google Таблицам по ID")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Таблицам: {e}")
            # Создаем заглушку чтобы бот работал даже без таблиц
            self.spreadsheet = None
    
    def setup_sheets(self):
        """Настройка листов в таблице"""
        if not self.spreadsheet:
            logger.warning("❌ Таблица не доступна, пропускаем настройку")
            return False
            
        try:
            # Лист для заявок
            try:
                applications_sheet = self.spreadsheet.worksheet("Заявки")
                logger.info("✅ Лист 'Заявки' уже существует")
            except gspread.WorksheetNotFound:
                applications_sheet = self.spreadsheet.add_worksheet(
                    title="Заявки", rows="1000", cols="15"
                )
                # Заголовки для заявок
                headers = [
                    "Номер заявки", "Дата создания", "ID пользователя", 
                    "ФИО", "Username", "Ссылка на пользователя",
                    "Подразделение/Цель", "Оборудование", 
                    "Даты бронирования", "Статус", "Время обработки",
                    "Комментарий администратора", "Телеграм для связи",
                    "Дата последнего обновления"
                ]
                applications_sheet.append_row(headers)
                logger.info("✅ Создан новый лист 'Заявки' с заголовками")
            
            # Лист для пользователей
            try:
                users_sheet = self.spreadsheet.worksheet("Пользователи")
                logger.info("✅ Лист 'Пользователи' уже существует")
            except gspread.WorksheetNotFound:
                users_sheet = self.spreadsheet.add_worksheet(
                    title="Пользователи", rows="1000", cols="10"
                )
                # Заголовки для пользователей
                headers = [
                    "ID пользователя", "ФИО", "Username", "Дата регистрации",
                    "Количество заявок", "Последняя заявка", "Статус",
                    "Дата последней активности"
                ]
                users_sheet.append_row(headers)
                logger.info("✅ Создан новый лист 'Пользователи' с заголовками")
            
            logger.info("✅ Все листы Google Таблиц настроены")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки листов: {e}")
            return False
    
    def add_application(self, application_data: dict) -> bool:
        """Добавление новой заявки в таблицу"""
        if not self.spreadsheet:
            logger.warning("❌ Таблица не доступна, пропускаем сохранение заявки")
            return False
            
        try:
            sheet = self.spreadsheet.worksheet("Заявки")
            
            application_row = [
                application_data.get("app_number", ""),
                application_data.get("created_at", ""),
                application_data.get("user_id", ""),
                application_data.get("full_name", ""),
                application_data.get("username", ""),
                application_data.get("user_link", ""),
                application_data.get("unit", ""),
                application_data.get("equipment", ""),
                application_data.get("dates_display", ""),
                "НОВАЯ",  # Статус
                "",  # Время обработки
                "",  # Комментарий администратора
                f"https://t.me/{application_data.get('username', '')}",  # Ссылка для связи
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Дата обновления
            ]
            
            sheet.append_row(application_row)
            logger.info(f"✅ Заявка {application_data.get('app_number')} добавлена в Google Таблицы")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка добавления заявки: {e}")
            return False
    
    def update_user(self, user_data: dict) -> bool:
        """Добавление/обновление пользователя в таблице"""
        if not self.spreadsheet:
            logger.warning("❌ Таблица не доступна, пропускаем обновление пользователя")
            return False
            
        try:
            sheet = self.spreadsheet.worksheet("Пользователи")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Ищем пользователя
            try:
                user_cell = sheet.find(str(user_data.get("user_id")))
                # Пользователь существует - обновляем
                row = user_cell.row
                sheet.update_cell(row, 2, user_data.get("full_name", ""))  # ФИО
                sheet.update_cell(row, 3, user_data.get("username", ""))   # Username
                
                # Увеличиваем счетчик заявок
                current_count = sheet.cell(row, 5).value
                new_count = str(int(current_count) + 1) if current_count and current_count.isdigit() else "1"
                sheet.update_cell(row, 5, new_count)
                
                sheet.update_cell(row, 6, current_time)  # Последняя заявка
                sheet.update_cell(row, 8, current_time)  # Дата последней активности
                
                logger.info(f"✅ Пользователь {user_data.get('user_id')} обновлен в Google Таблицах")
                
            except gspread.exceptions.CellNotFound:
                # Новый пользователь
                user_row = [
                    user_data.get("user_id", ""),
                    user_data.get("full_name", ""),
                    user_data.get("username", ""),
                    current_time,  # Дата регистрации
                    "1",  # Количество заявок
                    current_time,  # Последняя заявка
                    "АКТИВНЫЙ",  # Статус
                    current_time  # Дата последней активности
                ]
                sheet.append_row(user_row)
                logger.info(f"✅ Новый пользователь {user_data.get('user_id')} добавлен в Google Таблицы")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления пользователя: {e}")
            return False
    
    def get_user_applications(self, user_id: int) -> list:
        """Получение заявок пользователя"""
        if not self.spreadsheet:
            return []
            
        try:
            sheet = self.spreadsheet.worksheet("Заявки")
            records = sheet.get_all_records()
            
            user_applications = []
            for record in records:
                if str(record.get("ID пользователя", "")) == str(user_id):
                    user_applications.append(record)
            
            return user_applications
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения заявок пользователя: {e}")
            return []

class EquipmentBot:
    def __init__(self):
        self.user_data = {}
        # Инициализация Google Sheets Manager с ID таблицы
        try:
            self.gsheets = GoogleSheetsManager(
                creds_file="credentials.json",  # Путь к вашему JSON-файлу
                spreadsheet_id=SPREADSHEET_ID  # Используем ID вместо названия
            )
            # Настройка листов при запуске
            self.gsheets.setup_sheets()
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Google Таблиц: {e}")
            self.gsheets = None

    def generate_application_number(self) -> str:
        """Генерация номера заявки"""
        return f"mc{datetime.now().strftime('%d%H%M%S')}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало диалога"""
        try:
            user = update.message.from_user
            logger.info(f"🔄 Пользователь {user.id} начал диалог")
            
            welcome_text = """
Привет! Это бот для бронирования съемочного оборудования в Студенческом Медиацентре.

⚠️ *ВАЖНО!*
Заявки принимаются минимум за 48 часов!
            """
            
            await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=ReplyKeyboardRemove())
            
            # Инициализация данных пользователя
            self.user_data[user.id] = {
                'app_number': self.generate_application_number(),
                'username': user.username or 'Не указан',
                'user_link': f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}",
                'full_name': '',
                'unit': '',
                'equipment': '',
                'dates': [],
                'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            logger.info(f"✅ Данные пользователя {user.id} инициализированы")
            
            await update.message.reply_text("Введите ваше ФИО:")
            return FIO
            
        except Exception as e:
            logger.error(f"💥 Ошибка в start: {e}")
            await update.message.reply_text("❌ Произошла ошибка. Пожалуйста, попробуйте снова /start")
            return ConversationHandler.END

    async def get_fio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение ФИО"""
        try:
            user = update.message.from_user
            user_text = update.message.text
            
            logger.info(f"🔄 Пользователь {user.id} ввел ФИО: {user_text}")
            
            if user.id not in self.user_data:
                logger.error(f"❌ Данные пользователя {user.id} не найдены!")
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            # Сохраняем ФИО
            self.user_data[user.id]['full_name'] = user_text
            logger.info(f"✅ ФИО сохранено: {user_text}")
            
            await update.message.reply_text("Укажите для чего вам необходимо оборудование:")
            return UNIT
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в get_fio: {e}")
            await update.message.reply_text("❌ Ошибка при сохранении ФИО. Попробуйте снова /start")
            return ConversationHandler.END

    async def get_unit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение цели использования"""
        try:
            user = update.message.from_user
            user_text = update.message.text
            
            logger.info(f"🔄 Пользователь {user.id} ввел цель: {user_text}")
            
            if user.id not in self.user_data:
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            self.user_data[user.id]['unit'] = user_text
            
            await update.message.reply_text(f"Введите список оборудования:\n\n{AVAILABLE_EQUIPMENT}")
            return EQUIPMENT
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в get_unit: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def get_equipment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение списка оборудования"""
        try:
            user = update.message.from_user
            user_text = update.message.text
            
            logger.info(f"🔄 Пользователь {user.id} ввел оборудование: {user_text}")
            
            if user.id not in self.user_data:
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            self.user_data[user.id]['equipment'] = user_text
            
            # Создаем клавиатуру для выбора дат
            keyboard = self._create_dates_keyboard()
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                "📅 *Выберите даты:*\n\nМожно выбрать несколько дат. Завершите выбор кнопкой ниже.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return DATES
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в get_equipment: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    def _create_dates_keyboard(self):
        """Создание клавиатуры для выбора дат"""
        try:
            today = datetime.now()
            dates_keyboard = []
            
            # Генерируем даты на 2 недели вперед
            for i in range(0, 14, 2):
                row = []
                for j in range(2):
                    if i + j < 14:
                        date = today + timedelta(days=i+j+2)
                        date_str = date.strftime("%d.%m (%a)")
                        row.append(f"📅 {date_str}")
                if row:
                    dates_keyboard.append(row)
            
            dates_keyboard.append(["✅ Завершить выбор", "🔄 Очистить"])
            dates_keyboard.append(["✏️ Ввести вручную"])
            return dates_keyboard
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в _create_dates_keyboard: {e}")
            return [["❌ Ошибка создания клавиатуры"]]

    async def get_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора дат"""
        try:
            user = update.message.from_user
            choice = update.message.text
            user_data = self.user_data[user.id]
            
            logger.info(f"🔄 Пользователь {user.id} выбрал: {choice}")
            
            if user.id not in self.user_data:
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            if choice == "✅ Завершить выбор":
                if not user_data['dates']:
                    await update.message.reply_text("❌ Вы не выбрали ни одной даты. Пожалуйста, выберите хотя бы одну дату.")
                    return DATES
                return await self.ask_for_time(update, context)
                
            elif choice == "🔄 Очистить":
                user_data['dates'] = []
                keyboard = self._create_dates_keyboard()
                await update.message.reply_text("✅ Выбор очищен:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
                return DATES
                
            elif choice == "✏️ Ввести вручную":
                await update.message.reply_text("Введите даты в формате: ДД.ММ.ГГГГ ЧЧ:ММ - ДД.ММ.ГГГГ ЧЧ:ММ", reply_markup=ReplyKeyboardRemove())
                return DATES
                
            else:
                # Обработка выбора даты
                selected_date = choice.replace("📅 ", "").strip()
                if selected_date not in user_data['dates']:
                    user_data['dates'].append(selected_date)
                
                dates_text = "\n".join([f"• {date}" for date in user_data['dates']])
                keyboard = self._create_dates_keyboard()
                
                await update.message.reply_text(
                    f"✅ Выбрано:\n{dates_text}\n\nПродолжайте выбор или завершите:",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return DATES
                
        except Exception as e:
            logger.error(f"💥 ОШИБКА в get_dates: {e}")
            await update.message.reply_text("❌ Ошибка выбора дат. Попробуйте снова /start")
            return ConversationHandler.END

    async def ask_for_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрос временного промежутка"""
        try:
            user = update.message.from_user
            user_data = self.user_data[user.id]
            
            time_keyboard = [
                ["🕘 09:00-13:00", "🕐 13:00-17:00", "🕔 17:00-21:00"],
                ["🌅 Утро 09-12", "🌞 День 12-18", "🌙 Вечер 18-21"],
                ["📆 Весь день 09-21", "✏️ Свое время"]
            ]
            
            dates_text = "\n".join([f"• {date}" for date in user_data['dates']])
            
            await update.message.reply_text(
                f"📅 Выбрано:\n{dates_text}\n\n⏰ Выберите время:",
                reply_markup=ReplyKeyboardMarkup(time_keyboard, resize_keyboard=True)
            )
            return TIME_SELECTION
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в ask_for_time: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def handle_time_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора времени"""
        try:
            user = update.message.from_user
            time_choice = update.message.text
            user_data = self.user_data[user.id]
            
            if user.id not in self.user_data:
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            time_mapping = {
                "🕘 09:00-13:00": "09:00-13:00",
                "🕐 13:00-17:00": "13:00-17:00", 
                "🕔 17:00-21:00": "17:00-21:00",
                "🌅 Утро 09-12": "09:00-12:00",
                "🌞 День 12-18": "12:00-18:00",
                "🌙 Вечер 18-21": "18:00-21:00",
                "📆 Весь день 09-21": "09:00-21:00"
            }
            
            if time_choice == "✏️ Свое время":
                await update.message.reply_text("Введите время в формате: ЧЧ:ММ-ЧЧ:ММ", reply_markup=ReplyKeyboardRemove())
                return TIME_SELECTION
                
            time_range = time_mapping.get(time_choice, time_choice)
            user_data['dates'] = [f"{date} {time_range}" for date in user_data['dates']]
            
            return await self.show_summary(update, context)
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в handle_time_selection: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def handle_manual_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка ручного ввода"""
        try:
            user = update.message.from_user
            user_data = self.user_data[user.id]
            user_data['dates'] = [update.message.text]
            return await self.show_summary(update, context)
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в handle_manual_input: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def show_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показ сводки заявки"""
        try:
            user = update.message.from_user
            data = self.user_data[user.id]
            
            dates_display = "\n".join([f"• {date}" for date in data['dates']])
            summary = f"""
📋 Заявка #{data['app_number']}

👤 ФИО: {data['full_name']}
🎯 Цель: {data['unit']}
📹 Оборудование: {data['equipment']}
📅 Даты:\n{dates_display}
            """
            
            keyboard = [["✅ Подтвердить", "✏️ Редактировать"]]
            await update.message.reply_text(summary, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return CONFIRMATION
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в show_summary: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка подтверждения"""
        try:
            user = update.message.from_user
            choice = update.message.text
            
            logger.info(f"🔄 Пользователь {user.id} подтверждает заявку: {choice}")
            
            if user.id not in self.user_data:
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            if choice == "✅ Подтвердить":
                user_data = self.user_data[user.id]
                
                # Сохраняем в Google Таблицы
                if self.gsheets:
                    try:
                        # Подготавливаем данные для таблицы
                        application_data = {
                            "app_number": user_data['app_number'],
                            "created_at": user_data['created_at'],
                            "user_id": user.id,
                            "full_name": user_data['full_name'],
                            "username": user_data['username'],
                            "user_link": user_data['user_link'],
                            "unit": user_data['unit'],
                            "equipment": user_data['equipment'],
                            "dates_display": "\n".join([f"• {date}" for date in user_data['dates']])
                        }
                        
                        # Добавляем заявку и обновляем пользователя
                        self.gsheets.add_application(application_data)
                        self.gsheets.update_user({
                            "user_id": user.id,
                            "full_name": user_data['full_name'],
                            "username": user_data['username']
                        })
                        
                        logger.info(f"✅ Данные заявки {user_data['app_number']} сохранены в Google Таблицы")
                        
                    except Exception as e:
                        logger.error(f"❌ Ошибка сохранения в Google Таблицы: {e}")
                
                # Отправляем уведомления администраторам
                await self.send_admin_notifications(user_data, context.bot)
                
                # Показываем успех пользователю
                keyboard = [["📝 Новая заявка"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                success_message = f"✅ Заявка #{user_data['app_number']} принята! С вами свяжутся."
                if not self.gsheets:
                    success_message += "\n\n⚠️ Данные не сохранены в систему. Сообщите администратору."
                
                await update.message.reply_text(success_message, reply_markup=reply_markup)
                
                # Очищаем данные
                del self.user_data[user.id]
                return ConversationHandler.END
                
            else:
                keyboard = [
                    ["👤 ФИО", "🎯 Цель"],
                    ["📹 Оборудование", "📅 Даты"],
                    ["🔙 Назад"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await update.message.reply_text("Что редактируем?", reply_markup=reply_markup)
                return CONFIRMATION
                
        except Exception as e:
            logger.error(f"💥 ОШИБКА в handle_confirmation: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def send_admin_notifications(self, user_data: dict, bot):
        """Отправка уведомлений администраторам"""
        try:
            dates_display = "\n".join([f"• {date}" for date in user_data['dates']])
            notification = f"""
🚨 *НОВАЯ ЗАЯВКА*

📋 #{user_data['app_number']}
👤 {user_data['full_name']}
🎯 {user_data['unit']}
📹 {user_data['equipment']}
📅 Даты:\n{dates_display}
👤 @{user_data['username']}
🔗 {user_data['user_link']}

{'✅ Сохранено в Google Таблицы' if self.gsheets else '⚠️ НЕ сохранено в таблицы!'}
            """
            
            for admin_id in ADMIN_CHAT_IDS:
                try:
                    await bot.send_message(chat_id=admin_id, text=notification, parse_mode='Markdown')
                    logger.info(f"✅ Уведомление отправлено admin_{admin_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки admin_{admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"💥 Ошибка уведомлений: {e}")

    async def handle_edit_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка редактирования"""
        try:
            user = update.message.from_user
            choice = update.message.text
            
            if user.id not in self.user_data:
                await update.message.reply_text("❌ Сессия устарела. Пожалуйста, начните заново /start")
                return ConversationHandler.END
            
            if choice == "👤 ФИО":
                await update.message.reply_text("Введите ФИО:")
                return FIO
            elif choice == "🎯 Цель":
                await update.message.reply_text("Укажите для чего нужно оборудование:")
                return UNIT
            elif choice == "📹 Оборудование":
                await update.message.reply_text(f"Введите оборудование:\n\n{AVAILABLE_EQUIPMENT}")
                return EQUIPMENT
            elif choice == "📅 Даты":
                self.user_data[user.id]['dates'] = []
                keyboard = self._create_dates_keyboard()
                await update.message.reply_text("Выберите даты:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
                return DATES
            else:
                return await self.show_summary(update, context)
                
        except Exception as e:
            logger.error(f"💥 ОШИБКА в handle_edit_choice: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте снова /start")
            return ConversationHandler.END

    async def new_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Новая заявка"""
        return await self.start(update, context)

    async def my_applications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю заявок пользователя"""
        if not self.gsheets:
            await update.message.reply_text("❌ Система хранения данных временно недоступна.")
            return
            
        user_id = update.effective_user.id
        applications = self.gsheets.get_user_applications(user_id)
        
        if not applications:
            await update.message.reply_text("📭 У вас еще нет заявок.")
            return
        
        message = "📋 Ваши последние заявки:\n\n"
        for app in applications[:5]:  # Показываем последние 5 заявок
            message += (
                f"Заявка #{app.get('Номер заявки', '')}\n"
                f"Статус: {app.get('Статус', '')}\n"
                f"Оборудование: {app.get('Оборудование', '')[:50]}...\n"
                f"Дата: {app.get('Дата создания', '')}\n"
                f"——————————————\n"
            )
        
        await update.message.reply_text(message)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена"""
        try:
            user = update.message.from_user
            if user.id in self.user_data:
                del self.user_data[user.id]
            
            keyboard = [["📝 Новая заявка"]]
            await update.message.reply_text('Диалог прерван.', reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return ConversationHandler.END
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА в cancel: {e}")
            await update.message.reply_text("❌ Ошибка. Используйте /start")
            return ConversationHandler.END

def main():
    try:
        BOT_TOKEN = os.getenv('BOT_TOKEN')
        if not BOT_TOKEN:
            logger.error("❌ BOT_TOKEN не найден!")
            return

        bot = EquipmentBot()
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Обработчики
        application.add_handler(MessageHandler(filters.Regex("^📝 Новая заявка$"), bot.new_request))
        application.add_handler(CommandHandler("myapps", bot.my_applications))
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', bot.start)],
            states={
                FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_fio)],
                UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_unit)],
                EQUIPMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_equipment)],
                DATES: [
                    MessageHandler(filters.Regex("^(✅ Завершить выбор|🔄 Очистить|✏️ Ввести вручную)$"), bot.get_dates),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_dates)
                ],
                TIME_SELECTION: [
                    MessageHandler(filters.Regex("^✏️ Свое время$"), bot.handle_time_selection),
                    MessageHandler(filters.Regex("^(🕘 |🕐 |🕔 |🌅 |🌞 |🌙 |📆 )"), bot.handle_time_selection),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_manual_input)
                ],
                CONFIRMATION: [
                    MessageHandler(filters.Regex("^(✅ Подтвердить|✏️ Редактировать)$"), bot.handle_confirmation),
                    MessageHandler(filters.Regex("^(👤 ФИО|🎯 Цель|📹 Оборудование|📅 Даты|🔙 Назад)$"), bot.handle_edit_choice)
                ],
            },
            fallbacks=[CommandHandler('cancel', bot.cancel)]
        )
        
        application.add_handler(conv_handler)
        
        logger.info("🎉 Бот запущен!")
        application.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА в main: {e}")
        logger.info("🔄 Перезапуск через 10 секунд...")
        import time
        time.sleep(10)
        main()

if __name__ == '__main__':
    main()
