"""SMS sending (OTP). Dev mode prints to the server console.

Production: implement send_sms() with an Indian DLT-registered SMS provider (MSG91, Gupshup,
Twilio, Exotel…). India requires DLT registration of sender ID and OTP template.
"""
import logging

from .config import settings

log = logging.getLogger("selfx.sms")


def send_sms(phone: str, text: str) -> bool:
    if settings.sms_provider == "dev":
        log.warning("DEV SMS to %s: %s", phone, text)
        return True
    # TODO: call provider API here (MSG91 / Twilio). Return True on success.
    log.error("SMS provider %s not configured", settings.sms_provider)
    return False
