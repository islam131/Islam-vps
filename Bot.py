import logging
import time
from threading import Thread, Event
from telegram import Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.error import TelegramError

# إعداد السجلات
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class BotForwarder:
    def __init__(self):
        self.target_bot_token = None
        self.target_bot = None
        self.target_user_id = None
        self.target_bot_info = None
        self.state = "waiting_token"  # waiting_token, waiting_user_id, active
        self.forwarding_active = False
        self.stop_event = Event()
        self.last_update_id = 0
    
    def start(self, update: Updater, context: CallbackContext):
        """بداية المحادثة"""
        self.forwarding_active = False
        self.stop_event.set()
        
        update.message.reply_text(
            "🤖 مرحباً! أرسل لي توكن البوت الذي تريد مراقبته\n"
            "مثال: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        )
        self.state = "waiting_token"
    
    def check_bot_token(self, token):
        """فحص صحة توكن البوت"""
        try:
            bot = Bot(token=token)
            bot_info = bot.get_me()
            return bot, bot_info
        except TelegramError as e:
            logger.error(f"خطأ في فحص التوكن: {e}")
            return None, None
    
    def forward_messages(self):
        """مراقبة وإعادة توجيه الرسائل الجديدة"""
        logger.info("بدء مؤشر ترابط إعادة التوجيه")
        offset = -1  # البدء من أحدث رسالة
        
        while not self.stop_event.is_set() and self.forwarding_active:
            try:
                # الحصول على الرسائل الجديدة
                updates = self.target_bot.get_updates(
                    offset=offset,
                    timeout=30,
                    limit=100
                )
                
                if updates:
                    logger.info(f"تم العثور على {len(updates)} تحديث جديد")
                    
                    for update in updates:
                        # تحديث الـ offset
                        offset = update.update_id + 1
                        self.last_update_id = update.update_id
                        
                        if update.message:
                            logger.info(f"رسالة من: {update.message.from_user.id if update.message.from_user else 'Unknown'} إلى: {update.message.chat.id}")
                            
                            # نعيد توجيه جميع الرسائل التي تصل للبوت
                            logger.info("جاري إعادة توجيه الرسالة")
                            self.forward_single_message(update.message)
                
                # انتظار قصير قبل المحاولة التالية
                time.sleep(1)
                
            except TelegramError as e:
                logger.error(f"خطأ في الحصول على التحديثات: {e}")
                time.sleep(5)
            except Exception as e:
                logger.error(f"خطأ غير متوقع: {e}")
                time.sleep(5)
        
        logger.info("توقف مؤشر ترابط إعادة التوجيه")
    
    def forward_single_message(self, message):
        """إعادة توجيه رسالة واحدة بشكل مباشر"""
        try:
            logger.info(f"محاولة إعادة توجيه رسالة {message.message_id} إلى المستخدم {self.target_user_id}")
            
            # إعادة توجيه الرسالة بشكل مباشر
            self.target_bot.forward_message(
                chat_id=self.target_user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            
            logger.info(f"تم إعادة توجيه الرسالة {message.message_id} بنجاح")
            
        except Exception as e:
            logger.error(f"خطأ في إعادة توجيه الرسالة: {e}")
    
    def handle_message(self, update: Updater, context: CallbackContext):
        """معالجة الرسائل"""
        user_message = update.message.text
        
        if self.state == "waiting_token":
            # فحص التوكن
            update.message.reply_text("🔍 جاري فحص التوكن...")
            
            bot, bot_info = self.check_bot_token(user_message)
            
            if bot and bot_info:
                self.target_bot = bot
                self.target_bot_info = bot_info
                
                update.message.reply_text(
                    f"✅ التوكن صحيح!\n"
                    f"🤖 اسم البوت: @{bot_info.username}\n"
                    f"📝 الاسم: {bot_info.first_name}\n\n"
                    f"الآن أرسل لي الـ User ID الذي تريد إرسال الرسائل إليه"
                )
                self.state = "waiting_user_id"
            else:
                update.message.reply_text(
                    "❌ التوكن غير صحيح أو البوت متوقف\n"
                    "تأكد من التوكن وحاول مرة أخرى"
                )
        
        elif self.state == "waiting_user_id":
            # حفظ الـ User ID
            try:
                self.target_user_id = int(user_message)
                
                # فحص إذا كان بإمكان إرسال رسالة للمستخدم
                try:
                    test_message = self.target_bot.send_message(
                        chat_id=self.target_user_id,
                        text="🔗 تم ربط البوت بنجاح! سيتم إعادة توجيه جميع الرسائل الجديدة إليك"
                    )
                    
                    logger.info(f"تم إرسال رسالة اختبار إلى المستخدم {self.target_user_id}")
                    
                    # بدء إعادة التوجيه
                    self.forwarding_active = True
                    self.stop_event.clear()
                    
                    # بدء مؤشر الترابط لمراقبة الرسائل
                    forward_thread = Thread(target=self.forward_messages)
                    forward_thread.daemon = True
                    forward_thread.start()
                    
                    update.message.reply_text(
                        f"✅ تم حفظ الـ User ID: {self.target_user_id}\n"
                        f"🔄 بدء إعادة توجيه الرسائل الجديدة...\n\n"
                        f"📝 الآن أي رسالة تصل للبوت @{self.target_bot_info.username} سيتم إعادة توجيهها إليك بشكل مباشر\n"
                        f"لإيقاف الإعادة التوجيه، أرسل /stop"
                    )
                    self.state = "active"
                
                except TelegramError as e:
                    logger.error(f"خطأ في إرسال رسالة للمستخدم: {e}")
                    update.message.reply_text(
                        f"❌ لا يمكن إرسال رسائل لهذا المستخدم\n"
                        f"تأكد من أن المستخدم بدأ محادثة مع البوت أولاً\n"
                        f"الخطأ: {str(e)}"
                    )
            
            except ValueError:
                update.message.reply_text(
                    "❌ الـ User ID يجب أن يكون رقماً\n"
                    "مثال: 123456789"
                )
        
        elif self.state == "active":
            # عندما يكون الإعادة التوجيه نشطة
            if user_message.lower() == '/stop':
                # إيقاف الإعادة التوجيه
                self.forwarding_active = False
                self.stop_event.set()
                
                update.message.reply_text(
                    "⏹️ تم إيقاف إعادة توجيه الرسائل\n"
                    "للبدء من جديد، أرسل /start"
                )
                self.state = "waiting_token"
            else:
                update.message.reply_text(
                    "🔄 إعادة التوجيه نشطة حالياً\n"
                    "لإيقاف الإعادة التوجيه، أرسل /stop"
                )

def main():
    """تشغيل البوت الرئيسي"""
    # ضع توكن البوت الرئيسي هنا
    MAIN_BOT_TOKEN = "8357386725:AAFbfPHJpp_kftsaggFvCwbwlLJR3r1FO1E"
    
    # إنشاء مثيل من معيد التوجيه
    bot_forwarder = BotForwarder()
    
    # إعداد Updater
    updater = Updater(token=MAIN_BOT_TOKEN, use_context=True)
    
    # إضافة المعالجات
    updater.dispatcher.add_handler(CommandHandler("start", bot_forwarder.start))
    updater.dispatcher.add_handler(CommandHandler("stop", bot_forwarder.handle_message))
    updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, bot_forwarder.handle_message))
    
    # تشغيل البوت
    print("🚀 البوت يعمل الآن...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
