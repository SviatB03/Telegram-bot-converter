import os
import json
import requests
from dotenv import load_dotenv
import telebot
from telebot import types
from lang import MESSAGES

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("EXCHANGE_API_KEY")
API_URL = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/"

bot = telebot.TeleBot(BOT_TOKEN)

user_lang = {}      # {chat_id: 'uk' or 'en'}
user_state = {}     # {chat_id: 'waiting_amount' or None}
user_amount = {}    # {chat_id: amount}
user_history = {}   # {chat_id: [("USD/UAH", 123, 456), ...]}


@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add('🇺🇦 Українська', '🇬🇧 English')
    bot.send_message(message.chat.id, MESSAGES['language_choose']['uk'], reply_markup=markup)
    bot.register_next_step_handler(message, set_language)


def set_language(message):
    lang = 'uk' if 'Українська' in message.text else 'en'
    user_lang[message.chat.id] = lang
    user_state[message.chat.id] = None
    show_main_menu(message.chat.id)
    bot.send_message(message.chat.id, MESSAGES['start'][lang])


def show_main_menu(chat_id):
    lang = user_lang.get(chat_id, 'uk')
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(MESSAGES['btn_convert'][lang])
    markup.add(MESSAGES['btn_history'][lang])
    markup.add(MESSAGES['btn_help'][lang], MESSAGES['btn_about'][lang])
    bot.send_message(chat_id, "📋", reply_markup=markup)


@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    chat_id = message.chat.id
    lang = user_lang.get(chat_id, 'uk')

    text = message.text

    if text == MESSAGES['btn_convert'][lang]:
        user_state[chat_id] = 'waiting_amount'
        bot.send_message(chat_id, MESSAGES['start'][lang])
        return

    elif text == MESSAGES['btn_history'][lang]:
        history = user_history.get(chat_id, [])
        if not history:
            bot.send_message(chat_id, MESSAGES['history_empty'][lang])
        else:
            msg = "\n".join([f"{a} {pair} = {r}" for pair, a, r in history[-5:]])
            bot.send_message(chat_id, msg)
        return

    elif text == MESSAGES['btn_help'][lang]:
        bot.send_message(chat_id, MESSAGES['help'][lang])
        return

    elif text == MESSAGES['btn_about'][lang]:
        bot.send_message(chat_id, MESSAGES['about'][lang])
        return

    # handle amount input
    if user_state.get(chat_id) == 'waiting_amount':
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError
            user_amount[chat_id] = amount
            user_state[chat_id] = None
            show_currency_options(chat_id)
        except ValueError:
            bot.send_message(chat_id, MESSAGES['invalid_amount'][lang])
    else:
        bot.send_message(chat_id, MESSAGES['invalid_amount'][lang])


def show_currency_options(chat_id):
    lang = user_lang.get(chat_id, 'uk')
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("USD/UAH", callback_data="USD/UAH"),
        types.InlineKeyboardButton("EUR/UAH", callback_data="EUR/UAH"),
        types.InlineKeyboardButton("UAH/USD", callback_data="UAH/USD"),
        types.InlineKeyboardButton(MESSAGES['enter_custom'][lang], callback_data="custom")
    )
    bot.send_message(chat_id, MESSAGES['choose_pair'][lang], reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def handle_currency_pair(call):
    chat_id = call.message.chat.id
    lang = user_lang.get(chat_id, 'uk')

    if call.data == "custom":
        bot.send_message(chat_id, MESSAGES['enter_custom'][lang])
        bot.register_next_step_handler(call.message, custom_pair)
        return

    amount = user_amount.get(chat_id)
    if not amount:
        bot.send_message(chat_id, MESSAGES['invalid_amount'][lang])
        return

    try:
        from_curr, to_curr = call.data.split('/')
        result = convert_currency(from_curr, to_curr, amount)
        if result is None:
            raise Exception
        msg = MESSAGES['result'][lang].format(result=round(result, 2))
        bot.send_message(chat_id, f"{amount} {from_curr} = {round(result, 2)} {to_curr}\n{msg}")
        user_history.setdefault(chat_id, []).append((f"{from_curr}/{to_curr}", amount, round(result, 2)))
        show_main_menu(chat_id)
    except Exception:
        bot.send_message(chat_id, MESSAGES['invalid_currency'][lang])


def custom_pair(message):
    chat_id = message.chat.id
    lang = user_lang.get(chat_id, 'uk')
    amount = user_amount.get(chat_id)

    try:
        from_curr, to_curr = message.text.upper().split('/')
        result = convert_currency(from_curr, to_curr, amount)
        if result is None:
            raise Exception
        msg = MESSAGES['result'][lang].format(result=round(result, 2))
        bot.send_message(chat_id, f"{amount} {from_curr} = {round(result, 2)} {to_curr}\n{msg}")
        user_history.setdefault(chat_id, []).append((f"{from_curr}/{to_curr}", amount, round(result, 2)))
        show_main_menu(chat_id)
    except Exception:
        bot.send_message(chat_id, MESSAGES['invalid_currency'][lang])
        bot.register_next_step_handler(message, custom_pair)


def convert_currency(from_currency, to_currency, amount):
    try:
        url = API_URL + from_currency
        response = requests.get(url)
        data = response.json()
        if data['result'] != 'success':
            return None
        rate = data['conversion_rates'].get(to_currency)
        if rate:
            return amount * rate
        return None
    except Exception:
        return None


bot.polling(none_stop=True)

