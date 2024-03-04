import os
from pathlib import Path

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
            },
            row_width=1,
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
    bot.register_next_step_handler(message, lambda m: on_host(m, message.text))


def on_host(message, username):
    bot.send_message(message.chat.id, 'Digite a Senha')
    bot.register_next_step_handler(
        message, lambda m: on_password(m, username, message.text)
    )


def on_password(message, username, host):
    with Session() as session:
        session.add(
            Connection(username=username, host=host, password=message.text)
        )
        session.commit()
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
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: 'remove_connection:' in c.data)
def remove_connection_action(callback_query):
    with Session() as session:
        connection_id = int(callback_query.data.split(':')[-1])
        connection = session.get(Connection, connection_id)
        session.delete(connection)
        session.commit()
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
            reply_markup=quick_markup(reply_markup, row_width=1),
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
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: 'connect:' in c.data)
def connect_action(callback_query):
    global sftp_connection
    message = bot.send_message(callback_query.message.chat.id, 'Conectando...')
    with Session() as session:
        connection_id = int(callback_query.data.split(':')[-1])
        connection = session.get(Connection, connection_id)
        cnopts = pysftp.CnOpts()
        cnopts.hostkeys = None
        sftp_connection = pysftp.Connection(
            connection.host,
            username=connection.username,
            password=connection.password,
            cnopts=cnopts,
        )
        show_folder_content(callback_query.message)
        bot.delete_message(callback_query.message.chat.id, message.message_id)


def show_folder_content(message):
    reply_markup = {}
    for directory in sftp_connection.listdir_attr():
        if sftp_connection.isdir(directory.filename):
            reply_markup[f'📂 {directory.filename}'] = {
                'callback_data': f'cd:{directory.filename}'
            }
        else:
            reply_markup[f'📄 {directory.filename}'] = {
                'callback_data': f'cd:{directory.filename}'
            }
    reply_markup['Upar Arquivos'] = {
        'callback_data': f'upload_file:{sftp_connection.pwd}'
    }
    reply_markup['Voltar'] = {
        'callback_data': f'cd:{Path(sftp_connection.pwd).parent}'
    }
    reply_markup['Desconectar'] = {'callback_data': 'disconnect'}
    bot.send_message(
        message.chat.id,
        'Escolha uma opção',
        reply_markup=quick_markup(reply_markup, row_width=1),
    )


@bot.callback_query_handler(func=lambda c: 'upload_file:' in c.data)
def upload_file(callback_query):
    bot.send_message(
        callback_query.message.chat.id,
        'Envie quantos arquivos quiser, digite /pronto para finalizar',
    )
    bot.register_next_step_handler(
        callback_query.message, lambda m: on_file(m, [])
    )


def on_file(message, filenames):
    if message.text == '/pronto':
        upload_message = bot.send_message(message.chat.id, 'Upando Arquivos...')
        for filename in filenames:
            sftp_connection.put(f'uploads/{filename}')
            os.remove(f'uploads/{filename}')
        show_folder_content(message)
        bot.delete_message(upload_message.chat.id, upload_message.message_id)
    else:
        files_types = [message.photo, message.document, message.audio]
        for file in files_types:
            if file:
                try:
                    file_info = bot.get_file(file.file_id)
                except AttributeError:
                    file_info = bot.get_file(file[-1].file_id)
                downloaded_file = bot.download_file(file_info.file_path)
                filename = file_info.file_path.split('/')[-1]
                with open(f'uploads/{filename}', 'wb') as f:
                    f.write(downloaded_file)
                filenames.append(filename)
                break
        bot.register_next_step_handler(
            message, lambda m: on_file(m, filenames)
        )


@bot.callback_query_handler(func=lambda c: 'cd:' in c.data)
def change_directory(callback_query):
    directory = callback_query.data.split(':')[-1]
    sftp_connection.chdir(directory)
    show_folder_content(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'disconnect')
def disconnect(callback_query):
    sftp_connection.close()
    bot.send_message(callback_query.message.chat.id, 'Desconectado!')
    start(callback_query.message)


if __name__ == '__main__':
    bot.infinity_polling()
