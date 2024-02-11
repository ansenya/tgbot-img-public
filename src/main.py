import os
import time

import threading

import telegram

from telegram import *
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from selenium import webdriver
import uuid
from jinja2 import Template
from pyvirtualdisplay import Display
import logging

from db import *

TOKEN = "your-token"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

bot = Bot(token=TOKEN)


def create_img(path):
    with Display(size=(1920 * 2, 1024 * 2)):
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument("--headless")

        driver = webdriver.Chrome(options=options)
        # driver.get(f"file:////home/s-pk/PycharmProjects/tgbot-img/{path}.html")
        driver.get(f"file:////root/tgbot-img/{path}.html")

        main_element = driver.find_element("css selector", '.main')
        main_width = int(main_element.size['width'])
        main_height = int(main_element.rect['height'])

        driver.set_window_size(int(main_width * 100 / 45 * 2), int(main_height * 1.05 * 2))

        driver.save_screenshot(f"{path}.png")

        driver.quit()


def create(update: Update, context: CallbackContext) -> None:
    messages = get_all_tasks(update.message.chat.id)
    logging.info(f"Got '/create' from {update.message.from_user.username} with size = {len(messages)}")

    try:
        bg = get_chat_bg(update.message.chat_id)
    except IndexError:
        bot.send_message(chat_id=update.message.chat.id,
                         text="Пожалуйста, вызовите /start для инициализации бота.")
        return

    event = threading.Event()

    def periodic_task():
        while not event.is_set():
            context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.UPLOAD_PHOTO)
            time.sleep(5)

    threading.Thread(target=periodic_task).start()

    if len(messages) == 0:
        event.set()
        bot.send_message(chat_id=update.message.chat.id,
                         text="База данных пуста.\nЛибо Вы ничего не отправили ранее, либо вызвали /create.\nФункция "
                              "/create удаляет из базы сообщения, которые были отправлены ранее.")
        return

    output = Template(open('src/res/index.html', 'r').read()).render(messages=messages, bg=bg)

    path = f"src/temp/{uuid.uuid4()}"
    open(f"{path}.html", 'w').write(output)

    create_img(path)

    event.set()

    try:
        bot.send_photo(chat_id=update.message.chat.id, photo=open(f'{path}.png', 'rb'),
                       caption="Вот фотография.")
        bot.send_document(chat_id=update.message.chat.id, document=open(f'{path}.png', 'rb'), caption="Вот файл.")
    except telegram.error.BadRequest as e:
        bot.send_document(chat_id=update.message.chat.id, document=open(f'{path}.png', 'rb'), caption="Фотка слишком "
                                                                                                      "большая для "
                                                                                                      "телеграма, "
                                                                                                      "так что вот "
                                                                                                      "только файл.")
        logging.error(f"Bad request {e.message}")
        os.remove(f"{path}.html")
        return

    clear_all_tasks(update.message.chat.id)

    os.remove(f"{path}.html")
    os.remove(f"{path}.png")


def message_handler(update: Update, context: CallbackContext) -> None:
    logging.info(f"Got message from {update.message.from_user.username}")

    forwarded_message = update.message.forward_from
    if forwarded_message:
        user_id = forwarded_message.id
        username = forwarded_message.first_name

    else:
        user_id = update.message.from_user.id
        username = update.message.from_user.first_name

    photos = context.bot.get_user_profile_photos(user_id=user_id)

    if photos.photos:
        photo = photos.photos[0][-1]
        file = context.bot.get_file(photo.file_id)
        file_url = file.file_path
        insert_task(update.message.chat.id, username, file_url, update.message.text)
    else:
        bot.send_message(reply_to_message_id=update.message.message_id, chat_id=update.message.chat_id,
                         text="У владельца этого сообщения либо скрыта аватарка, либо её нет.\nНа фотографии "
                              "будет болванка.")
        insert_task(update.message.chat.id, username, "http://localhost:5000/bg/ava.png",
                    update.message.text)


def photo_handler(update: Update, context: CallbackContext) -> None:
    chat = get_chat(update.message.chat_id)

    if chat[4]:
        file_id = update.message.photo[-1].file_id

        file_obj = context.bot.get_file(file_id)

        photo_path = f"src/bg/{update.message.chat.id}.jpg"

        file_obj.download(photo_path)

        set_chat_back(update.message.chat_id, f"{update.message.chat.id}.jpg")

        update.message.reply_text("Теперь в качестве заднего фона будет Ваша фотография.")


def start(update: Update, context: CallbackContext):
    logging.info(f"Got '/start' from {update.message.from_user.username}")
    insert_chat(update.message.chat_id, update.message.chat.title)
    context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    bot.send_message(chat_id=update.message.chat.id,
                     text="Чтобы получить фотографию, Вам нужно переслать мне сообщения, а затем ввести комманду "
                          "/create.")


def back(update: Update, context: CallbackContext):
    chat = get_chat(update.message.chat_id)

    if chat[3] != "def":
        bot.send_photo(chat_id=update.message.chat.id, photo=open(f'src/bg/{chat[3]}', 'rb'),
                       caption="Сейчас у вас такой задний фон.")
    else:
        bot.send_message(chat_id=update.message.chat.id, text='У вас стандартный (белый) задний фон.')


def change_back(update: Update, context: CallbackContext):
    logging.info(f"Got '/back' from {update.message.from_user.username}")
    set_chat_waiting(update.message.chat_id, True)
    context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    bot.send_message(chat_id=update.message.chat.id,
                     text="Сейчас отправьте мне фотографию, которую Вы хотите иметь в качестве заднего фона на ваших "
                          "фотографиях.")


def empty_back(update: Update, context: CallbackContext):
    logging.info(f"Got '/empty' from {update.message.from_user.username}")
    set_chat_waiting(update.message.chat_id, True)
    context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    set_chat_back(update.message.chat_id, "def")
    bot.send_message(chat_id=update.message.chat.id,
                     text="Теперь у Вас задний фон стандартый (белый).")


def main() -> None:
    updater = Updater(TOKEN)

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("create", create))
    dp.add_handler(CommandHandler("back", back))
    dp.add_handler(CommandHandler("change", change_back))
    dp.add_handler(CommandHandler("empty", empty_back))
    dp.add_handler(MessageHandler(Filters.text, message_handler))
    dp.add_handler(MessageHandler(Filters.photo, photo_handler))

    try:
        updater.start_polling()
        logging.info(f"Bot successfully initialized")
    except telegram.error.Unauthorized:
        logging.error(f"Bot did not successfully initialized (Unauthorized)")

    updater.idle()


if __name__ == '__main__':
    init()
    main()
