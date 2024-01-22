import csv
from functools import partial
from asyncio import get_running_loop
from shutil import rmtree
from pathlib import Path
import logging
import os
import time
from typing import Union, Optional
from dotenv import load_dotenv
from telethon import TelegramClient, Button, events, types
from telethon.events import NewMessage, StopPropagation
from telethon.tl.custom import Message
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import InputPeerUser, ReplyKeyboardForceReply
import pandas as pd
import datetime
import calendar
import re
from utils import download_files, add_to_zip

load_dotenv()

API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']
BOT_TOKEN = os.environ['BOT_TOKEN']
CONC_MAX = int(os.environ.get('CONC_MAX', 3))
USERNAME = os.environ['USERNAME']
STORAGE = Path('../data/')
global_user_data = {}
YEAR, MONTH = datetime.datetime.now().year, datetime.datetime.now().month
FILENAME = "../data/selected_days.csv"
# FILENAME = 'selected_days.csv'
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
write_headers = not (os.path.exists(FILENAME) and os.path.getsize(FILENAME) > 0)
columns = ['Year', 'Month', 'Day', 'Count', 'USERNAME', 'FIRST_NAME', 'LAST_NAME']
if os.path.exists(FILENAME):
    existing_data = pd.read_csv(FILENAME)
else:
    # Create the file   
    existing_data = pd.DataFrame(columns=columns)
    with open(FILENAME, 'w') as file:
        existing_data.to_csv(file, index=False)

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
        'Try to do it after each class. The updates to calendar help us automate the payment process. 💸 \n\n '
        # 'We will give you an extra 1% bonus 💰 for calendar updates. '
        '📈 After you add the classes, the system will send you an automatically generated csv file with'
        ' the selected dates and the number of '
        'classes you had each day. 📊 You can take a look to make sure everything is correct.👀\n\n'
        
        '🚨 Try to be careful when selecting the days. 📆 Command for removing accidental selections is under '
        'development and will be added within a month. 🛠️\n\n'

        'Thank you 😊'


    )
    raise StopPropagation


