import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import os
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from datetime import datetime,timedelta

from collections import defaultdict

active_sessions = defaultdict(dict)
# Conversation states
(
    PERSONAL_FIRSTNAME,
    PERSONAL_MIDDLENAME,
    PERSONAL_LASTNAME,
    PERSONAL_GEZZ_FIRSTNAME,
    PERSONAL_GEZZ_MIDDLENAME,
    PERSONAL_GEZZ_LASTNAME,
    PERSONAL_BIRTHPLACE,
    PERSONAL_BIRTH_CERT_NO,
    PERSONAL_PHONE_NUMBER,
    PERSONAL_EMAIL,
    PERSONAL_HEIGHT,
    PERSONAL_DOB,
    PERSONAL_DONE,
    DROPDOWN_STATE,
    FILE_UPLOAD_ID_DOC,
    FILE_UPLOAD_BIRTH_CERT,
    PAYMENT_METHOD_STATE,
    SEND_CONFIRMATION_STATE,
    SEND_PAYMENT_INSTRUCTION
) = range(6,25,1)

# --- Dropdown Sequence Configuration ---
DROPDOWN_SEQUENCE = [
    ('select[name="gender"]', "Gender", 2),
    ('select[name="martialStatus"]', "Marital Status", 3),
]
MAIN_MENU = 100
async def ask_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    message = update.message or update.callback_query.message
    await message.reply_text("Please select your region.")
    select_locator = page.locator("select.form-control").nth(0)
    await select_locator.wait_for()
    options = await select_locator.locator('option').all()
    valid_options = []
    
    for opt in options:
        value = await opt.get_attribute("value")
        text = (await opt.inner_text()).strip()
        if value and "--" not in text:
            valid_options.append((value, text))

    context.user_data["region_options"] = valid_options

    # Create keyboard with 2 buttons per row
    keyboard = []
    for i in range(0, len(valid_options), 2):
        row = []
        # Add first button of the pair
        if i < len(valid_options):
            value, text = valid_options[i]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        # Add second button of the pair if exists
        if i+1 < len(valid_options):
            value, text = valid_options[i+1]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a Region:", reply_markup=reply_markup)
    return 0

