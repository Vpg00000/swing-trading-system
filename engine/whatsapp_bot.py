"""
engine/whatsapp_bot.py - WhatsApp Business API notification webhook adapter.

Task T-300: WhatsApp Business API notification webhook adapter for trading bot interactions,
command parsing, 2FA, and alerts.
"""

import os
import json
import logging
import datetime
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List, Union
from engine.telegram_bot import TelegramTradingBot, TelegramAuditLogger, NaturalLanguageTradeParser

logger = logging.getLogger(__name__)


class WhatsAppWebhookAdapter:
    """Adapter handling WhatsApp Business API & Twilio webhooks (T-300)."""

    def __init__(self, verify_token: Optional[str] = None, allowed_phone_numbers: Optional[List[str]] = None,
                 telegram_bot_ref: Optional[TelegramTradingBot] = None):
        self.verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "swing_trading_secret_token")
        
        raw_allowed = os.getenv("WHATSAPP_ALLOWED_PHONES", "")
        if allowed_phone_numbers is not None:
            self.allowed_phones = [str(p).strip() for p in allowed_phone_numbers]
        elif raw_allowed:
            self.allowed_phones = [p.strip() for p in raw_allowed.split(",") if p.strip()]
        else:
            self.allowed_phones = []

        self.trading_bot = telegram_bot_ref or TelegramTradingBot()
        self.audit_logger = TelegramAuditLogger()

    def verify_webhook_challenge(self, mode: str, token: str, challenge: str) -> Union[str, bool]:
        """
        Meta WhatsApp Business API GET webhook verification handler.
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("WhatsApp webhook verified successfully!")
            return challenge
        return False

    def is_phone_allowed(self, phone: str) -> bool:
        """Permission check for incoming WhatsApp phone numbers."""
        if not self.allowed_phones:
            return True
        clean_phone = phone.replace("whatsapp:", "").replace("+", "").strip()
        for allowed in self.allowed_phones:
            if allowed.replace("+", "").strip() in clean_phone:
                return True
        return False

    def process_incoming_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes incoming POST webhook from Meta WhatsApp API or Twilio WhatsApp adapter.
        """
        sender_phone = "unknown"
        message_text = ""
        is_audio = False
        media_url = None

        # Check Meta WhatsApp API structure
        if "entry" in payload:
            try:
                changes = payload["entry"][0]["changes"][0]["value"]
                messages = changes.get("messages", [])
                if messages:
                    msg = messages[0]
                    sender_phone = msg.get("from", "unknown")
                    if msg.get("type") == "text":
                        message_text = msg.get("text", {}).get("body", "")
                    elif msg.get("type") == "audio" or msg.get("type") == "voice":
                        is_audio = True
                        media_url = msg.get("audio", {}).get("id", "")
                        message_text = "voice trade command"
            except Exception as exc:
                logger.error(f"Error parsing Meta WhatsApp payload: {exc}")

        # Check Twilio webhook structure
        elif "From" in payload or "Body" in payload:
            sender_phone = payload.get("From", "unknown").replace("whatsapp:", "")
            message_text = payload.get("Body", "").strip()
            if payload.get("NumMedia") and int(payload.get("NumMedia", 0)) > 0:
                is_audio = True
                media_url = payload.get("MediaUrl0", "")

        # Check direct test dictionary
        else:
            sender_phone = payload.get("from_phone", payload.get("sender", "unknown"))
            message_text = payload.get("text", payload.get("message", "")).strip()

        # Check Phone Lock Permission
        if not self.is_phone_allowed(sender_phone):
            resp = "⛔ Access Denied: Your phone number is not authorized to interact with this trading system."
            self.audit_logger.log_interaction("WhatsApp", sender_phone, "UNAUTHORIZED", message_text, resp, status="DENIED")
            return {"status": "unauthorized", "response": resp}

        # Process Audio if present
        if is_audio:
            parsed = NaturalLanguageTradeParser.transcribe_and_parse_audio(media_url or message_text)
            if parsed.get("parsed"):
                action = parsed["action"]
                symbol = parsed["symbol"]
                qty = parsed["qty"]
                message_text = f"/{action.lower()} {symbol} {qty}"

        # Delegate command to central trading bot logic
        bot_message_input = {
            "from": {"id": sender_phone, "username": f"wa_{sender_phone}"},
            "user_id": sender_phone,
            "chat": {"id": sender_phone},
            "text": message_text
        }

        bot_result = self.trading_bot.process_message(bot_message_input)
        
        # Log to SQLite audit log
        self.audit_logger.log_interaction(
            channel="WhatsApp",
            user_id=sender_phone,
            command=message_text,
            raw_message=json.dumps(payload),
            response=bot_result.get("response", ""),
            status=bot_result.get("status", "SUCCESS"),
            chat_id=sender_phone,
            trade_executed=(bot_result.get("status") == "executed")
        )

        return {
            "status": "processed",
            "sender_phone": sender_phone,
            "bot_response": bot_result.get("response"),
            "raw_bot_result": bot_result
        }

    def send_whatsapp_message(self, to_phone: str, text: str) -> Dict[str, Any]:
        """Dispatches WhatsApp message to recipient phone."""
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        from_num = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

        if not account_sid or not auth_token:
            logger.info(f"[WhatsApp Mock Send to {to_phone}]: {text[:60]}...")
            return {"status": "mock_sent", "to": to_phone, "text": text}

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        
        to_num = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
        from_formatted = from_num if from_num.startswith("whatsapp:") else f"whatsapp:{from_num}"

        payload = urllib.parse.urlencode({
            "From": from_formatted,
            "To": to_num,
            "Body": text
        }).encode("utf-8")

        import base64
        auth_header = "Basic " + base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("utf-8")

        try:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": auth_header}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {"status": "sent", "sid": res_data.get("sid")}
        except Exception as exc:
            logger.error(f"WhatsApp send failed: {exc}")
            return {"status": "error", "error": str(exc)}
