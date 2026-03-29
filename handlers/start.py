from telegram import Update
from telegram.ext import ContextTypes
import database as db
import config
from keyboards import get_dev_keyboard, get_admin_keyboard, get_user_keyboard
from utils import send_notification_to_admins

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    with db.get_db_session() as session:
        user = session.query(db.User).filter_by(user_id=user_id).first()
        is_new_user = False
        
        if not user:
            user = db.User(user_id=user_id, username=username)
            session.add(user)
            is_new_user = True
        else:
            if username != user.username:
                user.username = username

    if is_new_user:
        user_tag = f"@{username}" if username else "بدون يوزر"
        msg = (
            f"🔔 <b>مستخدم جديد</b>\n"
            f"┌ 👤 الاسم: {user_tag}\n"
            f"└ 🆔 الآيدي: <code>{user_id}</code>"
        )
        await send_notification_to_admins(context, msg)

    if user_id == config.DEVELOPER_ID:
        welcome = "👨‍💻 <b>مرحباً بك يا مطور</b>\nلوحة التحكم الكاملة:"
        await update.message.reply_text(welcome, reply_markup=get_dev_keyboard(), parse_mode='HTML')
    elif db.is_admin(user_id):
        welcome = "🛡️ <b>مرحباً بك يا مشرف</b>\nلوحة الإدارة:"
        await update.message.reply_text(welcome, reply_markup=get_admin_keyboard(), parse_mode='HTML')
    else:
        welcome = "👋 <b>أهلاً بك في بوت النشر التلقائي</b>\nاختر من القائمة:"
        await update.message.reply_text(welcome, reply_markup=get_user_keyboard(), parse_mode='HTML')