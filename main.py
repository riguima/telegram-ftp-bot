import pysftp
from sqlalchemy import select
from telebot import TeleBot
from telebot.util import quick_markup

from telegram_ftp_bot.config import config
from telegram_ftp_bot.database import Session
from telegram_ftp_bot.models import Connection

bot = TeleBot(config['bot_token'])

sftp_connection = None


@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.send_message(
        message.chat.id,
        'Escolha uma opção:',
        reply_markup=quick_markup(
            {
                'Adicionar Conexão': {'callback_data': 'add_connection'},
                'Remover Conexão': {'callback_data': 'remove_connection'},
                'Conexões': {'callback_data': 'connections'},
                'Acessar': {'callback_data': 'connect'},
            }
        ),
    )


@bot.callback_query_handler(func=lambda c: c.data == 'add_connection')
def add_connection(callback_query):
    bot.send_message(
        callback_query.message.chat.id, 'Digite o nome de usuario'
    )
    bot.register_next_step_handler(callback_query.message, on_username)


def on_username(message):
    bot.send_message(message.chat.id, 'Digite o IP')
    bot.register_next_step_handler(
        message, lambda: on_host(message, message.text)
    )


def on_host(message, username):
    bot.send_message(message.chat.id, 'Digite a Senha')
    bot.register_next_step_handler(
        message, lambda: on_password(message, username, message.text)
    )


def on_password(message, username, host):
    with Session() as session:
        session.add(
            Connection(username=username, host=host, password=message.text)
        )
        bot.send_message(message.chat.id, 'Conexão Adicionada!')
        start(message)


@bot.callback_query_handler(func=lambda c: c.data == 'remove_connection')
def remove_connection(callback_query):
    with Session() as session:
        reply_markup = {}
        for connection in session.scalars(select(Connection)).all():
            reply_markup[connection.host] = {
                'callback_data': f'remove_connection:{connection.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return'}
        bot.send_message(
            callback_query.message.chat.id,
            'Escolha uma conexão para ser removida',
            reply_markup=quick_markup(reply_markup),
        )


@bot.callback_query_handler(func=lambda c: 'remove_connection:' in c.data)
def remove_connection_action(callback_query):
    with Session() as session:
        connection_id = int(callback_query.data.split(':')[-1])
        connection = session.get(Connection, connection_id)
        session.delete(connection)
        bot.send_message(callback_query.message.chat.id, 'Conexão removida!')
        start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'connections')
def show_connections(callback_query):
    with Session() as session:
        reply_markup = {}
        for connection in session.scalars(select(Connection)).all():
            reply_markup[connection.host] = {
                'callback_data': f'show_connection:{connection.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return'}
        bot.send_message(
            callback_query.message.chat.id,
            'Conexões',
            reply_markup=quick_markup(reply_markup),
        )


@bot.callback_query_handler(func=lambda c: c.data == 'return')
def return_to_main_menu(callback_query):
    start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'connect')
def connect(callback_query):
    with Session() as session:
        reply_markup = {}
        for connection in session.scalars(select(Connection)).all():
            reply_markup[connection.host] = {
                'callback_data': f'connect:{connection.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return'}
        bot.send_message(
            callback_query.message.chat.id,
            'Escolha uma conexão',
            quick_markup(reply_markup),
        )


@bot.callback_query_handler(func=lambda c: 'connect:' in c.data)
def connect_action(callback_query):
    global sftp_connection
    with Session() as session:
        connection_id = int(callback_query.data.split(':')[-1])
        connection = session.get(Connection, connection_id)
        sftp_connection = pysftp.Connection(
            connection.host,
            username=connection.username,
            password=connection.password,
        )
        directories = sftp_connection.listdir_attr()
        for directory in directories:
            print(directory.filename, directory)
