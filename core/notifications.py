import requests
import logging

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self, settings_getter=None):
        self.settings_getter = settings_getter

    def send_live_alert(self, member_name, title, slug, avatar_url=None):
        settings = self.settings_getter() if self.settings_getter else {}
        stream_url = f"https://www.idn.app/@{slug}" if not slug.startswith("http") else slug
        
        discord_url = settings.get("discord_webhook_url", "").strip()
        if discord_url:
            self._send_discord(
                discord_url,
                title=f"🔴 {member_name} Sedang LIVE di IDN App!",
                description=f"**Judul:** {title}\n**Link:** [Tonton di IDN Live]({stream_url})",
                color=0xFF0033, # JKT48 Crimson Red
                thumbnail=avatar_url
            )
            
        tg_token = settings.get("telegram_bot_token", "").strip()
        tg_chat = settings.get("telegram_chat_id", "").strip()
        if tg_token and tg_chat:
            text = f"🔴 *{member_name} Sedang LIVE di IDN App!*\n\n*Judul:* {title}\n*Link:* {stream_url}"
            self._send_telegram(tg_token, tg_chat, text)

    def send_record_complete_alert(self, member_name, title, file_name, file_size_mb, duration_str, cloud_url=None):
        settings = self.settings_getter() if self.settings_getter else {}
        discord_url = settings.get("discord_webhook_url", "").strip()
        
        cloud_info = f"\n☁️ **Cloud:** [Lihat di Cloud]({cloud_url})" if cloud_url else ""
        
        if discord_url:
            self._send_discord(
                discord_url,
                title=f"✅ Recording Selesai: {member_name}",
                description=f"**Judul:** {title}\n📁 **File:** `{file_name}`\n📦 **Ukuran:** {file_size_mb:.1f} MB\n⏱️ **Durasi:** {duration_str}{cloud_info}",
                color=0x00FF88
            )
            
        tg_token = settings.get("telegram_bot_token", "").strip()
        tg_chat = settings.get("telegram_chat_id", "").strip()
        if tg_token and tg_chat:
            tg_cloud = f"\n☁️ *Cloud:* {cloud_url}" if cloud_url else ""
            text = (
                f"✅ *Recording Selesai: {member_name}*\n\n"
                f"*Judul:* {title}\n"
                f"📁 *File:* `{file_name}`\n"
                f"📦 *Ukuran:* {file_size_mb:.1f} MB\n"
                f"⏱️ *Durasi:* {duration_str}{tg_cloud}"
            )
            self._send_telegram(tg_token, tg_chat, text)

    def _send_discord(self, webhook_url, title, description, color=0xDC2626, thumbnail=None):
        payload = {
            "embeds": [{
                "title": title,
                "description": description,
                "color": color,
                "footer": {"text": "JKT48 IDN Live Recorder Dashboard"}
            }]
        }
        if thumbnail:
            payload["embeds"][0]["thumbnail"] = {"url": thumbnail}
            
        try:
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as e:
            logger.warning(f"[Notify] Discord send failed: {e}")

    def _send_telegram(self, bot_token, chat_id, text):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.warning(f"[Notify] Telegram send failed: {e}")
