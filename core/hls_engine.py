import os
import time
import requests
import threading
import logging
from urllib.parse import urljoin, urlparse
from collections import deque

logger = logging.getLogger(__name__)

class HLSRecorder:
    def __init__(self, playback_url, output_path, progress_callback=None, completion_callback=None):
        self.playback_url = playback_url
        self.output_path = output_path
        self.progress_callback = progress_callback
        self.completion_callback = completion_callback
        
        self.stop_event = threading.Event()
        self.thread = None
        
        self.total_bytes = 0
        self.total_duration = 0.0
        self.start_time = None
        self.status = "idle" # idle, recording, completed, stopped, failed
        self.error_message = None
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.idn.app/"
        })

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.status = "stopped"
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

    def get_stats(self):
        elapsed = time.time() - self.start_time if self.start_time else 0
        speed_kbps = (self.total_bytes / 1024) / elapsed if elapsed > 0 else 0
        return {
            "status": self.status,
            "total_bytes": self.total_bytes,
            "total_duration": int(self.total_duration),
            "elapsed_seconds": int(elapsed),
            "speed_kbps": round(speed_kbps, 2),
            "file_path": self.output_path,
            "error_message": self.error_message
        }

    def _resolve_stream_url(self, url):
        """If master playlist, selects highest quality stream."""
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                return url
            
            content = resp.text
            if "#EXT-X-STREAM-INF" in content:
                # Master playlist: choose highest bandwidth
                best_bandwidth = -1
                best_url = None
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("#EXT-X-STREAM-INF:"):
                        # Parse bandwidth
                        bw = 0
                        for part in line.split(","):
                            if "BANDWIDTH=" in part:
                                try:
                                    bw = int(part.split("=")[1].strip())
                                except:
                                    pass
                        if i + 1 < len(lines):
                            target_line = lines[i + 1].strip()
                            if target_line and not target_line.startswith("#"):
                                if bw >= best_bandwidth:
                                    best_bandwidth = bw
                                    best_url = urljoin(url, target_line)
                if best_url:
                    logger.info(f"[HLS] Selected sub-stream with bandwidth {best_bandwidth}: {best_url}")
                    return best_url
        except Exception as e:
            logger.warning(f"[HLS] Could not parse master playlist: {e}")
        return url

    def _record_loop(self):
        self.status = "recording"
        self.start_time = time.time()
        seen_segments = deque(maxlen=2000)
        seen_set = set()
        
        target_playlist_url = self._resolve_stream_url(self.playback_url)
        consecutive_errors = 0
        max_errors = 20 # ~60 seconds of consecutive failures
        
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
        
        try:
            with open(self.output_path, "wb") as out_file:
                while not self.stop_event.is_set():
                    try:
                        resp = self.session.get(target_playlist_url, timeout=8)
                        if resp.status_code != 200:
                            consecutive_errors += 1
                            if consecutive_errors >= max_errors:
                                logger.info("[HLS] Stream playlist unavailable. Assuming stream ended.")
                                break
                            time.sleep(2)
                            continue
                        
                        consecutive_errors = 0
                        playlist_text = resp.text
                        lines = playlist_text.splitlines()
                        
                        target_duration = 3.0
                        segments_to_download = []
                        current_segment_duration = 2.0
                        
                        for line in lines:
                            line = line.strip()
                            if line.startswith("#EXT-X-TARGETDURATION:"):
                                try:
                                    target_duration = float(line.split(":")[1])
                                except:
                                    pass
                            elif line.startswith("#EXTINF:"):
                                try:
                                    current_segment_duration = float(line.split(":")[1].split(",")[0])
                                except:
                                    current_segment_duration = 2.0
                            elif line and not line.startswith("#"):
                                segment_url = urljoin(target_playlist_url, line)
                                if segment_url not in seen_set:
                                    segments_to_download.append((segment_url, current_segment_duration))
                        
                        # Download each new segment
                        for seg_url, seg_dur in segments_to_download:
                            if self.stop_event.is_set():
                                break
                            
                            try:
                                seg_resp = self.session.get(seg_url, timeout=10, stream=True)
                                if seg_resp.status_code == 200:
                                    seg_bytes = 0
                                    for chunk in seg_resp.iter_content(chunk_size=32768):
                                        if chunk:
                                            out_file.write(chunk)
                                            seg_bytes += len(chunk)
                                    out_file.flush()
                                    
                                    self.total_bytes += seg_bytes
                                    self.total_duration += seg_dur
                                    
                                    seen_segments.append(seg_url)
                                    seen_set.add(seg_url)
                                    
                                    if len(seen_segments) >= 2000:
                                        # Cleanup old items in seen_set
                                        seen_set = set(seen_segments)
                                        
                                    if self.progress_callback:
                                        self.progress_callback(self.get_stats())
                            except Exception as seg_err:
                                logger.warning(f"[HLS] Failed to download segment {seg_url}: {seg_err}")
                                
                        # Check if playlist signals end of stream
                        if "#EXT-X-ENDLIST" in playlist_text:
                            logger.info("[HLS] Stream ended (#EXT-X-ENDLIST received).")
                            self.status = "completed"
                            break
                            
                        # Sleep roughly half the target duration
                        sleep_time = max(1.5, target_duration * 0.5)
                        self.stop_event.wait(sleep_time)
                        
                    except Exception as loop_err:
                        consecutive_errors += 1
                        logger.warning(f"[HLS] Playlist fetch error: {loop_err}")
                        if consecutive_errors >= max_errors:
                            break
                        self.stop_event.wait(3)

            if self.status != "stopped":
                self.status = "completed"
                
        except Exception as file_err:
            self.status = "failed"
            self.error_message = str(file_err)
            logger.error(f"[HLS] Recorder critical error: {file_err}")
            
        finally:
            logger.info(f"[HLS] Recording finished: {self.output_path} ({self.total_bytes} bytes, {int(self.total_duration)}s)")
            if self.completion_callback:
                self.completion_callback(self.get_stats())
