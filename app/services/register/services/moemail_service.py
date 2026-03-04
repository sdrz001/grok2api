"""MoeMail email service for temporary inbox creation."""
from __future__ import annotations

import os
import random
import string
from typing import Tuple, Optional

import requests

from app.core.config import get_config
from app.core.logger import logger


class MoeMailService:
    """MoeMail API service wrapper for temporary email."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        email_domain: Optional[str] = None,
    ) -> None:
        self.api_url = (
            (api_url or get_config("register.moemail_api_url", "") or os.getenv("MOEMAIL_API_URL", "")).strip().rstrip("/")
        )
        self.api_key = (
            (api_key or get_config("register.moemail_api_key", "") or os.getenv("MOEMAIL_API_KEY", "")).strip()
        )
        self.email_domain = (
            (email_domain or get_config("register.moemail_domain", "") or os.getenv("MOEMAIL_DOMAIN", "")).strip()
        )

        if not all([self.api_url, self.api_key, self.email_domain]):
            raise ValueError(
                "Missing required MoeMail settings: register.moemail_api_url, register.moemail_api_key, "
                "register.moemail_domain"
            )

        # Store email_id for later fetching
        self._current_email_id: Optional[str] = None

    def _generate_random_name(self) -> str:
        letters1 = "".join(random.choices(string.ascii_lowercase, k=random.randint(4, 6)))
        numbers = "".join(random.choices(string.digits, k=random.randint(1, 3)))
        letters2 = "".join(random.choices(string.ascii_lowercase, k=random.randint(0, 5)))
        return letters1 + numbers + letters2

    def create_email(self) -> Tuple[Optional[str], Optional[str]]:
        """Create a temporary mailbox via MoeMail API. Returns (email_id, address)."""
        url = f"{self.api_url}/api/emails/generate"
        try:
            random_name = self._generate_random_name()
            res = requests.post(
                url,
                json={
                    "name": random_name,
                    "expiryTime": 3600000,  # 1 hour
                    "domain": self.email_domain,
                },
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if res.status_code == 200:
                data = res.json()
                email_id = data.get("id")
                address = data.get("address") or data.get("email")
                if email_id:
                    self._current_email_id = email_id
                    logger.info(f"[MoeMail] Created email: {address} (id: {email_id})")
                    return email_id, address
                logger.warning(f"[MoeMail] Create missing id: {data}")
            else:
                logger.warning(f"[MoeMail] Create failed: {res.status_code} - {res.text}")
        except Exception as exc:
            logger.error(f"[MoeMail] Create error ({url}): {exc}")
        return None, None

    def fetch_first_email(self, email_id: str) -> Optional[str]:
        """Fetch the first email content for the mailbox."""
        try:
            # Get email list for this mailbox
            res = requests.get(
                f"{self.api_url}/api/emails/{email_id}",
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            logger.info(f"[MoeMail] Fetch emails response: status={res.status_code}, body={res.text[:500] if res.text else 'empty'}...")
            if res.status_code == 200:
                data = res.json()
                # MoeMail returns messages in the response - try multiple possible field names
                messages = data.get("messages") or data.get("items") or data.get("data") or data.get("list") or []
                if not messages and isinstance(data, list):
                    messages = data
                
                if messages and len(messages) > 0:
                    # Get the first message - use content directly from list response
                    first_msg = messages[0]
                    content = first_msg.get("html") or first_msg.get("text") or first_msg.get("body") or first_msg.get("raw") or first_msg.get("content")
                    
                    if content:
                        logger.info(f"[MoeMail] Got email content from list (len={len(content)}): {content[:200]}...")
                        return content
                    
                    # Fallback: fetch full message if list doesn't have content
                    message_id = first_msg.get("id") or first_msg.get("messageId")
                    if message_id:
                        msg_res = requests.get(
                            f"{self.api_url}/api/emails/{email_id}/{message_id}",
                            headers={
                                "X-API-Key": self.api_key,
                                "Content-Type": "application/json",
                            },
                            timeout=15,
                        )
                        logger.info(f"[MoeMail] Fetch single message response: status={msg_res.status_code}, body={msg_res.text[:300] if msg_res.text else 'empty'}...")
                        if msg_res.status_code == 200:
                            msg_data = msg_res.json()
                            content = msg_data.get("html") or msg_data.get("text") or msg_data.get("body") or msg_data.get("raw") or msg_data.get("content")
                            if content:
                                return content
            logger.debug(f"[MoeMail] No messages found for email_id: {email_id}")
            return None
        except Exception as exc:
            logger.error(f"[MoeMail] Fetch failed: {exc}")
            return None
