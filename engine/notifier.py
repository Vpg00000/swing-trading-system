"""
engine/notifier.py - Instant Telegram & WhatsApp order/risk alert bot dispatcher.
Supports real-time alerts for opportunity setups, trade executions, risk events, and drawdowns.
Includes dry-run/mock mode and full HTTP integration.
"""

import os
import json
import logging
import datetime
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Global log history for in-memory tracking
_NOTIFICATION_LOGS: List[Dict[str, Any]] = []

def _record_log(channel: str, alert_type: str, status: str, details: Dict[str, Any]):
    log_entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "channel": channel,
        "alert_type": alert_type,
        "status": status,
        "details": details
    }
    _NOTIFICATION_LOGS.insert(0, log_entry)
    if len(_NOTIFICATION_LOGS) > 200:
        _NOTIFICATION_LOGS.pop()
    return log_entry


class TelegramNotifier:
    """Telegram Bot API dispatcher."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None, enabled: bool = True):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = enabled

    def send_message(self, text: str, parse_mode: str = "HTML") -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "channel": "Telegram", "message": "Telegram notification is disabled."}

        if not self.bot_token or not self.chat_id:
            # Dry-run / mock dispatch mode
            logger.info(f"[Telegram Mock Dispatch] {text[:60]}...")
            _record_log("Telegram", "MOCK", "SUCCESS", {"text": text, "mock": True})
            return {
                "status": "success",
                "channel": "Telegram",
                "mode": "mock",
                "message": "Alert dispatched in mock mode (no token/chat_id configured).",
                "text": text
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                if res_body.get("ok"):
                    _record_log("Telegram", "HTTP", "SUCCESS", {"message_id": res_body.get("result", {}).get("message_id")})
                    return {"status": "success", "channel": "Telegram", "mode": "live", "response": res_body}
                else:
                    _record_log("Telegram", "HTTP", "FAILED", {"response": res_body})
                    return {"status": "error", "channel": "Telegram", "error": res_body.get("description", "Unknown Telegram API error")}
        except Exception as exc:
            logger.error(f"Telegram dispatch failed: {exc}")
            _record_log("Telegram", "HTTP", "ERROR", {"error": str(exc)})
            return {"status": "error", "channel": "Telegram", "error": str(exc)}

    def send_alert(self, alert_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        emoji_map = {
            "OPPORTUNITY": "⚡",
            "ORDER_FILL": "📈",
            "STOP_LOSS": "🚨",
            "RISK_WARNING": "⚠️",
            "DRAWDOWN": "📉",
            "CUSTOM": "🔔"
        }
        emoji = emoji_map.get(alert_type.upper(), "📢")
        symbol = data.get("symbol", "N/A")
        title = data.get("title", f"{alert_type.replace('_', ' ').title()}")
        message_body = data.get("message", "")

        text = f"<b>{emoji} [{alert_type.upper()}] {title}</b>\n"
        if symbol != "N/A":
            text += f"<b>Symbol:</b> {symbol}\n"
        if "price" in data:
            text += f"<b>Price:</b> ₹{data['price']}\n"
        if "qty" in data:
            text += f"<b>Quantity:</b> {data['qty']}\n"
        if "score" in data:
            text += f"<b>Score:</b> {data['score']}\n"
        if message_body:
            text += f"\n<i>{message_body}</i>\n"
        text += f"\n<small>Time: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</small>"

        return self.send_message(text, parse_mode="HTML")


class WhatsAppNotifier:
    """WhatsApp Twilio / Webhook dispatcher."""

    def __init__(self, account_sid: Optional[str] = None, auth_token: Optional[str] = None,
                 from_number: Optional[str] = None, to_number: Optional[str] = None, enabled: bool = True):
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        self.to_number = to_number or os.getenv("TWILIO_WHATSAPP_TO", "")
        self.enabled = enabled

    def send_message(self, text: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled", "channel": "WhatsApp", "message": "WhatsApp notification is disabled."}

        if not self.account_sid or not self.auth_token or not self.to_number:
            # Dry-run / mock dispatch mode
            logger.info(f"[WhatsApp Mock Dispatch] {text[:60]}...")
            _record_log("WhatsApp", "MOCK", "SUCCESS", {"text": text, "mock": True})
            return {
                "status": "success",
                "channel": "WhatsApp",
                "mode": "mock",
                "message": "Alert dispatched in mock mode (no Twilio credentials/phone configured).",
                "text": text
            }

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        
        from_num = self.from_number if self.from_number.startswith("whatsapp:") else f"whatsapp:{self.from_number}"
        to_num = self.to_number if self.to_number.startswith("whatsapp:") else f"whatsapp:{self.to_number}"

        payload = urllib.parse.urlencode({
            "From": from_num,
            "To": to_num,
            "Body": text
        }).encode("utf-8")

        import base64
        auth_header = "Basic " + base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode("utf-8")).decode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": auth_header
                }
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                _record_log("WhatsApp", "HTTP", "SUCCESS", {"sid": res_body.get("sid")})
                return {"status": "success", "channel": "WhatsApp", "mode": "live", "response": res_body}
        except Exception as exc:
            logger.error(f"WhatsApp dispatch failed: {exc}")
            _record_log("WhatsApp", "HTTP", "ERROR", {"error": str(exc)})
            return {"status": "error", "channel": "WhatsApp", "error": str(exc)}

    def send_alert(self, alert_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        emoji_map = {
            "OPPORTUNITY": "⚡",
            "ORDER_FILL": "📈",
            "STOP_LOSS": "🚨",
            "RISK_WARNING": "⚠️",
            "DRAWDOWN": "📉",
            "CUSTOM": "🔔"
        }
        emoji = emoji_map.get(alert_type.upper(), "📢")
        symbol = data.get("symbol", "N/A")
        title = data.get("title", f"{alert_type.replace('_', ' ').title()}")
        message_body = data.get("message", "")

        text = f"{emoji} *[{alert_type.upper()}] {title}*\n"
        if symbol != "N/A":
            text += f"*Symbol:* {symbol}\n"
        if "price" in data:
            text += f"*Price:* ₹{data['price']}\n"
        if "qty" in data:
            text += f"*Quantity:* {data['qty']}\n"
        if "score" in data:
            text += f"*Score:* {data['score']}\n"
        if message_body:
            text += f"\n_{message_body}_\n"
        text += f"\nTimestamp: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"

        return self.send_message(text)


class AlertDispatcher:
    """Central dispatcher managing Telegram & WhatsApp notifications."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {
            "telegram_enabled": True,
            "whatsapp_enabled": True,
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
            "twilio_account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
            "twilio_auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
            "twilio_whatsapp_from": os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
            "twilio_whatsapp_to": os.getenv("TWILIO_WHATSAPP_TO", "")
        }
        self.init_notifiers()

    def init_notifiers(self):
        self.telegram = TelegramNotifier(
            bot_token=self.config.get("telegram_bot_token"),
            chat_id=self.config.get("telegram_chat_id"),
            enabled=self.config.get("telegram_enabled", True)
        )
        self.whatsapp = WhatsAppNotifier(
            account_sid=self.config.get("twilio_account_sid"),
            auth_token=self.config.get("twilio_auth_token"),
            from_number=self.config.get("twilio_whatsapp_from"),
            to_number=self.config.get("twilio_whatsapp_to"),
            enabled=self.config.get("whatsapp_enabled", True)
        )

    def update_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        self.config.update(new_config)
        self.init_notifiers()
        return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        redacted = dict(self.config)
        for key in ["telegram_bot_token", "twilio_auth_token", "twilio_account_sid"]:
            if redacted.get(key):
                val = redacted[key]
                redacted[key] = val[:4] + "..." + val[-4:] if len(val) > 8 else "[REDACTED]"
        return redacted

    def dispatch_alert(self, alert_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        results = {}
        if self.config.get("telegram_enabled", True):
            results["telegram"] = self.telegram.send_alert(alert_type, data)
        if self.config.get("whatsapp_enabled", True):
            results["whatsapp"] = self.whatsapp.send_alert(alert_type, data)
        return {
            "status": "dispatched",
            "alert_type": alert_type,
            "channels": results,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    def dispatch_order_alert(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.dispatch_alert("ORDER_FILL", order_data)

    def dispatch_risk_alert(self, risk_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.dispatch_alert("RISK_WARNING", risk_data)

    def dispatch_opportunity_alert(self, opp_data: Dict[str, Any]) -> Dict[str, Any]:
        return self.dispatch_alert("OPPORTUNITY", opp_data)

    def dispatch_custom_alert(self, title: str, message: str, level: str = "INFO", extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "title": title,
            "message": message,
            "level": level
        }
        if extra_data:
            payload.update(extra_data)
        return self.dispatch_alert(level.upper(), payload)

    @staticmethod
    def get_notification_logs(limit: int = 50) -> List[Dict[str, Any]]:
        return _NOTIFICATION_LOGS[:limit]


default_dispatcher = AlertDispatcher()
