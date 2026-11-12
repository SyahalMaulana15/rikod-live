import os
import re
import time
import uuid
import shutil
import logging
import subprocess
import threading
from datetime import datetime
from core.hls_engine import HLSRecorder

logger = logging.getLogger(__name__)

class ActiveSession:
    def __init__(self, task_id, stream_data, file_path, engine, engine_instance=None, proc=None):
        self.task_id = task_id
        self.stream_data = stream_data
        self.file_path = file_path
        self.engine = engine
        self.engine_instance = engine_instance # For native HLSRecorder
        self.proc = proc # For ffmpeg / yt-dlp subprocess
        self.chat_recorder = None # Synchronized Chat & Gift recorder
        self.start_time = time.time()
        self.status = "recording"

    def get_stats(self):
        file_size = 0
        if os.path.exists(self.file_path):
            try:
                file_size = os.path.getsize(self.file_path)
            except:
                pass
                
        elapsed = int(time.time() - self.start_time)
        speed_kbps = round((file_size / 1024) / elapsed, 2) if elapsed > 0 else 0
        
        return {
            "task_id": self.task_id,
            "member_name": self.stream_data.get("creator", {}).get("name", "Unknown"),
            "member_username": self.stream_data.get("creator", {}).get("username", ""),
            "title": self.stream_data.get("title", ""),
            "slug": self.stream_data.get("slug", ""),
            "image_url": self.stream_data.get("image_url", ""),
            "engine": self.engine,
            "status": self.status,
            "elapsed_seconds": elapsed,
            "file_size": file_size,
            "speed_kbps": speed_kbps,
            "file_path": self.file_path,
            "file_name": os.path.basename(self.file_path)
        }

