from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from telegram_ftp_bot.config import config

db = create_engine(config['database_uri'])
Session = sessionmaker(db)
