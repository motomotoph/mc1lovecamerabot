import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, ConversationHandler
)
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния разговора
FIO, UNIT, EQUIPMENT, DATES, CONFIRMATION = range(5)

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
        self.setup_google_sheets()
        
    def setup_google_sheets(self):
        """Настройка подключения к Google Sheets"""
        try:
            # Используем переменные окружения Render
            creds_json = os.getenv('GOOGLE_CREDENTIALS')
            if creds_json:
                import json
                creds_dict = json.loads(creds_json)
                creds = Credentials.from_service_account_info(creds_dict)
            else:
                # Для локальной разработки
                scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
                creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
            
            self.gc = gspread.authorize(creds)
            self.sheet = self.gc.open("Заявки на оборудование").sheet1
            logger.info("Успешно подключились к Google Sheets")
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}")
            self.sheet = None

    def generate_application_number(self) -> str:
        """Генерация номера заявки формата mc00000"""
        try:
            if not self.sheet:
                return "mc00001"
                
            # Получаем все существующие заявки
            records = self.sheet.get_all_records()
            
            if not records:
                return "mc00001"
            
            # Ищем максимальный номер
            max_number = 0
            for record in records:
                # Предполагаем, что номер заявки в первом столбце
                app_number = list(record.values())[0] if record else ""
                if isinstance(app_number, str) and app_number.startswith('mc'):
                    try:
                        current_num = int(app_number[2:])
                        max_number = max(max_number, current_num)
                    except ValueError:
                        continue
            
            next_number = max_number + 1
            return f"mc{next_number:05d}"  # Формат mc00000
            
        except Exception as e:
            logger.error(f"Ошибка генерации номера заявки: {e}")
            return "mc00001"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало диалога"""
        user = update.message.from_user
        
        # Генерируем номер заявки
        app_number = self.generate_application_number()
        
        # Создаем ссылку на пользователя
        user_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        
        self.user_data[user.id] = {
            'app_number': app_number,  # ✅ Добавляем номер заявки
            'username': user.username or 'Не указан',
            'user_link': user_link,
            'full_name': '',
            'unit': '',
            'equipment': '',
            'dates': '',
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        await update.message.reply_text(
            "Добро пожаловать в систему заявок на съемочное оборудование! 🎬\n\n"
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
        
        await update.message.reply_text(
            "Укажите даты и временные промежутки, когда необходимо оборудование:\n\n"
            "Пример: 15.12.2024 10:00 - 16.12.2024 18:00"
        )
        return DATES

    async def get_dates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение дат и показ сводки"""
        user = update.message.from_user
        self.user_data[user.id]['dates'] = update.message.text
        
        summary = self._create_summary(user.id)
        keyboard = [["✅ Подтвердить", "✏️ Редактировать"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(summary, reply_markup=reply_markup)
        return CONFIRMATION

    def _create_summary(self, user_id: int) -> str:
        """Создание сводки заявки"""
        data = self.user_data[user_id]
        return f"""
📋 Сводка заявки #{data['app_number']}

👤 ФИО: {data['full_name']}
🏢 Структурная единица/Проект: {data['unit']}
📹 Оборудование: {data['equipment']}
📅 Даты и время: {data['dates']}
⏰ Создано: {data['created_at']}
        """

    async def save_to_google_sheets(self, user_id: int) -> bool:
        """Сохранение заявки в Google Sheets"""
        try:
            if not self.sheet:
                logger.error("Google Sheets не настроен")
                return False
                
            data = self.user_data[user_id]
            
            # Подготавливаем данные для таблицы
            row = [
                data['app_number'],           # ✅ Номер заявки (ПЕРВЫЙ СТОЛБЕЦ!)
                data['created_at'],           # Дата создания
                data['full_name'],           # ФИО
                data['unit'],                # Проект/Отдел
                data['equipment'],           # Оборудование
                data['dates'],               # Даты
                data['username'],            # Username
                data['user_link']            # Ссылка на пользователя
            ]
            
            # Добавляем строку в таблицу
            self.sheet.append_row(row)
            logger.info(f"Заявка {data['app_number']} сохранена в Google Sheets")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения в Google Sheets: {e}")
            return False

    async def handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка подтверждения"""
        user = update.message.from_user
        choice = update.message.text
        
        if choice == "✅ Подтвердить":
            # Сохраняем в Google Sheets
            success = await self.save_to_google_sheets(user.id)
            
            if success:
                app_number = self.user_data[user.id]['app_number']
                await update.message.reply_text(
                    f"✅ Ваша заявка #{app_number} принята! С вами скоро свяжутся.",
                    reply_markup=ReplyKeyboardRemove()
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
            await update.message.reply_text("Укажите даты и время:")
            return DATES
        elif choice == "🔙 Назад к сводке":
            summary = self._create_summary(user.id)
            keyboard = [["✅ Подтвердить", "✏️ Редактировать"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            await update.message.reply_text(summary, reply_markup=reply_markup)
            return CONFIRMATION

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена диалога"""
        user = update.message.from_user
        if user.id in self.user_data:
            del self.user_data[user.id]
        await update.message.reply_text('Диалог прерван. Для новой заявки отправьте /start')
        return ConversationHandler.END

def main():
    # Получаем токен из переменных окружения Render
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        logger.error("Токен бота не найден! Установите переменную BOT_TOKEN в Render.com")
        return
    
    bot = EquipmentBot()
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_fio)],
            UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_unit)],
            EQUIPMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_equipment)],
            DATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_dates)],
            CONFIRMATION: [
                MessageHandler(filters.Regex("^(✅ Подтвердить|✏️ Редактировать)$"), bot.handle_confirmation),
                MessageHandler(filters.Regex("^(👤 ФИО|🏢 Структурная единица|📹 Оборудование|📅 Даты|🔙 Назад к сводке)$"), bot.handle_edit_choice)
            ],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Запускаем бота
    logger.info("Бот запущен на Render.com!")
    application.run_polling()

if __name__ == '__main__':
    main()