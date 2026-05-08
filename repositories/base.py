"""仓储通用会话辅助。"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from core.database import SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """提供短生命周期会话，成功提交，异常回滚。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
