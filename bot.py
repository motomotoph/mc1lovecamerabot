import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, ConversationHandler
)
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

# ID твоего телеграм аккаунта для уведомлений (замени на свой)
ADMIN_CHAT_ID = "730691574"  # ← ЗАМЕНИ НА СВОЙ TELEGRAM ID

class EquipmentBot:
    def __init__(self):
        self.user_data = {}
        self.sheet = None
        self.setup_google_sheets()
        
    def setup_google_sheets(self):
        """Упрощенное подключение к Google Sheets с правильными scopes"""
        try:
            logger.info("🔄 Попытка подключения к Google Sheets...")
            
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            
            if not creds_json:
                logger.error("❌ GOOGLE_CREDENTIALS не найдены!")
                return
                
            logger.info("✅ Переменные окружения найдены")
            
            # Импортируем библиотеки
            import gspread
            from google.oauth2.service_account import Credentials
            import json
            
            # Загружаем credentials
            creds_dict = json.loads(creds_json)
            
            # 🔥 ПРАВИЛЬНЫЕ SCOPES - только для Sheets!
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive.file'
            ]
            
            # Создаем credentials
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            # 🔥 ПРОБУЕМ ОТКРЫТЬ ТАБЛИЦУ ПО ID
            try:
                # ВСТАВЬ СЮДА СВОЙ ID ТАБЛИЦЫ!
                sheet_id = "1IhI_3WR2y8iBLQa9X_-0Vjn0RGnuTVpghNSurkmnlRk"  # ← ЗАМЕНИ НА СВОЙ ID
                self.sheet = client.open_by_key(sheet_id).sheet1
                logger.info("🎉 УСПЕХ: Таблица найдена по ID!")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при открытии таблицы по ID: {e}")
                
            # Проверяем подключение
            if self.sheet:
                try:
                    # Пробуем прочитать первую ячейку
                    test_value = self.sheet.acell('A1').value
                    logger.info(f"✅ Тест подключения успешен! A1 = '{test_value}'")
                except Exception as e:
                    logger.error(f"❌ Ошибка при тесте таблицы: {e}")
                    self.sheet = None
                    
        except Exception as e:
            logger.error(f"💥 ОШИБКА подключения: {str(e)}")
            self.sheet = None

    def generate_application_number(self) -> str:
        """Генерация номера заявки"""
        try:
            if not self.sheet:
                return "mc00001"
                
            # Получаем все записи
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
            return "mc00001"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало диалога с приветственным сообщением"""
        user = update.message.from_user
        
        # Приветственное сообщение с важной информацией
        welcome_text = """
Привет! Это бот с помощью которого ты можешь забронировать съемочное оборудование в Студенческом Медиацентре.

