import os
import sys
from config import DATABASE_URL

from sqlalchemy import create_engine, Column, BigInteger, String, Boolean, DateTime, Text, Integer  # ✅ أضفنا Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime
import random

# إعداد MySQL
print(f"Connecting to MySQL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'custom'}")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_recycle=3600,
    pool_pre_ping=True,
    connect_args={
        'charset': 'utf8mb4',
        'connect_timeout': 10
    }
)

Base = declarative_base()
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

# --- تعريف الجداول ---
# ملاحظة: create_all يتم استدعاؤه من main.py فقط بعد التحقق من الاتصال

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    is_admin = Column(Boolean, default=False)

class Channel(Base):
    __tablename__ = 'channels'
    id = Column(BigInteger, primary_key=True)
    channel_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    added_by = Column(BigInteger, nullable=True, index=True)
    category = Column(String(100), default="اقتباسات عامة")
    msg_format = Column(String(50), default="normal")
    time_type = Column(String(50), default="default")
    time_value = Column(String(50), nullable=True)
    last_post_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    
    # خصائص الملصق التفاعلي
    sticker_file_id = Column(String(255), nullable=True)
    sticker_interval = Column(Integer, default=0)  # ✅ Integer مستورد الآن
    msg_counter = Column(Integer, default=0)      # ✅ Integer مستورد الآن
    sticker_sender_id = Column(BigInteger, nullable=True)

class BotSettings(Base):
    __tablename__ = 'settings'
    id = Column(BigInteger, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)

class FileContent(Base):
    __tablename__ = 'files_content'
    id = Column(BigInteger, primary_key=True)
    category = Column(String(100), index=True, nullable=False)
    content = Column(Text, nullable=False)

# إنشاء الجداول - يتم استدعاؤه من main.py فقط

# --- Context Manager ---
from contextlib import contextmanager

@contextmanager
def get_db_session():
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# --- دوال مساعدة ---
def is_admin(user_id: int) -> bool:
    with get_db_session() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.is_admin if user else False

def add_channel(ch_id: int, title: str, added_by: int, cat: str, fmt: str, 
                t_type: str = 'default', t_val: str = None) -> bool:
    with get_db_session() as session:
        try:
            existing = session.query(Channel).filter_by(channel_id=ch_id).first()
            if existing:
                return False
            
            new_ch = Channel(
                channel_id=ch_id,
                title=title,
                added_by=added_by,
                category=cat,
                msg_format=fmt,
                time_type=t_type,
                time_value=t_val
            )
            session.add(new_ch)
            return True
        except Exception as e:
            print(f"Error adding channel: {e}")
            return False

def remove_channel_db(ch_id: int) -> bool:
    with get_db_session() as session:
        try:
            ch = session.query(Channel).filter_by(channel_id=ch_id).first()
            if ch:
                session.delete(ch)
                return True
            return False
        except Exception as e:
            print(f"Error removing channel: {e}")
            return False

def add_file_content(category: str, content_list: list) -> int:
    if not content_list:
        return 0
        
    with get_db_session() as session:
        count = 0
        
        if category == 'ابيات شعرية':
            poems = []
            current_poem = []
            
            for line in content_list:
                text = line.strip()
                
                if '-----' in text:
                    if current_poem:
                        poems.append("\n".join(current_poem))
                        current_poem = []
                elif text and not text.startswith('الشاعر:'):
                    current_poem.append(text)
            
            if current_poem:
                poems.append("\n".join(current_poem))
            
            for poem in poems:
                session.add(FileContent(category=category, content=poem))
                count += 1
        else:
            for text in content_list:
                if text.strip():
                    session.add(FileContent(category=category, content=text.strip()))
                    count += 1
        
        return count

def get_next_content(category: str) -> str:
    with get_db_session() as session:
        from sqlalchemy import func
        content = session.query(FileContent).filter_by(category=category).order_by(func.rand()).first()
        return content.content if content else None

def get_stats() -> str:
    with get_db_session() as session:
        users_count = session.query(User).count()
        channels_count = session.query(Channel).count()
        posts_count = session.query(FileContent).count()
        
        return (
            f"📊 <b>إحصائيات البوت</b>\n"
            f"┌ 👥 المستخدمون: <b>{users_count}</b>\n"
            f"├ 📢 القنوات: <b>{channels_count}</b>\n"
            f"└ 📝 الاقتباسات المخزنة: <b>{posts_count}</b>"
        )

def init_admin(user_id: int, username: str = None):
    with get_db_session() as session:
        existing = session.query(User).filter_by(user_id=user_id).first()
        if not existing:
            admin = User(user_id=user_id, username=username, is_admin=True)
            session.add(admin)
            print(f"Admin initialized: {user_id}")

def get_all_channels():
    with get_db_session() as session:
        return session.query(Channel).filter_by(is_active=True).all()

def update_channel_last_post(channel_id: int):
    with get_db_session() as session:
        ch = session.query(Channel).filter_by(channel_id=channel_id).first()
        if ch:
            ch.last_post_at = datetime.now()

def get_setting(key: str) -> str:
    with get_db_session() as session:
        s = session.query(BotSettings).filter_by(key=key).first()
        return s.value if s else None

def set_setting(key: str, value: str):
    with get_db_session() as session:
        s = session.query(BotSettings).filter_by(key=key).first()
        if s:
            s.value = value
        else:
            session.add(BotSettings(key=key, value=value))

def get_all_settings() -> list:
    with get_db_session() as session:
        return [(s.key, s.value) for s in session.query(BotSettings).all()]

def get_content_count_by_category() -> list:
    with get_db_session() as session:
        from sqlalchemy import func
        return session.query(FileContent.category, func.count(FileContent.id)).group_by(FileContent.category).all()

def delete_content_by_category(category: str) -> int:
    with get_db_session() as session:
        count = session.query(FileContent).filter_by(category=category).count()
        session.query(FileContent).filter_by(category=category).delete()
        return count

def toggle_channel_posting(channel_db_id: int) -> bool:
    """تبديل حالة النشر لقناة معينة، يرجع الحالة الجديدة"""
    with get_db_session() as session:
        ch = session.query(Channel).filter_by(id=channel_db_id).first()
        if ch:
            ch.is_active = not ch.is_active
            return ch.is_active
        return None
