import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
import config
from keyboards import (
    get_dev_keyboard, get_admin_keyboard, get_user_keyboard,
    get_back_keyboard, get_categories_keyboard, get_format_keyboard,
    get_time_keyboard, get_files_keyboard, get_categories_keyboard_edit,
    get_format_keyboard_edit, get_channel_options_keyboard
)
from utils import post_job, finalize_channel_addition, notify_dev

logger = logging.getLogger(__name__)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if user_id == config.DEVELOPER_ID: 
        role = "dev"
    elif db.is_admin(user_id): 
        role = "admin"
    else: 
        role = "user"

    # 1. زر تعديل الوقت
    if data == "edit_channel_time":
        await query.edit_message_text("اختر طريقة النشر الجديدة:", reply_markup=get_time_keyboard())
        return

    # 2. إدارة القنوات (تم التعديل ليعمل مع المستخدمين العاديين)
    if data == "manage_channels":
        with db.get_db_session() as session:
            all_channels = session.query(db.Channel).all()
            accessible_channels = []
            for ch in all_channels:
                try:
                    bot_member = await context.bot.get_chat_member(ch.channel_id, context.bot.id)
                    if bot_member.status not in ['administrator', 'creator']:
                        continue
                    user_member = await context.bot.get_chat_member(ch.channel_id, user_id)
                    if user_member.status in ['administrator', 'creator']:
                        accessible_channels.append(ch)
                        await asyncio.sleep(0.05)
                except Exception as e:
                    logger.warning(f"Skipping channel {ch.channel_id}: {e}")
                    continue
            
            if not accessible_channels:
                await query.edit_message_text(
                    "📭 <b>لا توجد قنوات</b>\nلا تملك صلاحيات إدارية في أي قناة مضافة.",
                    parse_mode='HTML',
                    reply_markup=get_back_keyboard(role)
                )
                return
            
            keyboard = []
            for ch in accessible_channels:
                status_icon = "🟢" if ch.is_active else "🔴"
                keyboard.append([InlineKeyboardButton(
                    f"{status_icon} {ch.title} — {ch.category}",
                    callback_data=f"edit_channel_{ch.id}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{role}")])
            await query.edit_message_text(
                "📋 <b>قنواتك:</b>\n🟢 نشط  |  🔴 موقوف",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    # زر إعدادات القناة (تم السماح للمستخدمين بالدخول طالما مروا من الفلتر)
    if data.startswith("edit_channel_") and data != "edit_channel_time":
        try:
            ch_id = int(data.split("_")[2])
        except ValueError:
            return

        context.user_data['editing_channel_id'] = ch_id

        # جلب حالة القناة الحالية
        with db.get_db_session() as session:
            ch = session.query(db.Channel).filter_by(id=ch_id).first()
            is_active = ch.is_active if ch else True

        await query.edit_message_text(
            f"⚙️ <b>إعدادات القناة</b>\nالحالة: {'🟢 نشط' if is_active else '🔴 موقوف'}",
            parse_mode='HTML',
            reply_markup=get_channel_options_keyboard(ch_id, is_active)
        )

    # --- إعداد الملصق التفاعلي ---
    if data == "set_sticker_flow":
        ch_id = context.user_data.get('editing_channel_id')
        if not ch_id: 
            return
        context.user_data['action'] = 'waiting_sticker'
        await query.edit_message_text(
            "✏️ أرسل الملصق (Sticker) الذي تريده أن ينشر تلقائياً:", 
            reply_markup=get_back_keyboard(role)
        )

    # حذف القناة
    if data == "confirm_del_channel":
        ch_id = context.user_data.get('editing_channel_id')
        if not ch_id:
            return
        keyboard = [
            [InlineKeyboardButton("❌ لا، تراجع", callback_data=f"edit_channel_{ch_id}")],
            [InlineKeyboardButton("✅ نعم، احذف", callback_data=f"delete_channel_{ch_id}", style="danger")]
        ]
        await query.edit_message_text(
            "⚠️ <b>تأكيد الحذف</b>\nهل أنت متأكد من حذف هذه القناة من النظام؟\n\n<i>لا يمكن التراجع عن هذا الإجراء.</i>",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    if data.startswith("delete_channel_"):
        ch_id = int(data.split("_")[2])
        
        # ✅ استخدام Context Manager
        with db.get_db_session() as session:
            ch = session.query(db.Channel).filter_by(id=ch_id).first()
            if ch:
                title = ch.title
                session.delete(ch)
                msg = f"✅ تم حذف القناة <b>{title}</b> بنجاح."
            else:
                msg = "❌ لم يتم العثور على القناة."
        
        context.user_data['editing_channel_id'] = None
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
        if "✅" in msg:
            user_tag = f"@{query.from_user.username}" if query.from_user.username else f"ID: {user_id}"
            asyncio.create_task(notify_dev(context, f"🗑️ <b>قناة حُذفت</b>\n📌 الاسم: <b>{title}</b>\n👤 حذفها: {user_tag}"))

    # تغيير الفئة والتنسيق
    if data == "change_cat_select":
        await query.edit_message_text(
            "اختر نوع المحتوى الجديد:", 
            reply_markup=get_categories_keyboard_edit(context)
        )

    if data == "change_fmt_select":
        await query.edit_message_text(
            "اختر شكل الرسالة الجديد:", 
            reply_markup=get_format_keyboard_edit(context)
        )

    if data.startswith("set_edit_cat_"):
        new_cat = data.split("_")[3]
        ch_id = context.user_data.get('editing_channel_id')
        if ch_id:
            # ✅ استخدام Context Manager
            with db.get_db_session() as session:
                try:
                    ch = session.query(db.Channel).filter_by(id=ch_id).first()
                    if ch:
                        ch.category = new_cat
                        msg = f"✅ تم تغيير نوع المحتوى إلى <b>{new_cat}</b>."
                    else:
                        msg = "❌ حدث خطأ."
                except Exception as e:
                    logger.error(f"Error updating category: {e}")
                    msg = "❌ حدث خطأ في قاعدة البيانات."
            
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    if data.startswith("set_edit_fmt_"):
        new_fmt = data.split("_")[3]
        ch_id = context.user_data.get('editing_channel_id')
        if ch_id:
            # ✅ استخدام Context Manager
            with db.get_db_session() as session:
                try:
                    ch = session.query(db.Channel).filter_by(id=ch_id).first()
                    if ch:
                        ch.msg_format = new_fmt
                        msg = f"✅ تم تغيير شكل الرسالة إلى <b>{new_fmt}</b>."
                    else:
                        msg = "❌ حدث خطأ."
                except Exception as e:
                    logger.error(f"Error updating format: {e}")
                    msg = "❌ حدث خطأ في قاعدة البيانات."
            
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    # إدارة المشرفين
    if data == "manage_admins":
        if user_id != config.DEVELOPER_ID:
            await query.edit_message_text("⛔️ هذا القسم للمطور فقط.", reply_markup=get_back_keyboard(role))
            return
        keyboard = [
            [InlineKeyboardButton("➕ إضافة مشرف", callback_data="add_admin_step1", style="primary")],
            [InlineKeyboardButton("➖ إزالة مشرف", callback_data="del_admin_step1", style="danger")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_dev")]
        ]
        await query.edit_message_text(
            "👥 <b>إدارة المشرفين</b>\nاختر العملية:",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    if data == "add_admin_step1":
        context.user_data['action'] = 'add_admin'
        await query.edit_message_text(
            "➕ <b>إضافة مشرف</b>\nأرسل الآيدي الرقمي أو @يوزرنيم للمستخدم:",
            parse_mode='HTML',
            reply_markup=get_back_keyboard(role)
        )

    if data == "del_admin_step1":
        context.user_data['action'] = 'del_admin'
        await query.edit_message_text(
            "➖ <b>إزالة مشرف</b>\nأرسل الآيدي الرقمي أو @يوزرنيم للمستخدم:",
            parse_mode='HTML',
            reply_markup=get_back_keyboard(role)
        )

    # إدارة الملفات
    if data == "manage_files":
        if not db.is_admin(user_id) and user_id != config.DEVELOPER_ID:
            await query.edit_message_text(
                "⛔️ هذا القسم للمشرفين فقط.", 
                reply_markup=get_back_keyboard(role)
            )
            return
        if user_id == config.DEVELOPER_ID:
            from keyboards import CATEGORIES
            counts = db.get_content_count_by_category()
            counts_dict = {cat: cnt for cat, cnt in counts}
            keyboard = []
            for label, value in CATEGORIES:
                cnt = counts_dict.get(value, 0)
                keyboard.append([InlineKeyboardButton(f"{label} ({cnt} اقتباس)", callback_data=f"dev_file_menu_{value}")])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_dev")])
            await query.edit_message_text("📂 <b>إدارة ملفات النشر:</b>\nاختر الفئة:", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("اختر القسم لرفع ملفات الاقتباسات (txt):", reply_markup=get_files_keyboard())

    if data.startswith("dev_file_menu_"):
        if user_id != config.DEVELOPER_ID:
            return
        category = data[len("dev_file_menu_"):]
        context.user_data['dev_file_category'] = category
        counts_dict = {c: n for c, n in db.get_content_count_by_category()}
        keyboard = [
            [InlineKeyboardButton("📤 رفع ملف جديد (إضافة)", callback_data=f"upload_{category}")],
            [InlineKeyboardButton("🔄 استبدال الكل برفع ملف جديد", callback_data=f"replace_file_{category}")],
            [InlineKeyboardButton("🗑️ حذف كل محتوى الفئة", callback_data=f"confirm_del_content_{category}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="manage_files")],
        ]
        await query.edit_message_text(
            f"📁 الفئة: <b>{category}</b>\nعدد الاقتباسات: <b>{counts_dict.get(category, 0)}</b>\n\nاختر العملية:",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    if data.startswith("confirm_del_content_"):
        if user_id != config.DEVELOPER_ID:
            return
        category = data[len("confirm_del_content_"):]
        keyboard = [
            [InlineKeyboardButton("❌ لا، ارجع", callback_data=f"dev_file_menu_{category}")],
            [InlineKeyboardButton("✅ نعم، احذف الكل", callback_data=f"do_del_content_{category}")],
        ]
        await query.edit_message_text(
            f"⚠️ هل أنت متأكد من حذف <b>كل</b> اقتباسات فئة <b>{category}</b>؟",
            parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard)
        )

    if data.startswith("do_del_content_"):
        if user_id != config.DEVELOPER_ID:
            return
        category = data[len("do_del_content_"):]
        deleted = db.delete_content_by_category(category)
        await query.edit_message_text(
            f"✅ تم حذف <b>{deleted}</b> اقتباس من فئة <b>{category}</b>.",
            parse_mode='HTML', reply_markup=get_back_keyboard(role)
        )

    if data.startswith("replace_file_"):
        if user_id != config.DEVELOPER_ID:
            return
        category = data[len("replace_file_"):]
        db.delete_content_by_category(category)
        context.user_data['upload_category'] = category
        await query.edit_message_text(
            f"🗑️ تم مسح محتوى <b>{category}</b>.\n\nأرسل الآن ملف <code>.txt</code> الجديد:",
            parse_mode='HTML', reply_markup=get_back_keyboard(role)
        )

    if data.startswith("upload_"):
        category = data[len("upload_"):]
        context.user_data['upload_category'] = category
        msg = f"تم اختيار قسم: <b>{category}</b>\n\nالآن قم بإرسال ملف <code>.txt</code> يحتوي على الاقتباسات."
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    # ===== إعدادات البوت (للمطور فقط) =====
    if data == "bot_settings":
        if user_id != config.DEVELOPER_ID:
            return
        settings = db.get_all_settings()
        if settings:
            text = "⚙️ <b>إعدادات البوت الحالية:</b>\n\n"
            text += "\n".join([f"🔹 <code>{k}</code>: <b>{v}</b>" for k, v in settings])
        else:
            text = "⚙️ لا توجد إعدادات محفوظة حالياً."
        keyboard = [
            [InlineKeyboardButton("✏️ تعديل إعداد", callback_data="edit_setting_prompt")],
            [InlineKeyboardButton("➕ إضافة إعداد جديد", callback_data="add_setting_prompt")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_dev")],
        ]
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    if data == "edit_setting_prompt":
        if user_id != config.DEVELOPER_ID:
            return
        context.user_data['action'] = 'edit_setting_key'
        await query.edit_message_text("أرسل اسم الإعداد (key) الذي تريد تعديله:", reply_markup=get_back_keyboard(role))

    if data == "add_setting_prompt":
        if user_id != config.DEVELOPER_ID:
            return
        context.user_data['action'] = 'add_setting_key'
        await query.edit_message_text("أرسل اسم الإعداد الجديد (key):", reply_markup=get_back_keyboard(role))

    # إضافة قناة
    if data == "add_channel_prompt":
        context.user_data['step'] = 'waiting_channel'
        await query.edit_message_text(
            "➕ <b>إضافة قناة</b>\n\nأرسل معرف القناة مثل <code>@ChannelName</code>\nأو حوّل (Forward) أي رسالة من القناة هنا:",
            parse_mode='HTML',
            reply_markup=get_back_keyboard(role)
        )

    # اختيارات القسم والتنسيق والوقت
    if data.startswith("cat_"):
        category = data.split("_")[1]
        context.user_data['selected_category'] = category
        msg = f"تم اختيار القسم: <b>{category}</b>.\n\nاختر شكل الرسالة:"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_format_keyboard())

    if data.startswith("fmt_"):
        fmt = data.split("_")[1]
        context.user_data['selected_format'] = fmt
        await query.edit_message_text("اختر طريقة النشر:", reply_markup=get_time_keyboard())

    if data.startswith("time_"):
        time_type = data.split("_")[1]
        context.user_data['time_type'] = time_type
        
        is_edit_mode = context.user_data.get('editing_channel_id') is not None
        
        if is_edit_mode:
            # ✅ استخدام Context Manager
            with db.get_db_session() as session:
                ch_id = context.user_data.get('editing_channel_id')
                ch = session.query(db.Channel).filter_by(id=ch_id).first()
                
                msg = ""
                if ch:
                    ch.time_type = time_type
                    if time_type == "default":
                        ch.time_value = None
                        msg = "✅ تم تغيير الوقت إلى <b>افتراضي (عشوائي/فوري)</b>."
                        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
                        return
                    else:
                        if time_type == "fixed":
                            context.user_data['action'] = 'set_fixed_time'
                            msg = f"الوقت الحالي: {ch.time_value}\n\nأرسل الساعات الجديدة (مثلاً: 10, 14, 20):"
                        elif time_type == "interval":
                            context.user_data['action'] = 'set_interval'
                            msg = f"الوقت الحالي: {ch.time_value}\n\nأرسل الفارق الزمني الجديد بالدقائق (مثلاً: 60):"
                        
                        context.user_data['mode'] = 'edit' 
                        await query.edit_message_text(msg, reply_markup=get_back_keyboard(role))
                        return
                else:
                    msg = "❌ القناة غير موجودة."
                    await query.edit_message_text(msg)
                    return

        else:
            msg = ""
            if time_type == "fixed":
                context.user_data['action'] = 'set_fixed_time'
                msg = "أرسل الساعات المطلوبة (مثلاً: 10, 14, 20) مفصولة بفاصلة:"
            elif time_type == "interval":
                context.user_data['action'] = 'set_interval'
                msg = "أرسل الفارق الزمني بالدقائق (مثلاً: 60):"
            else:
                await finalize_channel_addition(update, context, query, role)
                return
            
            await query.edit_message_text(msg, reply_markup=get_back_keyboard(role))
        
    # إحصائيات
    if data == "show_stats":
        stats = db.get_stats()
        await query.edit_message_text(stats, parse_mode='HTML', reply_markup=get_back_keyboard(role))

    if data == "back_home":
        context.user_data.clear()
        kb = get_dev_keyboard() if role == "dev" else (get_admin_keyboard() if role == "admin" else get_user_keyboard())
        titles = {"dev": "👨‍💻 <b>لوحة المطور</b>", "admin": "🛡️ <b>لوحة المشرف</b>", "user": "📋 <b>القائمة الرئيسية</b>"}
        await query.edit_message_text(titles[role], parse_mode='HTML', reply_markup=kb)

    if data == "back_dev":
        context.user_data.clear()
        await query.edit_message_text("👨‍💻 <b>لوحة المطور</b>", parse_mode='HTML', reply_markup=get_dev_keyboard())

    if data == "back_admin":
        context.user_data.clear()
        await query.edit_message_text("🛡️ <b>لوحة المشرف</b>", parse_mode='HTML', reply_markup=get_admin_keyboard())

    if data == "back_user":
        context.user_data.clear()
        await query.edit_message_text("📋 <b>القائمة الرئيسية</b>", parse_mode='HTML', reply_markup=get_user_keyboard())

    # تشغيل/إيقاف النشر لقناة محددة
    if data.startswith("toggle_channel_"):
        ch_id = int(data.split("_")[2])
        new_state = db.toggle_channel_posting(ch_id)
        if new_state is None:
            await query.edit_message_text("❌ لم يتم العثور على القناة.", reply_markup=get_back_keyboard(role))
            return
        state_text = "🟢 مفعّل" if new_state else "🔴 موقوف"
        await query.edit_message_text(
            f"✅ تم تغيير حالة النشر إلى: <b>{state_text}</b>\n\nخيارات القناة:",
            parse_mode='HTML', reply_markup=get_channel_options_keyboard(ch_id, new_state)
        )
        user_tag = f"@{query.from_user.username}" if query.from_user.username else f"ID: {user_id}"
        asyncio.create_task(notify_dev(context, f"⚙️ <b>نشر قناة تغيّر</b>\n👤 بواسطة: {user_tag}\n📊 الحالة: {state_text}"))
        return

    # تفعيل/تعطيل البوت كلياً (للمطور فقط)
    if data == "toggle_bot":
        if user_id != config.DEVELOPER_ID:
            await query.edit_message_text("⛔️ هذا الخيار للمطور فقط.", reply_markup=get_back_keyboard(role))
            return
        with db.get_db_session() as session:
            setting = session.query(db.BotSettings).filter_by(key='posting_status').first()
            status = setting.value if setting else 'off'
            new_status = 'on' if status == 'off' else 'off'
            if setting:
                setting.value = new_status
            else:
                session.add(db.BotSettings(key='posting_status', value=new_status))
        state_text = "🟢 مفعّل" if new_status == 'on' else "🔴 متوقف"
        msg = f"تم تغيير حالة البوت إلى: <b>{state_text}</b>"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard(role))
        user_tag = f"@{query.from_user.username}" if query.from_user.username else f"ID: {user_id}"
        asyncio.create_task(notify_dev(context, f"🤖 <b>حالة البوت تغيّرت</b>\n👤 بواسطة: {user_tag}\n📊 الحالة: {state_text}"))

    if data == "post_now":
        await query.edit_message_text("⏳ <b>جاري النشر الفوري...</b>", parse_mode='HTML')
        await post_job(context, force_one=True)
        await query.edit_message_text("✅ <b>تم النشر بنجاح</b>", parse_mode='HTML', reply_markup=get_back_keyboard(role))

    if data == "broadcast_menu":
        if not db.is_admin(user_id) and user_id != config.DEVELOPER_ID:
            await query.edit_message_text("⛔️ هذه الميزة للمشرفين فقط.", reply_markup=get_back_keyboard(role))
            return
        context.user_data['action'] = 'waiting_broadcast'
        await query.edit_message_text(
            "📢 <b>إرسال إذاعة</b>\n\nأرسل الرسالة التي تريد إذاعتها لجميع المستخدمين والقنوات:",
            parse_mode='HTML',
            reply_markup=get_back_keyboard(role)
        )