import csv
from functools import partial
from asyncio import get_running_loop
from shutil import rmtree
from pathlib import Path
import logging
import os
from typing import Union, Optional
from dotenv import load_dotenv
from telethon import TelegramClient, Button, events, types
from telethon.events import NewMessage, StopPropagation
from telethon.tl.custom import Message
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import InputPeerUser, ReplyKeyboardForceReply
import pandas as pd
import re
from utils import download_files, add_to_zip

load_dotenv()

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
CONC_MAX = int(os.environ.get('CONC_MAX', 3))
USERNAME = os.environ['USERNAME']
STORAGE = Path('../data/')

MessageEvent = Union[NewMessage.Event, Message]
# MessageEvent = NewMessage.Event | Message

logging.basicConfig(
    format='[%(levelname)s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
    ]
)

# dict to keep track of tasks for every user
tasks: dict[int, list[int]] = {}

bot = TelegramClient(
    USERNAME, api_id=API_ID, api_hash=API_HASH).start(bot_token=BOT_TOKEN)

def is_valid_usdt_bep20_address(address):
    """
    Validate whether the input string is a USDT address in BEP20 (Binance Smart Chain) format.

    BEP20 addresses should follow the Ethereum address format, as they are Ethereum-style addresses.
    They typically start with '0x' followed by 40 hexadecimal characters. This function checks
    for that specific pattern.

    Args:
    address (str): The address string to be validated.

    Returns:
    bool: True if the address is in valid BEP20 format, False otherwise.
    """
    # Regex pattern for a valid Ethereum/BEP20 address
    pattern = r"^0x[a-fA-F0-9]{40}$"

    # Check if the address matches the pattern
    return bool(re.match(pattern, address))

@bot.on(NewMessage(pattern='/add'))
async def start_task_handler(event: MessageEvent):
    """
    Notifies the bot that the user is going to send the media.
    """
    tasks[event.sender_id] = []

    await event.respond('OK, send me some files.')

    raise StopPropagation


@bot.on(NewMessage(
    func=lambda e: e.sender_id in tasks and e.file is not None))
async def add_file_handler(event: MessageEvent):
    """
    Stores the ID of messages sended with files by this user.
    """
    tasks[event.sender_id].append(event.id)

    raise StopPropagation


@bot.on(NewMessage(pattern='/start'))
async def start_handler(event: MessageEvent):
    """
    Sends a welcome message to the user.
    """
    await event.respond(
        "Welcome to the CoinTutor Bot 🤖 \n \n"
        "This bot is used to automate the payment process for tutors. 💸 \n \n"
        "Please add your USDT address (BEP20 network) to receive payments using /crypto_address command. 🏦 \n \n"
        'Add the schedule of your completed classes. 📆 \n \n'
        "Please use /help to get more information about the bot. ℹ️ \n \n"
    )

    raise StopPropagation


@bot.on(NewMessage(pattern='/help'))
async def start_handler(event: MessageEvent):
    """
    Sends a welcome message to the user.
    """
    await event.respond(
        'You should update the calendar 📅 before the end of the month to indicate the classes you had that month. '
        'Try to do it after each class. The updates to calendar help us automate the payment process. 💸 '
        'We will give you an extra 1% bonus 💰 for calendar updates. \n\n'
        'Each star ⭐ on the calendar day indicates the number of the classes you had on that day.'
         'Left click 👈 to increase the value, right click 👉 to decrease. \n\n'

        'Thank you 😊'


    )
    raise StopPropagation


@bot.on(NewMessage(pattern='/crypto_address'))
async def handle_crypto_address(event):
    user_id = event.sender_id
    username = event.sender.username
    current_address = None

    try:
        with open('../data/crypto_addresses.csv', 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == str(user_id):
                    current_address = row[2]
                    break
    except (FileNotFoundError, StopIteration):
        current_address = None

    if current_address:
        message = f"✅ Current USDT Address (BEP20 network): {current_address}\n \n\n"

        await event.respond(
            message,
            buttons=[
                [Button.url("Tutorial for finding your USDT address in Binance",
                           url="https://www.youtube.com/watch?v=bSU84swL5kw&t=1s")],

                [Button.inline(f"USDT Address: {current_address} ", data=current_address)]
            ],
            link_preview=True
        )
        force_reply = ReplyKeyboardForceReply(single_use=True, selective=True)
        await bot(SendMessageRequest(
            peer=await event.get_input_chat(),
            message="💬 If you want to update your USDT address (BEP20 network), please reply to this message."
                    "  (include only the address):",
            reply_markup=force_reply,
        ))
    else:
        message = "⚠️ No crypto address found. Please set one for receiving payments. "
        await event.respond(
            message,
            buttons=[
                Button.url("Tutorial for finding your USDT address in Binance",
                           url="https://www.youtube.com/watch?v=bSU84swL5kw&t=1s")
            ],
            link_preview=True
        )
        force_reply = ReplyKeyboardForceReply(single_use=True, selective=True)
        await bot(SendMessageRequest(
            peer=await event.get_input_chat(),
            message="💬 Please reply to this message with your USDT address (BEP20 network) (only the address):",
            reply_markup=force_reply,
        ))

    @bot.on(NewMessage(from_users=event.sender_id, func=lambda e: e.text.strip().startswith('0x')))
    async def wait_for_reply(reply_event):
        new_address = reply_event.text.strip()
        if is_valid_usdt_bep20_address(new_address):
            try:
                with open('../data/crypto_addresses.csv', 'r') as file:
                    reader = csv.reader(file)
                    for row in reader:
                        if row[0] == str(user_id):
                            row[2] = new_address
                            break
            except (FileNotFoundError, StopIteration):
                with open('../data/crypto_addresses.csv', 'w') as file:
                    writer = csv.writer(file)
                    writer.writerow([user_id, username, new_address])
            await reply_event.reply("Crypto address updated.")
        else:
            await reply_event.reply("Invalid address. Make sure you chose the correct <b>BEP20 network</b>."
                                    " Run the /crypto_address command to try again.", parse_mode='html')
        bot.remove_event_handler(wait_for_reply)


if __name__ == '__main__':
    bot.run_until_disconnected()
