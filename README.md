# Telegram Passport Bot

Telegram Passport Bot is a Python bot that helps users book Ethiopian passport appointments and check passport status through a guided Telegram conversation.

## Main Concept

The bot combines Telegram conversation handlers with Playwright browser automation. A user interacts through Telegram buttons and messages, while the bot controls the Ethiopian passport services website in the background to select locations, dates, appointment details, upload files, choose payment options, and generate PDF records.

## Core Capabilities

- Start a guided appointment booking session
- Select region, city, office, branch, date, and time slot
- Collect personal and address information
- Upload required documents
- Choose payment method
- Generate appointment and passport status PDFs
- Check passport status by application number
- Clean up inactive browser sessions

## Tech Stack

- Python
- `python-telegram-bot`
- Playwright
- BeautifulSoup
- Ethiopian date utilities
- Environment variables for runtime secrets

## Safe Setup

Create a `.env` file and keep tokens out of source code:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
```

Install dependencies and run:

```bash
pip install -r requirements.txt
python ICS_passport.py
```

## Notes

Because the bot automates a live government service, selectors and page flows may need maintenance when the website changes.
