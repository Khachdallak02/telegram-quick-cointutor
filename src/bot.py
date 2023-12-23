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
STORAGE = Path('./files/')

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
    'quick-zip-bot', api_id=API_ID, api_hash=API_HASH
).start(bot_token=BOT_TOKEN)


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
        'Hi! I\'m a bot that can zip the media of messages you send me.\n\n'
        'To start a zip, use /add. Then, send me some files. When you\'re '
        'done, use /zip <zip_name> to get the zip file.\n\n'
        'To cancel a zip, use /cancel.\n\n'
        'To get this message again, use /start.'
    )

    raise StopPropagation

@bot.on(NewMessage(pattern='/zip (?P<name>\w+)'))
async def zip_handler(event: MessageEvent):
    """
    Zips the media of messages corresponding to the IDs saved for this user in
    tasks. The zip filename must be provided in the command.
    """
    if event.sender_id not in tasks:
        await event.respond('You must use /add first.')
    elif not tasks[event.sender_id]:
        await event.respond('You must send me some files first.')
    else:
        messages = await bot.get_messages(
            event.sender_id, ids=tasks[event.sender_id])
        zip_size = sum([m.file.size for m in messages])

        if zip_size > 1024 * 1024 * 2000:   # zip_size > 1.95 GB approximately
            await event.respond('Total filesize don\'t must exceed 2.0 GB.')
        else:
            root = STORAGE / f'{event.sender_id}/'
            zip_name = root / (event.pattern_match['name'] + '.zip')

            async for file in download_files(messages, CONC_MAX, root):
                await get_running_loop().run_in_executor(
                    None, partial(add_to_zip, zip_name, file))
            
            await event.respond('Done!', file=zip_name)

            await get_running_loop().run_in_executor(
                None, rmtree, STORAGE / str(event.sender_id))

        tasks.pop(event.sender_id)

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
                if row['user_id'] == str(user_id):
                    current_address = row['address']
                    break
    except (FileNotFoundError, StopIteration):
        current_address = None

    if current_address:
        message = f"Current USDT Address (BEP20 network): {current_address}\nIf you want to update it send "\
                  "your new address (nothing else, only the address). Tutorial for finding your USDT address in Binance: "\
                  "https://www.youtube.com/watch?v=bSU84swL5kw&t=1s"
        await bot.send_message(
            event.sender_id,
            message,

            buttons=[
                Button.url("Tutorial for finding your USDT address in Binance",
                           url="https://www.youtube.com/watch?v=bSU84swL5kw&t=1s"),
                Button.inline("USDT Address (BEP20 network)", data=current_address)

            ]

        )

    else:
        message = "⚠️ No crypto address found. Please set one for receiving payments. " \

        await event.respond(
            message,
            buttons=[
                Button.url("Tutorial for finding your USDT address in Binance",
                           url="https://www.youtube.com/watch?v=bSU84swL5kw&t=1s")
            ],
            link_preview=False
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
                        if row['user_id'] == str(user_id):
                            row['address'] = new_address
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


@bot.on(NewMessage(pattern='/cancel'))
async def cancel_handler(event: MessageEvent):
    """
    Cleans the list of tasks for the user.
    """
    try:
        tasks.pop(event.sender_id)
    except KeyError:
        pass

    await event.respond('Canceled zip. For a new one, use /add.')

    raise StopPropagation


if __name__ == '__main__':
    bot.run_until_disconnected()
