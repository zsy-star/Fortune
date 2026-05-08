"""数据库引擎、会话与初始化。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URL
from models import Base

# SQLite 与 Qt 同进程使用时，允许非创建线程访问连接（后续若在后台线程访问库时需要）
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """创建所有已注册的 ORM 表。"""
    Base.metadata.create_all(bind=engine)


def get_session():
    """获取一个新的数据库会话（调用方负责 close）。"""
    return SessionLocal()