@bot.on(NewMessage(pattern='/crypto_address'))
async def handle_crypto_address(event):
    user_id = event.sender_id
    user_entity = await event.client.get_entity(user_id)
    username = user_entity.username
    first_name = user_entity.first_name
    last_name = user_entity.last_name
    current_address = None
    flag_has_address = False
    try:
        with open('../data/crypto_addresses.csv', 'r') as file:
            reader = csv.reader(file)
            for row in reader:
                if row[0] == str(user_id):
                    current_address = row[4]
                    flag_has_address = True
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
            data_modified = False
            try:
                # Read all data from the CSV file
                with open('../data/crypto_addresses.csv', 'r') as file:
                    reader = csv.reader(file)
                    data = list(reader)

                # Check if user_id exists and update the address
                for row in data:
                    if row[0] == str(user_id):
                        row[4] = new_address
                        data_modified = True
                        break

                with open('../data/crypto_addresses.csv', 'w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerows(data)

                if not data_modified:
                    with open('../data/crypto_addresses.csv', 'a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow([user_id, username,first_name, last_name, new_address])

            except FileNotFoundError:
                with open('../data/crypto_addresses.csv', 'w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['USER_ID', 'USERNAME', 'FIRST_NAME', 'LAST_NAME', 'Address'])  # Optional: write headers
                    writer.writerow([user_id, username, first_name, last_name, new_address])
            await reply_event.reply("Crypto address updated.")
        else:
            await reply_event.reply("Invalid address. Make sure you chose the correct <b>BEP20 network</b>."
                                    " Run the /crypto_address command to try again.", parse_mode='html')
        bot.remove_event_handler(wait_for_reply)


@bot.on(NewMessage(pattern='/user_info'))
async def handle_user_info_request(event: MessageEvent):
    """
    Handle requests for user information.
    Starts by asking for a password.
    """
    force_reply = ReplyKeyboardForceReply(single_use=True, selective=True)
    await bot(SendMessageRequest(
        peer=await event.get_input_chat(),
        message="Please enter the admin password (it will take some time to send the files):",
        reply_markup=force_reply,
    ))
    time.sleep(8)

    @bot.on(NewMessage(from_users=event.sender_id))
    async def wait_for_password(reply_event):
        if reply_event.text.strip() == ADMIN_PASSWORD:
            # Password correct, send user information
            await send_user_info(reply_event)
        else:
            await reply_event.reply("Incorrect password.")
        bot.remove_event_handler(wait_for_password)


async def send_user_info(event: MessageEvent):
    """
    Send 'selected_days.csv' and 'crypto_addresses.csv' files.
    """
    # Assuming the files are in the '../data/' directory
    selected_days_file_path = "../data/selected_days.csv"
    crypto_addresses_file_path = "../data/crypto_addresses.csv"

    # Check if files exist
    if not os.path.exists(selected_days_file_path) or not os.path.exists(crypto_addresses_file_path):
        await event.reply("Error: One or both files do not exist.")
        return

    # Send the files
    await event.reply("Sending 'selected_days.csv' and 'crypto_addresses.csv' files.",
                      file=[selected_days_file_path, crypto_addresses_file_path])


def selected_days_from_csv(year: str, month: str, username: str):
    df = pd.read_csv(FILENAME)
    filtered_df = df[(df['Year'] == year) & (df['Month'] == month) & (df['USERNAME'] == username)]
    filtered = filtered_df.values.tolist()
    selected_days = list()
    for i in range(len(filtered)):
        selected_days.append(int(filtered[i][2]))
    selected_days.sort()
    selected_days = set(selected_days)
    return list(selected_days)


def create_calendar(year, month, selected_days):
    markup = []
    week_days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # Select a Different Month button
    markup.append([Button.inline("Select a Different Month", data="classes:selecting_month")])
    # Weekdays header
    markup += [[Button.inline(day, data="ignore") for day in week_days]]
    # Calendar days
    cal_month = calendar.monthcalendar(year, month)
    for week in cal_month:
        row = []
        for day in week:
            if day == 0:
                row.append(Button.inline(" ", data="ignore"))
                continue
            text = f"{day}🧑‍🏫" if day in selected_days else str(day)
            row.append(Button.inline(text, data=f"classes:{day}" if day != 0 else "ignore"))
        markup.append(row)
    # Submit button
    # markup.append([Button.inline("Submit", data="classes:submit")])
    return markup


@bot.on(NewMessage(pattern='/selected_month_calendar'))
async def ShowCalendar(event):
    user = await event.client.get_entity(event.sender_id)
    username = user.username

    year = global_user_data[event.sender_id]['selected_year']
    month = global_user_data[event.sender_id]['selected_month']

    # Filter data for the current user and month
    selected_days = selected_days_from_csv(str(year), str(month), str(username))

    # Creating and sending the calendar
    calendar_markup = create_calendar(year, month, selected_days)
    await event.respond(f"Please select the days in {calendar.month_name[month]} {year} when you had classes:",
                        buttons=calendar_markup)


@bot.on(NewMessage(pattern='/classes_current_month'))
async def ShowCalendarCurrentMonth(event):
    user = await event.client.get_entity(event.sender_id)
    username = user.username
    # Get the current year and month
    year, month = datetime.datetime.now().year, datetime.datetime.now().month
    user_id = event.sender_id
    # Accessing or initializing user data
    if user_id not in global_user_data:
        global_user_data[user_id] = {}
    global_user_data[event.sender_id]['selected_year'] = year
    global_user_data[event.sender_id]['selected_month'] = month
    # Filter data for the current user and month
    selected_days = selected_days_from_csv(str(year), str(month), str(username))
    # Creating and sending the calendar
    calendar_markup = create_calendar(year, month, selected_days)
    await event.respond(f"Please select the days in {calendar.month_name[month]} {year} when you had classes:",
                        buttons=calendar_markup)


@bot.on(events.NewMessage(pattern='/select_month'))
async def select_month(event):
    months = [calendar.month_abbr[i] for i in range(1, 13)]
    month_buttons = [Button.inline(month, f"select_month:month_{i}") for i, month in enumerate(months, 1)]

    # Grouping buttons in rows of three
    month_markup = [month_buttons[i:i + 3] for i in range(0, len(month_buttons), 3)]
    # month_markup.append([Button.inline("Submit", "select_month:submit")])

    await event.respond('Please select the month you want to make changes to:', buttons=month_markup)


async def select_year(event):
    current_year = datetime.datetime.now().year
    year_buttons = [Button.inline(str(year), f"select_month:year_{year}") for year in range(current_year - 5, current_year + 6)]

    # Grouping buttons in rows of three
    year_markup = [year_buttons[i:i+3] for i in range(0, len(year_buttons), 3)]
    # year_markup.append([Button.inline("Submit", "select_month:submit")])

    await event.respond('Please select the year you want to make changes to:', buttons=year_markup)


async def handle_selection_classes(event):
    # Extracting callback data
    data_formatted = event.data.decode('utf-8').split(':')[1]
    day_selected = data_formatted
    print(day_selected)
    if day_selected == "ignore":
        return
    user_id = event.sender_id
    user_entity = await event.client.get_entity(user_id)
    username = user_entity.username
    first_name = user_entity.first_name
    last_name = user_entity.last_name

    # Accessing or initializing user data
    if user_id not in global_user_data:
        global_user_data[user_id] = {}
    user_data = global_user_data[user_id]

    # Retrieve or set the selected year and month
    user_data['selected_year'] = user_data.get('selected_year', datetime.datetime.now().year)
    user_data['selected_month'] = user_data.get('selected_month', datetime.datetime.now().month)
    year, month = str(user_data['selected_year']), str(user_data['selected_month'])

    if os.path.exists(FILENAME) and os.path.getsize(FILENAME) > 0:
        with open(FILENAME, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            data = list(reader)
    else:
        data = []

    row_exists = False
    for row in data:
        if (row['Year'] == year and row['Month'] == month and row['Day'] == str(day_selected) and
                row['USERNAME'] == username):
            row['Count'] = str(int(row['Count']) + 1)
            row_exists = True
            break

    # If the row does not exist, add a new one
    if not row_exists:
        new_row = {
            'Year': year, 'Month': month, 'Day': str(day_selected), 'Count': '1',
            'USERNAME': username, 'FIRST_NAME': first_name, 'LAST_NAME': last_name
        }
        data.append(new_row)
    data.sort(key=lambda x: int(x['Day']))
    # Write the updated data back to the CSV
    with open(FILENAME, mode='w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(data)

    with open(FILENAME, mode='r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        filtered_rows = [row for row in reader if
                         row['USERNAME'] == username and row['Year'] == str(year) and row['Month'] == str(month)]

    output_filename = f"../data/{username}_{year}_{month}_classes.csv"
    with open(output_filename, mode='w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(filtered_rows)


    await event.respond(f"Your classes for {calendar.month_name[int(month)]} {year} have been updated.",
                        file=[output_filename])

async def handle_selection_help(event):
    # Extracting callback data
    data_formatted = event.data.decode('utf-8').split(':')[1]
    selected_data = data_formatted.split('_')
    selection_type = selected_data[0]
    value = int(selected_data[1])

    user_id = event.sender_id
    if user_id not in global_user_data:
        global_user_data[user_id] = {}
    user_data = global_user_data[user_id]

    if selection_type == "month":
        user_data['selected_month'] = value
        # Prompt for year selection
        await select_year(event)
    elif selection_type == "year":
        user_data['selected_year'] = value
        selected_month_name = calendar.month_name[user_data['selected_month']]
        # Confirming the selection and providing further instructions
        await event.edit(f"You have selected {selected_month_name} {value}. "
                         f"Now run /selected_month_calendar to see the calendar.")


@bot.on(events.CallbackQuery)
async def callback_query_handler(event):
    data = event.data.decode('utf-8')
    if data.startswith("select_month:"):
        await handle_selection_help(event)
    elif data.startswith("classes:"):
        await handle_selection_classes(event)


if __name__ == '__main__':
    bot.run_until_disconnected()
