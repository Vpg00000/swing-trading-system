"""
tests/test_telegram_bot.py - Integration tests for Telegram & WhatsApp trading bots.

Task T-304: Comprehensive tests for bot command parser, 2FA PIN, permission restriction,
interactive callbacks, voice parser, audit logger, and WhatsApp webhook adapter.
"""

import os
import pytest
import sqlite3
import tempfile
from pathlib import Path

from engine.telegram_bot import TelegramTradingBot, TelegramAuditLogger, NaturalLanguageTradeParser
from engine.whatsapp_bot import WhatsAppWebhookAdapter


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_telegram_bot_permission_locking(temp_db):
    bot = TelegramTradingBot(allowed_user_ids=["1001", "1002"], pin_2fa="9999", db_path=temp_db)
    
    # Test unauthorized user
    msg_unauth = {"from": {"id": "9999"}, "text": "/quote RELIANCE"}
    res_unauth = bot.process_message(msg_unauth)
    assert res_unauth["status"] == "unauthorized"
    assert "Access Denied" in res_unauth["response"]

    # Test authorized user
    msg_auth = {"from": {"id": "1001"}, "text": "/quote RELIANCE"}
    res_auth = bot.process_message(msg_auth)
    assert res_auth["status"] == "success"
    assert "RELIANCE" in res_auth["response"]


def test_telegram_bot_quote_command(temp_db):
    bot = TelegramTradingBot(db_path=temp_db)
    msg = {"from": {"id": "123"}, "text": "/quote TCS"}
    res = bot.process_message(msg)
    assert res["status"] == "success"
    assert "TCS" in res["response"]
    assert res["inline_keyboard"] is not None


def test_telegram_bot_trade_flow_and_2fa(temp_db):
    bot = TelegramTradingBot(pin_2fa="4321", db_path=temp_db)
    user_id = "555"

    # Step 1: Request Buy
    buy_msg = {"from": {"id": user_id}, "text": "/buy RELIANCE 10 2450"}
    res1 = bot.process_message(buy_msg)
    assert res1["status"] == "pending_2fa"
    assert "2FA Confirmation Required" in res1["response"]

    # Step 2: Submit wrong PIN
    wrong_pin_msg = {"from": {"id": user_id}, "text": "/pin 0000"}
    res2 = bot.process_message(wrong_pin_msg)
    assert res2["status"] == "error"
    assert "Invalid 2FA PIN" in res2["response"]

    # Re-trigger pending buy
    bot.process_message(buy_msg)

    # Step 3: Submit correct PIN
    correct_pin_msg = {"from": {"id": user_id}, "text": "4321"}
    res3 = bot.process_message(correct_pin_msg)
    assert res3["status"] == "executed"
    assert "Order Executed Successfully" in res3["response"]
    assert res3["order_info"]["symbol"] == "RELIANCE"
    assert res3["order_info"]["qty"] == 10


def test_telegram_bot_interactive_callbacks(temp_db):
    bot = TelegramTradingBot(pin_2fa="1234", db_path=temp_db)
    user_id = "777"

    # Callback buy button click
    cb_msg = {"from": {"id": user_id}, "data": "buy_INFY_5"}
    res1 = bot.handle_callback_query(cb_msg)
    assert res1["status"] == "pending_2fa"

    # Callback PIN confirm button
    cb_pin = {"from": {"id": user_id}, "data": "pin_1234"}
    res2 = bot.handle_callback_query(cb_pin)
    assert res2["status"] == "executed"
    assert res2["order_info"]["symbol"] == "INFY"


def test_natural_language_and_voice_parser():
    nlp_buy = NaturalLanguageTradeParser.parse_text("Buy 50 shares of TCS at 4000")
    assert nlp_buy["parsed"] is True
    assert nlp_buy["action"] == "BUY"
    assert nlp_buy["symbol"] == "TCS"
    assert nlp_buy["qty"] == 50
    assert nlp_buy["price"] == 4000.0

    nlp_sell = NaturalLanguageTradeParser.parse_text("Sell 15 HDFCBANK")
    assert nlp_sell["parsed"] is True
    assert nlp_sell["action"] == "SELL"
    assert nlp_sell["symbol"] == "HDFCBANK"

    voice_res = NaturalLanguageTradeParser.transcribe_and_parse_audio("buy 10 shares of RELIANCE")
    assert voice_res["parsed"] is True
    assert voice_res["symbol"] == "RELIANCE"


def test_telegram_audit_logger(temp_db):
    logger_inst = TelegramAuditLogger(db_path=temp_db)
    logger_inst.log_interaction(
        channel="Telegram", user_id="101", command="/quote RELIANCE",
        raw_message="/quote RELIANCE", response="Quote OK", status="SUCCESS", trade_executed=False
    )
    logs = logger_inst.get_logs()
    assert len(logs) == 1
    assert logs[0]["user_id"] == "101"
    assert logs[0]["command"] == "/quote RELIANCE"


def test_whatsapp_webhook_adapter(temp_db):
    bot_inst = TelegramTradingBot(db_path=temp_db)
    adapter = WhatsAppWebhookAdapter(verify_token="test_token", telegram_bot_ref=bot_inst)

    # Test GET Challenge verification
    challenge_res = adapter.verify_webhook_challenge("subscribe", "test_token", "challenge_123")
    assert challenge_res == "challenge_123"

    # Test incoming POST message
    payload = {
        "from_phone": "+919876543210",
        "text": "/status"
    }
    result = adapter.process_incoming_webhook(payload)
    assert result["status"] == "processed"
    assert "Portfolio & System Status" in result["bot_response"]


def test_scheduled_broadcasts(temp_db):
    bot = TelegramTradingBot(db_path=temp_db)
    morning = bot.generate_morning_briefing()
    assert morning["status"] == "broadcast_ready"
    assert "DAILY MORNING MARKET BRIEFING" in morning["text"]

    eod = bot.generate_eod_report()
    assert eod["status"] == "broadcast_ready"
    assert "END-OF-DAY P&L" in eod["text"]
