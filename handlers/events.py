import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
import database as db
from utils import send_notification_to_admins

logger = logging.getLogger(__name__)

async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result.old_chat_member.status in ['administrator', 'member'] and \
       result.new_chat_member.status in ['left', 'kicked']:
        
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title
        
        # ✅ استخدام asyncio.create_task للإشعار (لا يحتظر)
        asyncio.create_task(
            send_notification_to_admins(context, f"⚠️ تم حذف البوت من <b>{chat_title}</b>")
        )
        
        # ✅ استخدام الدالة المعدلة (ترجع bool الآن)
        success = db.remove_channel_db(chat_id)
        
        if success:
            logger.info(f"Channel {chat_title} ({chat_id}) removed from database")
        else:
            logger.warning(f"Failed to remove channel {chat_id} from database")