⚠️ *ВАЖНО!*
Заявки которые отправляются меньше чем за 48 часов рассматриваться не будут!!!
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Создаем новую заявку
        app_number = self.generate_application_number()
        user_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        
        self.user_data[user.id] = {
            'app_number': app_number,
            'username': user.username or 'Не указан',
            'user_link': user_link,
            'full_name': '',
            'unit': '',
            'equipment': '',
            'dates': [],
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        await update.message.reply_text(
            "Введите ваше ФИО:",
            reply_markup=ReplyKeyboardRemove()
        )
        return FIO

    async def get_fio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение ФИО"""
        user = update.message.from_user
        self.user_data[user.id]['full_name'] = update.message.text
        
        await update.message.reply_text("Укажите вашу структурную единицу или название проекта/мероприятия:")
        return UNIT

    async def get_unit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение структурной единицы"""
        user = update.message.from_user
        self.user_data[user.id]['unit'] = update.message.text
        
        await update.message.reply_text(
            f"Введите список необходимого оборудования:\n\n{AVAILABLE_EQUIPMENT}"
        )
        return EQUIPMENT

    async def get_equipment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение списка оборудования"""
        user = update.message.from_user
        self.user_data[user.id]['equipment'] = update.message.text
        
        # Создаем клавиатуру для выбора дат
        keyboard = self._create_dates_keyboard()
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
        
        await update.message.reply_text(
            "📅 *Выберите даты бронирования:*\n\n"
            "Можно выбрать несколько дат - просто нажимайте на нужные даты.\n"
            "Когда закончите, нажмите '✅ Завершить выбор дат'",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return DATES

    def _create_dates_keyboard(self):
        """Создание клавиатуры для выбора дат"""
        # Генерируем даты на 2 недели вперед
        today = datetime.now()
        dates_keyboard = []
        row = []
        
        for i in range(14):
            date = today + timedelta(days=i+2)  # +2 дня потому что за 48 часов
            date_str = date.strftime("%d.%m.%Y")
            day_name = date.strftime("%a")
            button_text = f"📅 {date_str} ({day_name})"
            
            row.append(button_text)
            
            # Создаем ряды по 2 кнопки (больше места)
            if len(row) == 2:
                dates_keyboard.append(row)
                row = []
        
        # Добавляем последний ряд если он не пустой
        if row:
            dates_keyboard.append(row)
            
        # Добавляем кнопки управления
        dates_keyboard.append(["✅ Завершить выбор дат", "🔄 Очистить выбор"])
        dates_keyboard.append(["✏️ Ввести даты вручную"])
        
        return dates_keyboard

    async def get_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора дат"""
        user = update.message.from_user
        choice = update.message.text
        
        if choice == "✅ Завершить выбор дат":
            # Проверяем, что выбрана хотя бы одна дата
            if not self.user_data[user.id]['dates']:
                await update.message.reply_text(
                    "❌ Вы не выбрали ни одной даты. Пожалуйста, выберите хотя бы одну дату."
                )
                return DATES
            
            # Переходим к выбору времени
            return await self.ask_for_time(update, context)
            
        elif choice == "🔄 Очистить выбор":
            # Очищаем выбранные даты
            self.user_data[user.id]['dates'] = []
            keyboard = self._create_dates_keyboard()
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
            
            await update.message.reply_text(
                "✅ Выбор дат очищен. Выберите даты заново:",
                reply_markup=reply_markup
            )
            return DATES            
        elif choice == "✏️ Ввести даты вручную":
            await update.message.reply_text(
                "Введите даты в формате: ДД.ММ.ГГГГ ЧЧ:ММ - ДД.ММ.ГГГГ ЧЧ:ММ\n\n"
                "Пример: 15.12.2024 10:00 - 16.12.2024 18:00\n"
                "Или несколько периодов через запятую:\n"
                "15.12.2024 10:00-13:00, 16.12.2024 14:00-18:00",
                reply_markup=ReplyKeyboardRemove()
            )
            return DATES
        else:
            # Обрабатываем выбор даты из кнопок
            selected_date = choice.replace("📅 ", "").split(" (")[0].strip()
            
            # Добавляем дату в список (если еще нет)
            if selected_date not in self.user_data[user.id]['dates']:
                self.user_data[user.id]['dates'].append(selected_date)
            
            # Показываем текущий выбор
            selected_dates = self.user_data[user.id]['dates']
            dates_text = "\n".join([f"• {date}" for date in selected_dates])
            
            keyboard = self._create_dates_keyboard()
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
            
            await update.message.reply_text(
                f"✅ Выбранные даты:\n{dates_text}\n\n"
                f"Продолжайте выбирать даты или нажмите '✅ Завершить выбор дат'",
                reply_markup=reply_markup
            )
            return DATES

    async def ask_for_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрос временного промежутка"""
        user = update.message.from_user
        
        # Предлагаем выбрать временной промежуток
        time_keyboard = [
            ["🕘 09:00 - 13:00", "🕐 13:00 - 17:00", "🕔 17:00 - 21:00"],
            ["🌅 Утро (09:00 - 12:00)", "🌞 День (12:00 - 18:00)"],
            ["🌙 Вечер (18:00 - 21:00)", "📆 Полный день (09:00 - 21:00)"],
            ["✏️ Указать свое время"]
        ]
        reply_markup = ReplyKeyboardMarkup(time_keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        selected_dates = self.user_data[user.id]['dates']
        dates_text = "\n".join([f"• {date}" for date in selected_dates])
        
        await update.message.reply_text(
            f"📅 Выбранные даты:\n{dates_text}\n\n"
            "⏰ Теперь выберите временной промежуток (будет применен ко всем выбранным датам):",
            reply_markup=reply_markup
        )
        return TIME_SELECTION

    async def handle_time_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора времени"""
        user = update.message.from_user
        time_choice = update.message.text
        
        if time_choice == "✏️ Указать свое время":
            await update.message.reply_text(
                "Введите время в формате: ЧЧ:ММ - ЧЧ:ММ\n\n"
                "Пример: 10:00 - 18:00\n"
                "Это время будет применено ко всем выбранным датам.",
                reply_markup=ReplyKeyboardRemove()
            )
            return TIME_SELECTION
        else:
            # Формируем полные строки с датами и временем
            time_mapping = {
                "🕘 09:00 - 13:00": "09:00-13:00",
                "🕐 13:00 - 17:00": "13:00-17:00", 
                "🕔 17:00 - 21:00": "17:00-21:00",
                "🌅 Утро (09:00 - 12:00)": "09:00-12:00",
                "🌞 День (12:00 - 18:00)": "12:00-18:00",
                "🌙 Вечер (18:00 - 21:00)": "18:00-21:00",
                "📆 Полный день (09:00 - 21:00)": "09:00-21:00"
            }
            
            time_range = time_mapping.get(time_choice, time_choice.replace(" - ", "-"))
            
            # Создаем список дат с временем
            dates_with_time = []
            for date in self.user_data[user.id]['dates']:
                dates_with_time.append(f"{date} {time_range}")
            
            self.user_data[user.id]['dates'] = dates_with_time
            
            # Показываем сводку
            return await self.show_summary(update, context)

    async def handle_manual_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка ручного ввода времени"""
        user = update.message.from_user
        time_range = update.message.text.replace(" - ", "-")
        
        # Создаем список дат с временем
        dates_with_time = []
        for date in self.user_data[user.id]['dates']:
            dates_with_time.append(f"{date} {time_range}")
        
        self.user_data[user.id]['dates'] = dates_with_time
        
        # Показываем сводку
        return await self.show_summary(update, context)

    async def handle_manual_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка ручного ввода дат"""
        user = update.message.from_user
        dates_text = update.message.text
        
        # Сохраняем как список с одним элементом (ручной ввод)
        self.user_data[user.id]['dates'] = [dates_text]
        
        # Показываем сводку
        return await self.show_summary(update, context)

    async def show_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показ сводки заявки"""
        user = update.message.from_user
        data = self.user_data[user.id]
        
        # Форматируем даты для отображения
        if isinstance(data['dates'], list):
            dates_display = "\n".join([f"• {date}" for date in data['dates']])
        else:
            dates_display = data['dates']
        
        summary = f"""
📋 Сводка заявки #{data['app_number']}

👤 ФИО: {data['full_name']}
🏢 Структурная единица/Проект: {data['unit']}
📹 Оборудование: {data['equipment']}
📅 Даты и время:\n{dates_display}
⏰ Создано: {data['created_at']}
        """
        
        keyboard = [["✅ Подтвердить", "✏️ Редактировать"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(summary, reply_markup=reply_markup)
        return CONFIRMATION

    async def save_to_google_sheets(self, user_id: int) -> bool:
        """Сохранение заявки в Google Sheets"""
        try:
            if not self.sheet:
                logger.error("❌ Google Sheets не доступен")
                return False
                
            data = self.user_data[user_id]
            
            # Форматируем даты для сохранения
            if isinstance(data['dates'], list):
                dates_for_sheet = ", ".join(data['dates'])
            else:
                dates_for_sheet = data['dates']
            
            # Подготавливаем данные
            row = [
                data['app_number'],
                data['created_at'], 
                data['full_name'],
                data['unit'],
                data['equipment'],
                dates_for_sheet,  # Сохраняем отформатированные даты
                data['username'],
                data['user_link']
            ]
            
            # Добавляем строку
            self.sheet.append_row(row)
            logger.info(f"✅ Заявка {data['app_number']} сохранена!")
            return True
            
        except Exception as e:
            logger.error(f"💥 ОШИБКА сохранения: {str(e)}")
            return False

    async def send_admin_notification(self, user_data: dict):
        """Отправка уведомления администратору"""
        try:
            # Форматируем даты для уведомления
            if isinstance(user_data['dates'], list):
                dates_display = "\n".join([f"• {date}" for date in user_data['dates']])
            else:
                dates_display = user_data['dates']
            
            notification = f"""
🚨 *НОВАЯ ЗАЯВКА НА ОБОРУДОВАНИЕ*

📋 Номер: #{user_data['app_number']}
👤 ФИО: {user_data['full_name']}
🏢 Проект: {user_data['unit']}
📹 Оборудование: {user_data['equipment']}
📅 Даты:\n{dates_display}
👤 Username: @{user_data['username']}
🔗 Ссылка: {user_data['user_link']}
⏰ Время заявки: {user_data['created_at']}
            """
            
            # Отправляем уведомление администратору
            from telegram.constants import ParseMode
            application = Application.builder().token(os.getenv('BOT_TOKEN')).build()
            
            await application.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=notification,
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"✅ Уведомление отправлено администратору")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка подтверждения с кнопкой новой заявки"""
        user = update.message.from_user
        choice = update.message.text
        
        if choice == "✅ Подтвердить":
            # Сохраняем в Google Sheets
            success = await self.save_to_google_sheets(user.id)
            
            if success:
                app_number = self.user_data[user.id]['app_number']
                
                # Отправляем уведомление администратору
                await self.send_admin_notification(self.user_data[user.id])
                
                # Клавиатура с кнопкой новой заявки
                new_request_keyboard = [["📝 Новая заявка"]]
                reply_markup = ReplyKeyboardMarkup(new_request_keyboard, one_time_keyboard=True, resize_keyboard=True)
                
                await update.message.reply_text(
                    f"✅ Ваша заявка #{app_number} принята! С вами скоро свяжутся.",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    "❌ Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте позже.",
                    reply_markup=ReplyKeyboardRemove()
                )
            
            # Очищаем данные
            if user.id in self.user_data:
                del self.user_data[user.id]
            return ConversationHandler.END
            
        else:  # Редактирование
            keyboard = [
                ["👤 ФИО", "🏢 Структурная единица"],
                ["📹 Оборудование", "📅 Даты"],
                ["🔙 Назад к сводке"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text("Выберите что хотите отредактировать:", reply_markup=reply_markup)
            return CONFIRMATION

    async def handle_edit_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора поля для редактирования"""
        user = update.message.from_user
        choice = update.message.text
        
        if choice == "👤 ФИО":
            await update.message.reply_text("Введите ваше ФИО:")
            return FIO
        elif choice == "🏢 Структурная единица":
            await update.message.reply_text("Укажите вашу структурную единицу:")
            return UNIT
        elif choice == "📹 Оборудование":
            await update.message.reply_text(f"Введите список оборудования:\n\n{AVAILABLE_EQUIPMENT}")
            return EQUIPMENT
        elif choice == "📅 Даты":
            # Сбрасываем выбранные даты
            self.user_data[user.id]['dates'] = []
            keyboard = self._create_dates_keyboard()
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=False, resize_keyboard=True)
            await update.message.reply_text("Выберите даты бронирования:", reply_markup=reply_markup)
            return DATES
        elif choice == "🔙 Назад к сводке":
            return await self.show_summary(update, context)

    async def new_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка кнопки новой заявки"""
        return await self.start(update, context)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена диалога"""
        user = update.message.from_user
        if user.id in self.user_data:
            del self.user_data[user.id]
        
        # Клавиатура с кнопкой новой заявки
        new_request_keyboard = [["📝 Новая заявка"]]
        reply_markup = ReplyKeyboardMarkup(new_request_keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            'Диалог прерван. Для новой заявки нажмите кнопку ниже или отправьте /start',
            reply_markup=reply_markup
        )
        return ConversationHandler.END

def main():
    # Проверяем переменные
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    GOOGLE_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS')
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return
        
    if not GOOGLE_CREDENTIALS:
        logger.error("❌ GOOGLE_CREDENTIALS не найдены!")
    
    logger.info("🤖 Запуск бота...")
    
    bot = EquipmentBot()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчик для кнопки "Новая заявка"
    application.add_handler(MessageHandler(filters.Regex("^📝 Новая заявка$"), bot.new_request))
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_fio)],
            UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_unit)],
            EQUIPMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_equipment)],
            DATES: [
                MessageHandler(filters.Regex("^(✅ Завершить выбор дат|🔄 Очистить выбор|✏️ Ввести даты вручную)$"), bot.get_dates),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_dates)
            ],
            TIME_SELECTION: [
                MessageHandler(filters.Regex("^(✏️ Указать свое время)$"), bot.handle_time_selection),
                MessageHandler(filters.Regex("^(🕘 |🕐 |🕔 |🌅 |🌞 |🌙 |📆 )"), bot.handle_time_selection),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_manual_time)
            ],
            CONFIRMATION: [
                MessageHandler(filters.Regex("^(✅ Подтвердить|✏️ Редактировать)$"), bot.handle_confirmation),
                MessageHandler(filters.Regex("^(👤 ФИО|🏢 Структурная единица|📹 Оборудование|📅 Даты|🔙 Назад к сводке)$"), bot.handle_edit_choice)
            ],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Запускаем бота
    logger.info("🎉 Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()

