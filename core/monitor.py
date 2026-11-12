import time
import logging
import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import models

logger = logging.getLogger(__name__)

class LiveMonitor:
    def __init__(self, idn_client, recorder_manager, notifier=None):
        self.idn_client = idn_client
        self.recorder_manager = recorder_manager
        self.notifier = notifier
        
        self.scheduler = BackgroundScheduler()
        self.last_check_time = None
        self.cached_streams = []
        self.alerted_slugs = set()
        self.lock = threading.Lock()
        self.is_running = False

    def start(self, interval_seconds=20):
        if self.is_running:
            return
            
        self.scheduler.add_job(
            self.check_streams,
            'interval',
            seconds=interval_seconds,
            id='idn_live_monitor',
            replace_existing=True
        )
        self.scheduler.start()
        self.is_running = True
        logger.info(f"[Monitor] Live monitor started with interval {interval_seconds}s")
        
        # Immediate first check in background thread
        threading.Thread(target=self.check_streams, daemon=True).start()

    def stop(self):
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("[Monitor] Live monitor stopped")

    def update_interval(self, interval_seconds):
        if self.is_running:
            self.scheduler.reschedule_job(
                'idn_live_monitor',
                trigger='interval',
                seconds=max(5, int(interval_seconds))
            )
            logger.info(f"[Monitor] Interval updated to {interval_seconds}s")

    def get_cached_streams(self):
        with self.lock:
            return list(self.cached_streams)

    def check_streams(self):
        try:
            settings = models.get_settings()
            members_list = models.get_all_members()
            # Map of lowercase username -> member dict
            member_watchlist = {m["username"].lower(): m for m in members_list}
            auto_all_jkt48 = settings.get("auto_record_all_jkt48") == "1"

            raw_streams = self.idn_client.fetch_active_livestreams()
            parsed_streams = self.idn_client.parse_and_match_streams(raw_streams, member_watchlist)

            with self.lock:
                self.cached_streams = parsed_streams
                self.last_check_time = datetime.now().isoformat()

            for stream in parsed_streams:
                slug = stream.get("slug", "")
                is_jkt48 = stream.get("is_jkt48", False)
                creator = stream.get("creator", {})
                name = creator.get("name", "Member")
                title = stream.get("title", "")
                avatar = creator.get("avatar", "")
                matched_member = stream.get("matched_member")
                
                # Check for live alert notification
                if slug and slug not in self.alerted_slugs and is_jkt48:
                    self.alerted_slugs.add(slug)
                    if self.notifier:
                        self.notifier.send_live_alert(name, title, slug, avatar_url=avatar)

                # Check if we should trigger auto-recording
                should_record = False
                if is_jkt48 and auto_all_jkt48:
                    should_record = True
                elif matched_member and matched_member.get("auto_record"):
                    should_record = True

                if should_record and not self.recorder_manager.is_recording(slug):
                    logger.info(f"[Monitor] Auto-recording triggered for {name} ({slug})")
                    self.recorder_manager.start_recording(stream)

            # Cleanup old alerted slugs that are no longer live
            active_slugs = {s.get("slug") for s in parsed_streams if s.get("slug")}
            with self.lock:
                self.alerted_slugs = self.alerted_slugs.intersection(active_slugs)

        except Exception as e:
            logger.error(f"[Monitor] Error during live stream check: {e}")