class StreamRecorderManager:
    def __init__(self, settings_getter, cloud_uploader=None, notifier=None):
        self.settings_getter = settings_getter
        self.cloud_uploader = cloud_uploader
        self.notifier = notifier
        self.sessions = {} # task_id -> ActiveSession
        self.lock = threading.Lock()

    def _sanitize_filename(self, text):
        clean = re.sub(r'[\\/*?:"<>|]', "", text)
        clean = re.sub(r'\s+', "_", clean)
        return clean[:60]

    def is_recording(self, identifier):
        """Checks if a stream or member is currently being recorded."""
        with self.lock:
            for s in self.sessions.values():
                slug = s.stream_data.get("slug", "")
                username = s.stream_data.get("creator", {}).get("username", "")
                if identifier in (slug, username, s.task_id):
                    return True
        return False

    def start_recording(self, stream_data, custom_engine=None):
        settings = self.settings_getter()
        slug = stream_data.get("slug", "")
        creator = stream_data.get("creator", {})
        username = creator.get("username", "")
        name = creator.get("name", username or "JKT48_Member")
        title = stream_data.get("title", "Live_Stream")
        playback_url = stream_data.get("playback_url", "")
        
        if not playback_url:
            raise ValueError("No playback_url found for this stream.")

        if self.is_recording(slug) or self.is_recording(username):
            logger.warning(f"[Recorder] Stream for {name} ({slug}) is already being recorded.")
            return None

        # Choose engine
        engine = custom_engine or settings.get("recording_engine", "native")
        local_ffmpeg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ffmpeg.exe")
        has_ffmpeg = bool(shutil.which("ffmpeg") or os.path.exists(local_ffmpeg))

        if engine == "ffmpeg" and not has_ffmpeg:
            logger.warning("[Recorder] ffmpeg not found, falling back to native engine.")
            engine = "native"
        elif engine == "ytdlp":
            ytdlp_bin = shutil.which("yt-dlp") or r"C:\Users\ASUS\AppData\Local\Programs\Python\Python313\Scripts\yt-dlp.exe"
            if not os.path.exists(ytdlp_bin) and not shutil.which("yt-dlp"):
                logger.warning("[Recorder] yt-dlp not found, falling back to native engine.")
                engine = "native"

        # Prepare directory and filename
        storage_dir = settings.get("storage_path", "./recordings")
        os.makedirs(storage_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        # yt-dlp can only mux to mp4 if ffmpeg is present; otherwise it must save as ts
        ext = "mp4" if (has_ffmpeg and engine in ("ffmpeg", "ytdlp")) else "ts"
        file_name = f"{timestamp}_{self._sanitize_filename(name)}_{self._sanitize_filename(title)}.{ext}"
        file_path = os.path.abspath(os.path.join(storage_dir, file_name))
        
        task_id = str(uuid.uuid4())[:8]

        # Record in DB
        import models
        models.create_recording_entry(
            task_id=task_id,
            member_name=name,
            member_username=username,
            title=title,
            slug=slug,
            file_path=file_path,
            file_name=file_name,
            engine=engine
        )

        session = ActiveSession(task_id, stream_data, file_path, engine)

        # Start synchronized Chat & Gift recorder
        chat_path = os.path.splitext(file_path)[0] + ".chat.json"
        try:
            from core.chat_recorder import ChatRecorder
            chat_rec = ChatRecorder(
                slug=slug,
                output_path=chat_path,
                start_time=session.start_time,
                creator_info=creator
            )
            session.chat_recorder = chat_rec
            chat_rec.start()
        except Exception as chat_err:
            logger.warning(f"[Recorder] Could not start ChatRecorder for {slug}: {chat_err}")

        if engine == "native":
            hls = HLSRecorder(
                playback_url=playback_url,
                output_path=file_path,
                completion_callback=lambda stats: self._on_recording_finish(task_id, stats)
            )
            session.engine_instance = hls
            with self.lock:
                self.sessions[task_id] = session
            hls.start()

        elif engine == "ffmpeg":
            ffmpeg_bin = local_ffmpeg if os.path.exists(local_ffmpeg) else (shutil.which("ffmpeg") or "ffmpeg")
            cmd = [ffmpeg_bin, "-y", "-i", playback_url, "-c", "copy", "-bsf:a", "aac_adtstoasc", file_path]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            session.proc = proc
            with self.lock:
                self.sessions[task_id] = session
            threading.Thread(target=self._monitor_subprocess, args=(task_id, proc), daemon=True).start()

        elif engine == "ytdlp":
            ytdlp_bin = shutil.which("yt-dlp") or r"C:\Users\ASUS\AppData\Local\Programs\Python\Python313\Scripts\yt-dlp.exe"
            cmd = [ytdlp_bin, "--hls-prefer-native", "--no-part", "-o", file_path, playback_url]
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            session.proc = proc
            with self.lock:
                self.sessions[task_id] = session
            threading.Thread(target=self._monitor_subprocess, args=(task_id, proc), daemon=True).start()

        logger.info(f"[Recorder] Started session {task_id} for {name} ({engine}): {file_path}")
        return session.get_stats()

    def _monitor_subprocess(self, task_id, proc):
        stdout, stderr = proc.communicate()
        stats = {}
        with self.lock:
            session = self.sessions.get(task_id)
            if session:
                stats = session.get_stats()
        cli_err = stderr.strip() if (proc.returncode != 0 and stderr) else None
        if cli_err:
            logger.warning(f"[Recorder] Process error for {task_id}: {cli_err[:200]}")
        self._on_recording_finish(task_id, stats, cli_error=cli_err)

    def stop_recording(self, task_id):
        with self.lock:
            session = self.sessions.get(task_id)
            if not session:
                return False

        logger.info(f"[Recorder] Stopping session {task_id}...")
        if session.chat_recorder:
            try:
                session.chat_recorder.stop()
            except Exception as e:
                logger.warning(f"[Recorder] Error stopping chat recorder: {e}")

        if session.engine == "native" and session.engine_instance:
            session.engine_instance.stop()
        elif session.proc:
            try:
                session.proc.terminate()
                session.proc.wait(timeout=5)
            except:
                session.proc.kill()

        return True

    def _on_recording_finish(self, task_id, stats, cli_error=None):
        with self.lock:
            session = self.sessions.pop(task_id, None)

        if not session:
            return

        if session.chat_recorder:
            try:
                session.chat_recorder.stop()
            except Exception as e:
                logger.warning(f"[Recorder] Error finalizing chat recorder: {e}")

        file_path = session.file_path
        file_size = 0
        if os.path.exists(file_path):
            try:
                file_size = os.path.getsize(file_path)
            except:
                pass

        elapsed = int(time.time() - session.start_time)
        status = "completed" if file_size > 1024 else "failed"
        error_msg = cli_error or (None if status == "completed" else "Recorded file too small or empty")

        import models
        models.update_recording_status(task_id, status, file_size=file_size, duration=elapsed, error_message=error_msg)
        logger.info(f"[Recorder] Finalized session {task_id}. Size: {file_size} bytes, Duration: {elapsed}s")

        # Auto cloud upload if configured
        settings = self.settings_getter()
        if status == "completed" and settings.get("cloud_auto_upload") == "1" and self.cloud_uploader:
            models.update_recording_cloud_status(task_id, "uploading", cloud_provider=settings.get("cloud_provider"))
            
            def cloud_cb(success, cloud_url, err):
                if success:
                    models.update_recording_cloud_status(task_id, "uploaded", cloud_url=cloud_url)
                else:
                    models.update_recording_cloud_status(task_id, "failed", error_message=err)
                
                # Notification
                if self.notifier:
                    creator = session.stream_data.get("creator", {})
                    name = creator.get("name", "Member")
                    title = session.stream_data.get("title", "")
                    dur_str = f"{elapsed // 60}m {elapsed % 60}s"
                    self.notifier.send_record_complete_alert(
                        name, title, os.path.basename(file_path), file_size / (1024*1024), dur_str, cloud_url=cloud_url
                    )

            self.cloud_uploader.upload_file_async(file_path, callback=cloud_cb)
        else:
            if self.notifier and status == "completed":
                creator = session.stream_data.get("creator", {})
                name = creator.get("name", "Member")
                title = session.stream_data.get("title", "")
                dur_str = f"{elapsed // 60}m {elapsed % 60}s"
                self.notifier.send_record_complete_alert(
                    name, title, os.path.basename(file_path), file_size / (1024*1024), dur_str
                )

    def get_active_sessions(self):
        with self.lock:
            return [s.get_stats() for s in self.sessions.values()]
