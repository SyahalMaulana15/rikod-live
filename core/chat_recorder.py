import os
import json
import time
import logging
import threading
import websocket

logger = logging.getLogger(__name__)

IDN_CHAT_WS_URL = "wss://chat.idn.app"

class ChatRecorder:
    def __init__(self, slug, output_path, start_time, creator_info=None):
        """
        Records live comments and gifts synchronized with video recording.
        :param slug: Livestream slug / room identifier
        :param output_path: Destination path for .chat.json
        :param start_time: Epoch timestamp (seconds) when video recording started
        :param creator_info: Metadata dictionary for creator/streamer
        """
        self.slug = slug
        self.output_path = output_path
        self.start_time = start_time
        self.creator_info = creator_info or {}
        self.events = []
        self.lock = threading.Lock()
        self.is_running = False
        self.thread = None
        self.ws = None
        self.last_saved_count = 0

    def start(self):
        """Starts the WebSocket chat capture in a background daemon thread."""
        self.is_running = True
        # Ensure initial empty JSON file exists
        self._save_to_file()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"[ChatRecorder] Started tracking chat & gifts for slug '{self.slug}' -> {self.output_path}")

    def _format_time_str(self, offset_sec):
        total_seconds = int(offset_sec)
        mins = total_seconds // 60
        secs = total_seconds % 60
        if mins >= 60:
            hrs = mins // 60
            mins = mins % 60
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _run_loop(self):
        retry_delay = 5
        while self.is_running:
            try:
                # Setup WebSocket connection
                self.ws = websocket.WebSocketApp(
                    IDN_CHAT_WS_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                logger.debug(f"[ChatRecorder] Socket error for {self.slug}: {e}")

            if not self.is_running:
                break
            time.sleep(retry_delay)

    def _on_open(self, ws):
        logger.info(f"[ChatRecorder] Connected to IDN Chat WebSocket for {self.slug}")
        # Send room join / subscribe payload
        try:
            join_payload = {
                "event": "join",
                "room_id": self.slug,
                "payload": {
                    "client_type": "web"
                }
            }
            ws.send(json.dumps(join_payload))

            # Also try alternative topic format in case gateway uses pubsub
            sub_payload = {
                "type": "subscribe",
                "channel": f"chat:{self.slug}"
            }
            ws.send(json.dumps(sub_payload))
        except Exception as e:
            logger.warning(f"[ChatRecorder] Error sending join payload: {e}")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            self._handle_raw_event(data)
        except Exception as e:
            logger.debug(f"[ChatRecorder] Non-JSON or unparseable chat frame: {e}")

    def _handle_raw_event(self, data):
        if not isinstance(data, dict):
            return

        # Extract nested payload if wrapped
        payload = data.get("payload") or data.get("data") or data
        event_name = data.get("event") or data.get("type") or "comment"

        # Determine if it's a gift or comment
        is_gift = (
            "gift" in str(event_name).lower() or
            "gift" in payload or
            "gold" in payload or
            "virtual_gift" in payload
        )

        user_raw = (
            payload.get("user") or
            payload.get("sender") or
            payload.get("creator") or
            payload.get("author") or
            {}
        )

        user_name = user_raw.get("name") or user_raw.get("display_name") or "Anon"
        username = user_raw.get("username") or user_name.lower().replace(" ", "_")
        avatar = user_raw.get("avatar") or user_raw.get("avatar_url") or ""

        # Extract message / text
        msg_text = (
            payload.get("text") or
            payload.get("comment") or
            payload.get("message") or
            payload.get("content") or
            ""
        )

        # Extract gift details if present
        gift_info = None
        if is_gift:
            g_raw = payload.get("gift") or payload
            g_name = g_raw.get("name") or g_raw.get("gift_name") or "Virtual Gift"
            g_gold = g_raw.get("gold") or g_raw.get("gold_value") or g_raw.get("price") or 0
            g_count = g_raw.get("count") or g_raw.get("quantity") or 1
            gift_info = {
                "name": g_name,
                "gold": g_gold,
                "count": g_count
            }
            if not msg_text:
                msg_text = f"Mengirim {g_count}x {g_name}"

        # If empty comment and not a gift, ignore system ping/pong
        if not msg_text and not is_gift:
            return

        offset_sec = max(0.0, round(time.time() - self.start_time, 2))
        time_str = self._format_time_str(offset_sec)

        event_item = {
            "id": len(self.events) + 1,
            "offset_sec": offset_sec,
            "time_str": time_str,
            "type": "gift" if is_gift else "comment",
            "user": {
                "name": user_name,
                "username": username,
                "avatar": avatar
            },
            "message": msg_text,
            "gift": gift_info
        }

        with self.lock:
            self.events.append(event_item)
            should_save = len(self.events) - self.last_saved_count >= 5

        if should_save:
            self._save_to_file()

    def _save_to_file(self):
        try:
            with self.lock:
                snapshot = list(self.events)
                self.last_saved_count = len(snapshot)

            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            temp_path = self.output_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.output_path)
        except Exception as e:
            logger.warning(f"[ChatRecorder] Error saving chat file {self.output_path}: {e}")

    def stop(self):
        """Stops the chat recorder and flushes the JSON file."""
        self.is_running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self._save_to_file()
        logger.info(f"[ChatRecorder] Stopped and finalized chat file ({len(self.events)} events) -> {self.output_path}")