async def ask_region_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    query = update.callback_query
    await query.answer()
    
    selected_value = query.data.replace("region_", "")
    region_select = active_sessions[chat_id]['page'].locator("select.form-control").nth(0)
    await region_select.select_option(value=selected_value)
    
    # Manually trigger change event
    await active_sessions[chat_id]['page'].evaluate(
        """() => {
            const select = document.querySelectorAll("select.form-control")[0];
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )
    region_name = next((text for value, text in context.user_data["region_options"] if value == selected_value), "Unknown")

    await query.edit_message_text(text=f"✅ Region selected: {region_name}!")
    # Save the selected region in user_data in order to use it it in the address form
    context.user_data["region"] = region_name
    return await ask_city(update, context)

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    message = update.message or update.callback_query.message
    
    # Wait for the select element
    select_locator = page.locator("select.form-control").nth(1)
    await select_locator.wait_for()
    
    MAX_RETRIES = 10
    city_options = []
    
    for _ in range(MAX_RETRIES):
        await page.wait_for_timeout(500)
        city_options = await page.evaluate("""
                                () => {
                                    const select = document.querySelectorAll("select.form-control")[1];
                                    return Array.from(select.options)
                                        .filter(opt => {
                        const txt = opt.textContent.trim().toLowerCase();
                        return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");
                    })
                                        .map(opt => [opt.value, opt.textContent.trim()]);
                                }
                            """)
        if city_options:
            break
    
    if not city_options:
        await message.reply_text("❌ Failed to load city options. Please try again.")
        return ConversationHandler.END

    # Save and show city options
    context.user_data["city_options"] = city_options
    
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"city_{value}")] for value, text in city_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a City:", reply_markup=reply_markup)
    
    return 1

async def ask_city_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    query = update.callback_query
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    await query.answer()
    
    selected_value = query.data.replace("city_", "")
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(1).select_option(value=selected_value)
    city_name = next((text for value, text in context.user_data["city_options"] if value == selected_value), "Unknown")

    await query.edit_message_text(text=f"✅ City selected: {city_name}!")
    # Save the selected city in user_data
    context.user_data["city"] = city_name
    return await ask_office(update, context)

async def ask_office(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    
    select_locator = page.locator("select.form-control").nth(2)
    await select_locator.wait_for()
    
    MAX_RETRIES = 10
    office_options = []
    
    for _ in range(MAX_RETRIES):
        await page.wait_for_timeout(500)
        office_options = await page.evaluate("""
                            () => {
                                const select = document.querySelectorAll("select.form-control")[2];
                                return Array.from(select.options)
                                    .filter(opt => {
                    const txt = opt.textContent.trim().toLowerCase();
                    return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");})
                                    .map(opt => [opt.value, opt.textContent.trim()]);
                            }
                        """)
        if office_options:
            break

    if not office_options:
        await message.reply_text("❌ Failed to load office options. Please try again.")
        return ConversationHandler.END

    context.user_data["office_options"] = office_options

    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"office_{value}")] for value, text in office_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select an Office:", reply_markup=reply_markup)

    return 2

async def ask_office_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    query = update.callback_query
    await query.answer()
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    selected_value = query.data.replace("office_", "")
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(2).select_option(value=selected_value)
    office_name = next((text for value, text in context.user_data["office_options"] if value == selected_value), "Unknown")
    await query.edit_message_text(text=f"✅ Office selected: {office_name}!")
    return await ask_branch(update, context)

async def ask_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    select_locator = page.locator("select.form-control").nth(3)
    await select_locator.wait_for()

    MAX_RETRIES = 10
    branch_options = []

    for _ in range(MAX_RETRIES):
        await page.wait_for_timeout(500)
        branch_options = await page.evaluate("""
            () => {
                const select = document.querySelectorAll("select.form-control")[3];
                return Array.from(select.options)
                    .filter(opt => {
    const txt = opt.textContent.trim().toLowerCase();
    return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");
                    })
                    .map(opt => [opt.value, opt.textContent.trim()]);
            }
        """)
        if branch_options:
            break

    if not branch_options:
        await message.reply_text("❌ Failed to load branch options. Please try again.")
        return ConversationHandler.END

    context.user_data["branch_options"] = branch_options

    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"branch_{value}")] for value, text in branch_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a Branch:", reply_markup=reply_markup)

    return 3

async def ask_branch_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    query = update.callback_query
    await query.answer()
    
    selected_value = query.data.replace("branch_", "")
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(3).select_option(value=selected_value)
    branch_name = next((text for value, text in context.user_data["branch_options"] if value == selected_value), "Unknown")
    await query.edit_message_text(text=f"✅ Branch selected: {branch_name}!")
    
    await page.get_by_role("button", name="Next").click()
    await page.wait_for_timeout(3000)
    return await ask_date(update, context)

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    calendar_visible = await page.locator("div.react-calendar__month-view__days").is_visible()
    if not calendar_visible:
        await message.reply_text("Sorry, we couldn't find any available dates. Please try again later.")
        await cancel(update, context)
        return ConversationHandler.END
    
    # Wait for available dates
    while True:
        day_buttons = await page.locator("div.react-calendar__month-view__days button:not([disabled])").all()
        if day_buttons:
            break
        await page.locator("button.react-calendar__navigation__next-button").click()
        await page.wait_for_timeout(1000)

    available_days = []
    for i, button in enumerate(day_buttons, start=1):
        label = await button.locator("abbr").get_attribute("aria-label")
        if label:
            available_days.append((i, label, button))

    context.user_data["available_days"] = available_days

    # Create inline keyboard for dates
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"date_{i}")] for i, label, _ in available_days
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("📅 Available Dates:", reply_markup=reply_markup)

    return 4

async def ask_date_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    selected_idx = int(query.data.replace("date_", ""))
    available_days = context.user_data["available_days"]
    
    for i, label, button in available_days:
        if i == selected_idx:
            await button.click()
            await query.edit_message_text(text=f"✅ Selected date: {label}")
            break

    await active_sessions[chat_id]['page'].wait_for_timeout(1000)
    return await select_time_slot(update, context)

async def select_time_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    # Check for morning slots
    morning_buttons = await page.locator("table#displayMorningAppts input.btn_select").all()
    if morning_buttons:
        keyboard = [
            [InlineKeyboardButton("Morning Slot", callback_data="time_morning")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("🕒 Available Time Slots:", reply_markup=reply_markup)
        return 4
    
    # Check for afternoon slots
    afternoon_buttons = await page.locator("table#displayAfternoonAppts input.btn_select").all()
    if afternoon_buttons:
        keyboard = [
            [InlineKeyboardButton("Afternoon Slot", callback_data="time_afternoon")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("🕒 Available Time Slots:", reply_markup=reply_markup)
        return 4
    
    await message.reply_text("❌ No time slots available.")
    return ConversationHandler.END

async def handle_time_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    query = update.callback_query
    await query.answer()
    
    time_type = query.data.replace("time_", "")
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    
    if time_type == "morning":
        morning_buttons = await page.locator("table#displayMorningAppts input.btn_select").all()
        await morning_buttons[0].click()
        await query.edit_message_text(text="🕒 Selected morning time slot.")
    else:
        afternoon_buttons = await page.locator("table#displayAfternoonAppts input.btn_select").all()
        await afternoon_buttons[0].click()
        await query.edit_message_text(text="🕒 Selected afternoon time slot.")

    await page.get_by_role("button", name="Next").click()
    await page.wait_for_timeout(1000)
    return await ask_first_name(update, context)

# --- Ask Functions ---
async def ask_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    await message.reply_text("Enter your First Name:")
    return PERSONAL_FIRSTNAME

async def handle_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["first_name"] = message.text.strip()
    await message.reply_text("Enter your Middle Name:")
    return PERSONAL_MIDDLENAME

async def handle_middle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["middle_name"] = message.text.strip()
    await message.reply_text("Enter your Last Name:")
    return PERSONAL_LASTNAME

async def handle_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["last_name"] = message.text.strip()
    await message.reply_text("Enter your First Name in Amharic:")
    return PERSONAL_GEZZ_FIRSTNAME

async def handle_gez_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["amharic_first_name"] = message.text.strip()
    await message.reply_text("Enter your Middle Name in Amharic:")
    return PERSONAL_GEZZ_MIDDLENAME

async def handle_gez_middle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["amharic_middle_name"] = message.text.strip()
    await message.reply_text("Enter your Last Name in Amharic:")
    return PERSONAL_GEZZ_LASTNAME

async def handle_gez_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["amharic_last_name"] = message.text.strip()
    await message.reply_text("Enter your Birth Place: ")
    return PERSONAL_BIRTHPLACE

async def handle_birth_place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["birth_place"] = message.text.strip()
    await message.reply_text("Enter your Date of birth:(mm/dd/yyyy) or (mmddyyyy)")
    return PERSONAL_DOB

async def handle_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["dob"] = message.text.strip()
    await message.reply_text("Enter your Phone Number:")
    return PERSONAL_PHONE_NUMBER

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["phone_number"] = message.text.strip()
    context.user_data["dropdown_step"] = 0  # Reset the dropdown sequence
    return await ask_dropdown_option(update, context)

async def ask_dropdown_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    step = context.user_data.get("dropdown_step", 0)
    
    if step >= len(DROPDOWN_SEQUENCE):
        return await fill_personal_form_on_page(update, context)

    selector, label, buttons_per_row = DROPDOWN_SEQUENCE[step]
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    dropdown = page.locator(selector)
    await dropdown.wait_for()
    options = await dropdown.locator('option').all()

    valid_options = []
    for opt in options:
        value = await opt.get_attribute("value")
        text = (await opt.inner_text()).strip()
        if value and "--" not in text:
            valid_options.append((value, text))

    context.user_data["dropdown_options"] = valid_options
    context.user_data["current_dropdown_selector"] = selector

    # Create inline keyboard with specified buttons per row
    keyboard = []
    row = []
    for i, (value, text) in enumerate(valid_options, 1):
        row.append(InlineKeyboardButton(text, callback_data=f"dropdown_{step}_{value}"))
        if i % buttons_per_row == 0 or i == len(valid_options):
            keyboard.append(row)
            row = []

    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(f"Please select {label}:", reply_markup=reply_markup)

    return DROPDOWN_STATE

async def handle_dropdown_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    message = update.message or update.callback_query.message
    await query.answer()
    
    # Handle normal dropdown selection
    _, step, value = query.data.split("_")
    step = int(step)
    options = context.user_data.get("dropdown_options", [])
    selector = context.user_data.get("current_dropdown_selector")

    # Find the selected option
    selected_option = next((opt for opt in options if opt[0] == value), None)
    if not selected_option:
        await query.edit_message_text(text="❌ Invalid selection. Please try again.")
        return DROPDOWN_STATE

    value, label = selected_option
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.select_option(selector, value)
    await query.edit_message_text(text=f"✅ {label} selected.")

    # Move to next step
    context.user_data["dropdown_step"] = step + 1
    return await ask_dropdown_option(update, context)

# --- Final Form Filling on Page ---
async def fill_personal_form_on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    user_data = context.user_data
    await page.fill('input[name="firstName"]', user_data["first_name"])
    await page.fill('input[name="middleName"]', user_data["middle_name"])
    await page.fill('input[name="lastName"]', user_data["last_name"])
    await page.fill('#date-picker-dialog', '')
    await page.type('#date-picker-dialog', user_data["dob"])
    await page.fill('input[name="geezFirstName"]', user_data["amharic_first_name"])
    await page.fill('input[name="geezMiddleName"]', user_data["amharic_middle_name"])
    await page.fill('input[name="geezLastName"]', user_data["amharic_last_name"])
    await page.select_option('select[name="nationalityId"]', "ETHIOPIA")   
    await page.fill('input[name="phoneNumber"]', user_data["phone_number"])
    await page.fill('input[name="birthPlace"]', user_data["birth_place"])
    await page.get_by_role("button", name="Next").click()
    await page.wait_for_timeout(1000)
    region_select = active_sessions[chat_id]['page'].locator("select[name='region']")
    await region_select.select_option(value=user_data["region"])
    await page.fill('input[name="city"]', user_data["city"])
    # Click Next buttons
    button = page.get_by_role("button", name="Next")
    await button.wait_for(state="visible")
    await button.click()
    await button.wait_for(state="visible")
    await button.click()
    submit_button = page.get_by_role("button", name="Submit")
    await submit_button.wait_for(state="visible")
    await submit_button.click()
    return await file_upload_from_telegram(update, context)

async def file_upload_from_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    keyboard = [
        [InlineKeyboardButton("📤 Upload ID Document", callback_data="upload_id")],
        [InlineKeyboardButton("📤 Upload Birth Certificate", callback_data="upload_birth")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "📤 Please upload your documents:",
        reply_markup=reply_markup
    )
    return FILE_UPLOAD_ID_DOC

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    ALLOWED_EXTENSIONS = {'jpeg', 'jpg', 'png', 'gif', 'pdf'}
    MAX_FILE_SIZE_MB = 1
    
    if update.callback_query:
        # Handle button selection
        query = update.callback_query
        await query.answer()
        
        if query.data == "upload_id":
            context.user_data["current_file_type"] = "id_doc"
            await query.edit_message_text(text="Please upload your **Valid Resident/Gov Employee ID** (JPEG, PNG, PDF, <1MB).")
            return FILE_UPLOAD_ID_DOC
        elif query.data == "upload_birth":
            context.user_data["current_file_type"] = "birth_cert"
            await query.edit_message_text(text="Please upload your **Authenticated Birth Certificate** (JPEG, PNG, PDF, <1MB).")
            return FILE_UPLOAD_BIRTH_CERT
    
    # Handle actual file upload
    file = message.document or (message.photo[-1] if message.photo else None)

    if not file:
        await message.reply_text("❌ Please send a file (image or document).")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    if hasattr(file, "file_name"):
        ext = file.file_name.split('.')[-1].lower()
    else:
        ext = "jpg"  # for photo

    if ext not in ALLOWED_EXTENSIONS:
        await message.reply_text("❌ Unsupported file type. Use JPEG, PNG, PDF, etc.")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    if file.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text("❌ File too large. Must be less than 1MB.")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    file_path = f"downloads/{context.user_data['current_file_type']}.{ext}"
    tg_file = await file.get_file()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await tg_file.download_to_drive(file_path)

    context.user_data[context.user_data["current_file_type"]] = file_path

    if context.user_data["current_file_type"] == "id_doc":
        keyboard = [[InlineKeyboardButton("📤 Upload Birth Certificate", callback_data="upload_birth")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("✅ ID uploaded. Please upload your birth certificate:", reply_markup=reply_markup)
        return FILE_UPLOAD_BIRTH_CERT

    await message.reply_text("✅ All files received. Uploading to the form...")
    return await upload_files_to_form(update, context)

async def upload_files_to_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.set_input_files('input[name="input-0"]', context.user_data["id_doc"])
    await page.set_input_files('input[name="input-1"]', context.user_data["birth_cert"])
    await page.get_by_role("button", name="Upload").click()
    await message.reply_text("📁 Uploaded successfully.")

    await page.click('label[for="defaultUnchecked"]')
    await page.get_by_role("button", name="Next").click()

    # Next step
    return await ask_payment_method(update, context)

async def ask_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    methods = ["CBE Birr", "TELE Birr", "CBE Mobile"]
    context.user_data["payment_methods"] = methods

    keyboard = [
        [InlineKeyboardButton(method, callback_data=f"payment_{i}")] 
        for i, method in enumerate(methods)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "💳 Please select your payment method:",
        reply_markup=reply_markup
    )
    return PAYMENT_METHOD_STATE

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    message = update.message or update.callback_query.message
    await query.answer()
    
    selected_idx = int(query.data.replace("payment_", ""))
    methods = context.user_data["payment_methods"]
    selected_method = methods[selected_idx]
    
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.locator(f"div.type:has(p:has-text('{selected_method}')) p").click()
    await page.click('label[for="defaultUncheckedDisabled2"]')
    await page.get_by_role("button", name="Next").click()

    await query.edit_message_text(text=f"✅ Selected payment method: {selected_method}")
    return await generate_complete_output(update, context)

async def generate_complete_output(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.wait_for_load_state("networkidle")
    await page.wait_for_selector('div.col-md-4.order-md-2.mb-4.mt-5')

    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')
    containers = soup.select('div.col-md-4.order-md-2.mb-4.mt-5 ul.list-group.mb-3')

    data = {}
    for container in containers:
        items = container.find_all('li', class_='list-group-item')
        for item in items[1:]:  # Skip the title row
            left = item.find('h6')
            right = item.find('span') or item.find('strong')
            if left and right:
                key = left.get_text(strip=True)
                value = right.get_text(strip=True)
                data[key] = value

    # Format the message
    message_t = "📄 *Your ePassport Summary:*\n\n"
    for key, value in data.items():
        message_t += f"*{key}:* {value}\n"

    await message.reply_text(message_t, parse_mode="Markdown")

    # Extract Application Number and use as filename (sanitize it)
    app_number = data.get("Application Number", "output").replace(" ", "_")
    filename = f"{app_number}.pdf"

    return await save_pdf(update, context, page, filename=filename,app_number=app_number)

async def save_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, page, filename="output.pdf", app_number=None) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    folder = "filesdownloaded"
    os.makedirs(folder, exist_ok=True)

    pdf_path = os.path.join(folder, filename)
    await page.pdf(path=pdf_path)
    print(f"📄 PDF saved as {pdf_path}")

    # Send PDF to user
    with open(pdf_path, "rb") as pdf_file:
        await message.reply_document(document=pdf_file, filename=filename, caption="📎 Here is your instruction PDF.")
        result= await main_passport_status(page,app_number)
        if result:
            await message.reply_text(result)

        with open(f"Passport_status_{app_number}.pdf", "rb") as pdf_file:
            await message.reply_document(pdf_file, caption="Your Appointment report is ready.")
    await message.reply_text("✅ All done!")
    await message.reply_text("Thank you for using the Ethiopian Passport Booking Bot!")
    await message.reply_text("If you need further assistance, please contact support.")
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    # Close existing session if any
    if chat_id in active_sessions:
        if 'page' in active_sessions[chat_id]:
            await active_sessions[chat_id]['page'].close()
        if 'browser' in active_sessions[chat_id]:
            await active_sessions[chat_id]['browser'].close()
        if 'playwright' in active_sessions[chat_id]:
            await active_sessions[chat_id]['playwright'].stop()
        del active_sessions[chat_id]
    
    # Setup new browser session for this user
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        browser_context = await browser.new_context()
        page = await browser_context.new_page()
        
        # Store the session
        active_sessions[chat_id] = {
            'playwright': playwright,
            'browser': browser,
            'page': page,
            'last_active': datetime.now()
        }
        
        # Initialize user data
        context.user_data.clear()
        page = active_sessions[chat_id]['page']
        active_sessions[chat_id]['last_active'] = datetime.now()
        
        await page.goto("https://www.ethiopianpassportservices.gov.et/request-appointment", 
                       wait_until="domcontentloaded")
        await page.wait_for_selector("label[for='defaultChecked2']", timeout=10000)
        await page.click("label[for='defaultChecked2']")
        await page.click(".card--link")
        await page.wait_for_load_state("load")
        await page.click(".card--teal.flex.flex--column")

        await message.reply_text("Welcome to the Ethiopian Passport Booking Bot!")
        await message.reply_text(
            "Please choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Book Appointment", callback_data="book_appointment")],
                [InlineKeyboardButton("🔍 Check Passport Status", callback_data="passport_status")],
                [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
            ])
        )
        return MAIN_MENU
    except Exception as e:
        await message.reply_text(f"❌ Error initializing session: {str(e)}")
        return ConversationHandler.END

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    
    # Update last active time
    if chat_id in active_sessions:
        active_sessions[chat_id]['last_active'] = datetime.now()
    
    if query.data == "book_appointment":
        await query.edit_message_text(text="📅 Booking an appointment...")
        return await new_appointment(update, context)
    elif query.data == "passport_status":
        await query.edit_message_text(text="🔍 Checking passport status...")
        return await ask_application_number(update, context)
    elif query.data == "help":
        return await help(update, context)
    else:   
        await query.edit_message_text(text="❌ Invalid option, please try again.")

async def new_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    if chat_id not in active_sessions:
        await message.reply_text("❌ Session expired. Please /start again.")
        return ConversationHandler.END
    
    try:

        
        await message.reply_text("✅ Ready! Let's begin your appointment booking.")
        return await ask_region(update, context)
    except Exception as e:
        await message.reply_text(f"❌ Error starting appointment: {str(e)}")
        return MAIN_MENU


async def main_passport_status(page,application_number):
        await page.goto("https://www.ethiopianpassportservices.gov.et/status", wait_until="domcontentloaded")
        await page.wait_for_selector('input[placeholder="Application Number"]', timeout=5000)
        await page.fill('input[placeholder="Application Number"]', application_number)

        # Click the search button using its text and class
        await page.click('button:has-text("Search")')
        await page.wait_for_selector('a.card--link', timeout=5000)
        card = await page.query_selector('a.card--link')
        text_content = await card.inner_text()
        eye_button = await card.query_selector('div i.fa-eye')
        if eye_button:
            await eye_button.click()
        else:
            print("❌ 'Eye' icon not found.")

        await page.wait_for_timeout(3000)
        #await enforce_official_styles(page)
        await generate_official_pdf(page, application_number)
        return text_content.strip()

async def generate_official_pdf(page, application_number):
    await page.pdf(
        path=f"Passport_status_{application_number}.pdf",
        print_background=True, )

async def ask_application_number(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    await message.reply_text("Please enter your Application Number to get started.")
    return 1

async def passport_status(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    passport_number = message.text
    result= await main_passport_status(page,passport_number)
    if result:
        await message.reply_text(result)
        with open(f"Passport_status_{passport_number}.pdf", "rb") as pdf_file:
            await message.reply_document(pdf_file, caption="Your passport status report is ready.")
            await message.reply_text("✅ All done!")
    await start(update, context)        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    # Clean up browser session
    if chat_id in active_sessions:
        if 'page' in active_sessions[chat_id]:
            await active_sessions[chat_id]['page'].close()
        if 'browser' in active_sessions[chat_id]:
            await active_sessions[chat_id]['browser'].close()
        if 'playwright' in active_sessions[chat_id]:
            await active_sessions[chat_id]['playwright'].stop()
        del active_sessions[chat_id]
    
    # Clear user data
    context.user_data.clear()
    
    await message.reply_text("❌ Operation cancelled. ,Starting over...")
    await start(update, context)
    return ConversationHandler.END

async def help(update:Update,context:ContextTypes.DEFAULT_TYPE)->int:
    message = update.message or update.callback_query.message
    keyboard = [
        [InlineKeyboardButton("Book Appointment", callback_data="help_book")],
        [InlineKeyboardButton("Check Status", callback_data="help_status")],
        [InlineKeyboardButton("Cancel Appointment", callback_data="help_cancel")],
        [InlineKeyboardButton("Contact Support", callback_data="help_contact")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "I can help you with the following:",
        reply_markup=reply_markup
    )
    return HELP_MENU

HELP_MENU = 1000
async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_book":
        await query.edit_message_text(text="To book an appointment, use the /new_appointment command.\n\nFollow the prompts to select your region, city, and other details.\n\nplease make sure to have your documents ready.")
    elif query.data == "help_status":
        await query.edit_message_text(text="To check your passport status, use the /passport_status command. \n\nEnter your application number when prompted.")
    elif query.data == "help_cancel":
        await query.edit_message_text(text="To cancel your appointment, use the /cancel command. \n\nThis will clear your current session and start over.")
    elif query.data == "help_contact":
        await query.edit_message_text(text="For support, please contact us at t.me/ns_asharama")
    return ConversationHandler.END
async def cleanup_inactive_sessions():
    while True:
        try:
            now = datetime.now()
            for chat_id in list(active_sessions.keys()):
                try:
                    last_active = active_sessions[chat_id].get('last_active')
                    if last_active and now - last_active > timedelta(minutes=30):
                        # Cleanup inactive session
                        if 'page' in active_sessions[chat_id]:
                            await active_sessions[chat_id]['page'].close()
                        if 'browser' in active_sessions[chat_id]:
                            await active_sessions[chat_id]['browser'].close()
                        if 'playwright' in active_sessions[chat_id]:
                            await active_sessions[chat_id]['playwright'].stop()
                        del active_sessions[chat_id]
                except Exception as e:
                    print(f"Error cleaning up session for {chat_id}: {e}")
            await asyncio.sleep(300)  # Check every 5 minutes
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    # Create application
    application = Application.builder().token("7885486896:AAGn1eU4dEjVGo7pUw6roi9k7VrA3ym1GR4").build()
    

    # Status check handler
    check_status = ConversationHandler(
        entry_points=[
            CommandHandler("passport_status", ask_application_number),
            CallbackQueryHandler(ask_application_number, pattern="^passport_status")
        ],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, passport_status)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Main form handler
    form_handle = ConversationHandler(
        entry_points=[CommandHandler("new_appointment", new_appointment),
                    CallbackQueryHandler(new_appointment, pattern="^book_appointment")],
        states={
            # Your state handlers...
            0: [CallbackQueryHandler(ask_region_response, pattern="^region_")],
            1: [CallbackQueryHandler(ask_city_response, pattern="^city_")],
            2: [CallbackQueryHandler(ask_office_response, pattern="^office_")],
            3: [CallbackQueryHandler(ask_branch_response, pattern="^branch_")],
            4: [
                CallbackQueryHandler(ask_date_response, pattern="^date_"),
                CallbackQueryHandler(handle_time_slot, pattern="^time_")
            ],
            # Message handlers
            PERSONAL_FIRSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_first_name)],
            PERSONAL_MIDDLENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_middle_name)],
            PERSONAL_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_last_name)],
            PERSONAL_GEZZ_FIRSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gez_first_name)],
            PERSONAL_GEZZ_MIDDLENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gez_middle_name)],
            PERSONAL_GEZZ_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gez_last_name)],
            PERSONAL_BIRTHPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birth_place)],
            PERSONAL_PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)],
            PERSONAL_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dob)],
            DROPDOWN_STATE: [
                CallbackQueryHandler(handle_dropdown_response, pattern="^dropdown_"),
                CallbackQueryHandler(handle_dropdown_response),
            ],
            FILE_UPLOAD_ID_DOC: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file_upload),
                CallbackQueryHandler(handle_file_upload, pattern="^upload_")
            ],
            FILE_UPLOAD_BIRTH_CERT: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file_upload),
                CallbackQueryHandler(handle_file_upload, pattern="^upload_")
            ],
            PAYMENT_METHOD_STATE: [CallbackQueryHandler(handle_payment_method, pattern="^payment_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,  # Keep this as False since we have mixed handlers
        per_user=True,
        per_chat=True,
    )

    #help handler
    help_h= ConversationHandler(
        entry_points=[
            CommandHandler("help", help),
            CallbackQueryHandler(help, pattern="^help")
        ],
        states={
            HELP_MENU: [CallbackQueryHandler(handle_help, pattern="^help_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    # Add handlers
    application.add_handler(CommandHandler("start" , start))
    application.add_handler(form_handle)
    application.add_handler(check_status)
    application.add_handler(help_h)
    application.add_handler(CommandHandler("cancel", cancel))
    async def post_init(application):
        asyncio.create_task(cleanup_inactive_sessions())

    application.post_init = post_init
    application.run_polling()
