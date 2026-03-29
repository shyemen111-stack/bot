import logging
from telegram import Update
from telegram.ext import ContextTypes, filters
import database as db

logger = logging.getLogger(__name__)

async def channel_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    هذه الدالة تراقب الرسائل القادمة من القنوات فقط.
    """
    if not update.channel_post:
        return

    # الفلتر في main.py يضمن أننا هنا فقط في حالة وجود نص أو صورة
    if update.channel_post.text or update.channel_post.photo:
        chat_id = update.effective_chat.id

        # ✅ استخدام Context Manager بدلاً من Session() المباشر
        with db.get_db_session() as session:
            try:
                channel = session.query(db.Channel).filter_by(channel_id=chat_id).first()
                
                # التأكد من وجود القناة وتفعيل خاصية الملصق التفاعلي
                if channel and channel.sticker_file_id and channel.sticker_interval:
                    
                    # زيادة العداد
                    channel.msg_counter += 1
                    
                    # حفظ العداد فوراً (commit داخلي)
                    # ✅ لا حاجة لـ session.commit() هنا لأننا في Context Manager
                    # لكن نحتاج commit قبل إرسال الملصق للتأكد من حفظ العداد
                    
                    # التحقق هل حان وقت النشر؟
                    if channel.msg_counter >= channel.sticker_interval:
                        sticker_sender_id = channel.sticker_sender_id
                        
                        try:
                            # إرسال الملصق كرسالة جديدة مستقلة
                            await context.bot.send_sticker(
                                chat_id=chat_id,
                                sticker=channel.sticker_file_id
                            )
                            
                            # تصفير العداد بعد النشر
                            channel.msg_counter = 0
                            logger.info(f"✅ Sticker sent to {channel.title} (Standalone).")

                        except Exception as e:
                            logger.error(f"❌ Failed to send sticker in {channel.title}: {e}")
                            # في حالة الفشل، لا نقوم بتصفير العداد لإعادة المحاولة لاحقاً

            except Exception as e:
                logger.error(f"Error in channel monitor: {e}")
                # ✅ لا حاجة لـ session.rollback() هنا لأن Context Manager يتعامل معه