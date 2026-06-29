#!/usr/bin/env python3
"""
Telegram Auth Setup — jalankan SATU KALI dari terminal Mac.

Usage:
    cd ~/mcp-atila
    venv/bin/pip install telethon
    TELEGRAM_API_ID=12345 TELEGRAM_API_HASH=abcdef... venv/bin/python scripts/telegram_auth.py

Atau set env vars dulu di ~/.zshrc / ~/.bash_profile:
    export TELEGRAM_API_ID=12345
    export TELEGRAM_API_HASH=abcdef...

Cara dapat API ID & Hash:
    1. Buka https://my.telegram.org
    2. Login dengan nomor HP Telegram kamu
    3. Klik "API development tools"
    4. Isi form (App title & Short name bebas, misal "mcp-atila")
    5. Copy api_id (angka) dan api_hash (string hex)
"""
import asyncio
import os
import sys

SESSION_FILE = os.path.expanduser("~/.mcp_atila_telegram.session")

try:
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError
except ImportError:
    print("ERROR: telethon belum terinstall.")
    print("Jalankan: venv/bin/pip install telethon")
    sys.exit(1)

api_id   = os.environ.get("TELEGRAM_API_ID", "")
api_hash = os.environ.get("TELEGRAM_API_HASH", "")

if not api_id or not api_hash:
    print("ERROR: Environment variables belum di-set.")
    print()
    print("Set dulu:")
    print("  export TELEGRAM_API_ID=<angka dari my.telegram.org>")
    print("  export TELEGRAM_API_HASH=<hash dari my.telegram.org>")
    print()
    print("Lalu jalankan script ini lagi.")
    sys.exit(1)


async def main():
    print(f"Session akan disimpan di: {SESSION_FILE}")
    print()

    client = TelegramClient(SESSION_FILE, int(api_id), api_hash)
    await client.start()

    # Kalau belum login, Telethon otomatis minta nomor HP + OTP
    if not await client.is_user_authorized():
        phone = input("Nomor HP (format internasional, contoh +6281234567890): ")
        await client.send_code_request(phone)
        code = input("Kode OTP dari Telegram: ")
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            password = input("2FA Password: ")
            await client.sign_in(password=password)

    me = await client.get_me()
    print()
    print(f"✅ Login berhasil sebagai: {me.first_name} ({me.username or me.phone})")
    print(f"✅ Session tersimpan di: {SESSION_FILE}")
    print()
    print("Sekarang tambahkan ke Claude Desktop config (~/.config/claude/claude_desktop_config.json):")
    print(f'    "TELEGRAM_API_ID": "{api_id}",')
    print(f'    "TELEGRAM_API_HASH": "{api_hash}"')
    print()
    print("Lalu restart MCP server — tools telegram_* siap dipakai!")

    await client.disconnect()


asyncio.run(main())
