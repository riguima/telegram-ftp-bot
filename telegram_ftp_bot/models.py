from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from telegram_ftp_bot.database import db


class Base(DeclarativeBase):
    pass


class Connection(Base):
    __tablename__ = 'connections'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str]
    host: Mapped[str]
    password: Mapped[str]


Base.metadata.create_all(db)
