import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора
FIO, UNIT, EQUIPMENT, DATES, TIME_SELECTION, CONFIRMATION = range(6)

# ID администраторов для уведомлений (замени на реальные)
ADMIN_CHAT_IDS = [730691574, 2114604500]  # ← ЗАМЕНИ НА РЕАЛЬНЫЕ ID

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

class EquipmentBot:
    def __init__(self):
        self.user_data = {}
        self.sheet = None
        self.setup_google_sheets()
        
    def setup_google_sheets(self):
        """Подключение к Google Sheets"""
        try:
            logger.info("🔄 Подключение к Google Sheets...")
            
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            if not creds_json:
                logger.error("❌ GOOGLE_CREDENTIALS не найдены!")
                return
                
            # Загружаем credentials
            creds_dict = json.loads(creds_json)
            scope = ['https://www.googleapis.com/auth/spreadsheets']
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            # Открываем таблицу по ID
            sheet_id = "1IhI_3WR2y8iBLQa9X_-0Vjn0RGnuTVpghNSurkmnlRk"  # ← ЗАМЕНИ НА СВОЙ ID
            self.sheet = client.open_by_key(sheet_id).sheet1
            
            logger.info("✅ Google Sheets подключен!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            self.sheet = None

    def generate_application_number(self) -> str:
        """Генерация номера заявки"""
        try:
            if not self.sheet:
                return f"mc{datetime.now().strftime('%d%H%M%S')}"
                
            # Получаем существующие заявки для генерации номера
            records = self.sheet.get_all_records()
            max_number = 0
            
            for record in records:
                values = list(record.values())
                if values:
                    app_number = values[0]
                    if isinstance(app_number, str) and app_number.startswith('mc'):
                        try:
                            current_num = int(app_number[2:])
                            max_number = max(max_number, current_num)
                        except ValueError:
                            continue
            
            return f"mc{max_number + 1:05d}"
            
        except Exception as e:
            logger.error(f"Ошибка генерации номера: {e}")
            return f"mc{datetime.now().strftime('%d%H%M%S')}"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало диалога"""
        user = update.message.from_user
        
        welcome_text = """
Привет! Это бот для бронирования съемочного оборудования в Студенческом Медиацентре.

⚠️ *ВАЖНО!*
Заявки принимаются минимум за 48 часов!
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        
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
        
        await update.message.reply_text("Введите ваше ФИО:")
        return FIO

    async def get_fio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение ФИО"""
        user = update.message.from_user
        user_text = update.message.text.strip()
        
        # Простая проверка
        if not user_text or len(user_text) < 2:
            await update.message.reply_text("❌ Пожалуйста, введите ваше ФИО:")
            return FIO
        
        # Сохраняем
        self.user_data[user.id]['full_name'] = user_text
        
        await update.message.reply_text("Укажите для чего вам необходимо оборудование:")
        return UNIT

    async def get_unit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение цели использования"""
        user = update.message.from_user
        self.user_data[user.id]['unit'] = update.message.text
        await update.message.reply_text(f"Введите список оборудования:\n\n{AVAILABLE_EQUIPMENT}")
        return EQUIPMENT

    async def get_equipment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение списка оборудования"""
        user = update.message.from_user
        self.user_data[user.id]['equipment'] = update.message.text
        
        keyboard = self._create_dates_keyboard()
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "📅 *Выберите даты:*\n\nМожно выбрать несколько дат. Завершите выбор кнопкой ниже.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return DATES

    def _create_dates_keyboard(self):
        """Создание клавиатуры для выбора дат"""
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

    async def get_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора дат"""
        user = update.message.from_user
        choice = update.message.text
        user_data = self.user_data[user.id]
        
        if choice == "✅ Завершить выбор":
            if not user_data['dates']:
                await update.message.reply_text("❌ Выберите хотя бы одну дату.")
                return DATES
            return await self.ask_for_time(update, context)
            
        elif choice == "🔄 Очистить":
            user_data['dates'] = []
            keyboard = self._create_dates_keyboard()
            await update.message.reply_text("✅ Выбор очищен:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return DATES
            
        elif choice == "✏️ Ввести вручную":
            await update.message.reply_text("Введите даты в формате: ДД.ММ.ГГГГ ЧЧ:ММ - ДД.ММ.ГГГГ ЧЧ:ММ")
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

    async def ask_for_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрос временного промежутка"""
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

    async def handle_time_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора времени"""
        user = update.message.from_user
        time_choice = update.message.text
        user_data = self.user_data[user.id]
        
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
            await update.message.reply_text("Введите время в формате: ЧЧ:ММ-ЧЧ:ММ")
            return TIME_SELECTION
            
        time_range = time_mapping.get(time_choice, time_choice)
        user_data['dates'] = [f"{date} {time_range}" for date in user_data['dates']]
        
        return await self.show_summary(update, context)

    async def handle_manual_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка ручного ввода"""
        user = update.message.from_user
        user_data = self.user_data[user.id]
        user_data['dates'] = [update.message.text]
        return await self.show_summary(update, context)

    async def show_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показ сводки заявки"""
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

    async def save_to_google_sheets(self, user_data: dict) -> bool:
        """Сохранение заявки в Google Sheets"""
        try:
            if not self.sheet:
                logger.error("❌ Google Sheets не доступен")
                return False
                
            # Форматируем даты для сохранения
            if isinstance(user_data['dates'], list):
                dates_for_sheet = ", ".join(user_data['dates'])
            else:
                dates_for_sheet = user_data['dates']
            
            # Подготавливаем данные
            row = [
                user_data['app_number'],
                user_data['created_at'], 
                user_data['full_name'],
                user_data['unit'],
                user_data['equipment'],
                dates_for_sheet,
                user_data['username'],
                user_data['user_link']
            ]
            
            # Добавляем строку
            self.sheet.append_row(row)
            logger.info(f"✅ Заявка {user_data['app_number']} сохранена в Google Sheets!")
            return True
            
        except Exception as e:
            logger.error(f"💥 Ошибка сохранения в Google Sheets: {str(e)}")
            return False

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
            """
            
            for admin_id in ADMIN_CHAT_IDS:
                try:
                    await bot.send_message(chat_id=admin_id, text=notification, parse_mode='Markdown')
                    logger.info(f"✅ Уведомление отправлено admin_{admin_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки admin_{admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"💥 Ошибка уведомлений: {e}")

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка подтверждения"""
        user = update.message.from_user
        choice = update.message.text
        
        if choice == "✅ Подтвердить":
            user_data = self.user_data[user.id]
            
            # Сохраняем в Google Sheets
            sheets_success = await self.save_to_google_sheets(user_data)
            
            # Отправляем уведомления администраторам
            await self.send_admin_notifications(user_data, context.bot)
            
            # Показываем успех пользователю
            keyboard = [["📝 Новая заявка"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            success_message = f"✅ Заявка #{user_data['app_number']} принята! С вами свяжутся."
            if sheets_success:
                success_message += "\n\n📊 Заявка сохранена в системе"
            
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

    async def handle_edit_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка редактирования"""
        user = update.message.from_user
        choice = update.message.text
        
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

    async def new_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Новая заявка"""
        return await self.start(update, context)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена"""
        user = update.message.from_user
        if user.id in self.user_data:
            del self.user_data[user.id]
        
        keyboard = [["📝 Новая заявка"]]
        await update.message.reply_text('Диалог прерван.', reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return ConversationHandler.END

def main():
    MAX_RETRIES = 3
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            BOT_TOKEN = os.getenv('BOT_TOKEN')
            if not BOT_TOKEN:
                logger.error("❌ BOT_TOKEN не найден!")
                return

            bot = EquipmentBot()
            application = Application.builder().token(BOT_TOKEN).build()
            
            # Обработчики
            application.add_handler(MessageHandler(filters.Regex("^📝 Новая заявка$"), bot.new_request))
            
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
            
            logger.info(f"🎉 Бот запущен (попытка {retry_count + 1}/{MAX_RETRIES})!")
            application.run_polling(drop_pending_updates=True)
            break
            
        except Exception as e:
            retry_count += 1
            wait_time = 10 * retry_count
            
            if "Conflict" in str(e):
                logger.error(f"❌ Конфликт (попытка {retry_count}/{MAX_RETRIES}): {e}")
            else:
                logger.error(f"💥 Ошибка (попытка {retry_count}/{MAX_RETRIES}): {e}")
            
            if retry_count < MAX_RETRIES:
                logger.info(f"🔄 Перезапуск через {wait_time} секунд...")
                import time
                time.sleep(wait_time)
            else:
                logger.error("🚨 Достигнут лимит попыток перезапуска. Бот остановлен.")
                break

if __name__ == '__main__':
    main()
