import os
import json
import shutil
import logging
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
from datetime import datetime

import models
from core.idn_client import IDNClient
from core.hls_engine import HLSRecorder
from core.cloud_uploader import CloudUploader
from core.notifications import NotificationManager
from core.recorder import StreamRecorderManager
from core.monitor import LiveMonitor

# ZeroGPU keeper for Hugging Face Spaces startup validation
try:
    import spaces
    @spaces.GPU
    def _zerogpu_init():
        return True
except Exception:
    pass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("RikodLive")

# Initialize database
models.init_db()

# Startup recovery: fix orphan recordings from previous sessions
try:
    conn = models.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_path FROM recordings WHERE status = 'recording'")
    for row in cursor.fetchall():
        fp = row['file_path']
        if fp and os.path.exists(fp):
            sz = os.path.getsize(fp)
            if sz > 1024 * 1024:
                cursor.execute("UPDATE recordings SET status = 'completed', file_size = ? WHERE id = ?", (sz, row['id']))
            else:
                cursor.execute("UPDATE recordings SET status = 'stopped', file_size = ? WHERE id = ?", (sz, row['id']))
        else:
            cursor.execute("UPDATE recordings SET status = 'stopped' WHERE id = ?", (row['id'],))
    conn.commit()
    conn.close()
except Exception as cleanup_err:
    logger.warning(f"Startup recordings recovery: {cleanup_err}")

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Gradio object placeholder for Hugging Face Spaces compatibility
try:
    import gradio as gr
    demo = gr.Blocks()
except Exception:
    demo = None

# Initialize subsystems
idn_client = IDNClient()
cloud_uploader = CloudUploader(settings_getter=models.get_settings)
notifier = NotificationManager(settings_getter=models.get_settings)
recorder_manager = StreamRecorderManager(
    settings_getter=models.get_settings,
    cloud_uploader=cloud_uploader,
    notifier=notifier
)
monitor = LiveMonitor(idn_client, recorder_manager, notifier=notifier)

# Start monitor with configured interval
settings = models.get_settings()
poll_int = int(settings.get("poll_interval", 20))
monitor.start(interval_seconds=poll_int)

@app.route("/")
def index():
    return render_template("index.html")

# --- SYSTEM & STATUS ---
@app.route("/api/status")
def get_status():
    settings = models.get_settings()
    storage_path = settings.get("storage_path", "./recordings")
    
    # Calculate disk usage
    total_disk, used_disk, free_disk = 0, 0, 0
    rec_folder_size = 0
    rec_count = 0
    
    try:
        if os.path.exists(storage_path):
            usage = shutil.disk_usage(storage_path)
            total_disk, free_disk = usage.total, usage.free
            for f in os.scandir(storage_path):
                if f.is_file():
                    rec_folder_size += f.stat().st_size
                    rec_count += 1
    except Exception as e:
        logger.warning(f"Error calculating disk usage: {e}")

    return jsonify({
        "status": "online",
        "monitor_running": monitor.is_running,
        "last_check_time": monitor.last_check_time,
        "active_recordings": recorder_manager.get_active_sessions(),
        "storage": {
            "path": storage_path,
            "total_bytes": total_disk,
            "free_bytes": free_disk,
            "recordings_bytes": rec_folder_size,
            "recordings_count": rec_count
        },
        "settings": {
            "recording_engine": settings.get("recording_engine", "native"),
            "auto_record_all_jkt48": settings.get("auto_record_all_jkt48") == "1",
            "cloud_provider": settings.get("cloud_provider", "none"),
            "cloud_auto_upload": settings.get("cloud_auto_upload") == "1",
            "poll_interval": int(settings.get("poll_interval", 20))
        }
    })

# --- LIVE STREAMS ---
@app.route("/api/live")
def get_live():
    streams = monitor.get_cached_streams()
    active_sessions = {s["slug"]: s for s in recorder_manager.get_active_sessions()}
    
    for s in streams:
        slug = s.get("slug")
        s["is_recording"] = slug in active_sessions
        if s["is_recording"]:
            s["recording_stats"] = active_sessions[slug]
            
    return jsonify({
        "count": len(streams),
        "streams": streams,
        "last_check": monitor.last_check_time
    })

@app.route("/api/live/check", methods=["POST"])
def force_check():
    monitor.check_streams()
    return jsonify({"success": True, "streams": monitor.get_cached_streams()})

# --- RECORDING ACTIONS ---
@app.route("/api/record/start", methods=["POST"])
def start_record():
    data = request.json or {}
    slug = data.get("slug")
    stream_data = data.get("stream_data")
    
    # If only slug is passed, look up in cached streams
    if not stream_data and slug:
        for s in monitor.get_cached_streams():
            if s.get("slug") == slug:
                stream_data = s
                break
                
    if not stream_data:
        # Check if direct playback URL or page URL was provided
        url_input = data.get("playback_url") or data.get("url")
        if url_input:
            # If user provided a web page URL like https://www.idn.app/@.../live/...
            if "idn.app" in url_input and ".m3u8" not in url_input:
                extracted = idn_client.extract_from_page_url(url_input)
                if extracted:
                    stream_data = extracted
                    if data.get("creator_name"):
                        stream_data["creator"]["name"] = data.get("creator_name")
                    if data.get("title"):
                        stream_data["title"] = data.get("title")

            # Fallback if still not extracted or it's a direct .m3u8 URL
            if not stream_data:
                title = data.get("title", "Custom Stream")
                name = data.get("creator_name", "Member")
                stream_data = {
                    "slug": slug or f"custom-{int(datetime.now().timestamp())}",
                    "title": title,
                    "playback_url": url_input,
                    "creator": {"name": name, "username": name.lower().replace(" ", "_")}
                }

    if not stream_data:
        return jsonify({"success": False, "error": "Stream not found or no playback URL."}), 400

    try:
        custom_engine = data.get("engine")
        stats = recorder_manager.start_recording(stream_data, custom_engine=custom_engine)
        if stats:
            return jsonify({"success": True, "session": stats})
        else:
            return jsonify({"success": False, "error": "Stream is already being recorded."}), 409
    except Exception as e:
        logger.error(f"Failed to start recording: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/record/stop", methods=["POST"])
def stop_record():
    data = request.json or {}
    task_id = data.get("task_id")
    if not task_id:
        return jsonify({"success": False, "error": "task_id is required"}), 400

    success = recorder_manager.stop_recording(task_id)
    return jsonify({"success": success})

# --- RECORDINGS LIBRARY ---
@app.route("/api/recordings")
def list_recordings():
    recs = models.get_recordings(limit=200)
    # Check if files still exist on disk
    for r in recs:
        fp = r.get("file_path", "")
        r["file_exists"] = os.path.exists(fp) if fp else False
        if r["file_exists"] and r.get("file_size", 0) == 0:
            try:
                r["file_size"] = os.path.getsize(fp)
            except:
                pass
    return jsonify({"recordings": recs})

@app.route("/api/recordings/<int:rec_id>", methods=["DELETE"])
def delete_recording(rec_id):
    file_path = models.delete_recording_entry(rec_id)
    deleted_file = False
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            deleted_file = True
        except Exception as e:
            logger.warning(f"Could not delete file {file_path}: {e}")
            
        # Clean up corresponding chat json if exists
        chat_path = os.path.splitext(file_path)[0] + ".chat.json"
        if os.path.exists(chat_path):
            try:
                os.remove(chat_path)
            except Exception as e:
                logger.warning(f"Could not delete chat file {chat_path}: {e}")

    return jsonify({"success": True, "file_deleted": deleted_file})

@app.route("/api/recordings/<int:rec_id>/comments")
def get_recording_comments(rec_id):
    rec = models.get_recording_by_id(rec_id)
    if not rec or not rec.get("file_path"):
        return jsonify({"success": False, "error": "Recording not found"}), 404

    file_path = rec["file_path"]
    chat_path = os.path.splitext(file_path)[0] + ".chat.json"
    
    if os.path.exists(chat_path):
        try:
            with open(chat_path, "r", encoding="utf-8") as f:
                comments = json.load(f)
            return jsonify({"success": True, "count": len(comments), "comments": comments})
        except Exception as e:
            logger.warning(f"Error reading chat file {chat_path}: {e}")
            return jsonify({"success": False, "error": str(e), "comments": []}), 500

    return jsonify({"success": True, "count": 0, "comments": []})

@app.route("/api/recordings/<int:rec_id>/download")
def download_recording(rec_id):
    rec = models.get_recording_by_id(rec_id)
    if not rec or not rec.get("file_path") or not os.path.exists(rec["file_path"]):
        return jsonify({"error": "File not found"}), 404
        
    return send_file(rec["file_path"], as_attachment=True, download_name=rec.get("file_name"))

@app.route("/api/recordings/<int:rec_id>/playlist.m3u8")
def get_recording_playlist(rec_id):
    rec = models.get_recording_by_id(rec_id)
    if not rec or not rec.get("file_path") or not os.path.exists(rec["file_path"]):
        return jsonify({"error": "File not found"}), 404

    path = rec["file_path"]
    file_size = os.path.getsize(path)
    dur = float(rec.get("duration") or 0)
    if dur <= 0:
        # Estimate duration if 0 in db: typical IDN live is ~250 KB/sec
        dur = max(10.0, round(file_size / (250 * 1024), 2))

    target_dur = int(dur) + 5
    m3u8_content = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:{target_dur}
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:{dur:.2f},
/api/recordings/{rec_id}/stream
#EXT-X-ENDLIST
"""
    return Response(m3u8_content, mimetype="application/vnd.apple.mpegurl")

@app.route("/api/recordings/<int:rec_id>/stream")
def stream_video(rec_id):
    rec = models.get_recording_by_id(rec_id)
    if not rec or not rec.get("file_path") or not os.path.exists(rec["file_path"]):
        return jsonify({"error": "File not found"}), 404

    path = rec["file_path"]
    file_size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    content_type = "video/mp4" if ext == ".mp4" else "video/mp2t"

    range_header = request.headers.get('Range', None)
    if not range_header:
        # Full content
        def generate():
            with open(path, 'rb') as f:
                while chunk := f.read(65536):
                    yield chunk
        return Response(generate(), mimetype=content_type, headers={'Content-Length': str(file_size)})

    # Handle partial range
    byte1, byte2 = 0, None
    m = range_header.replace('bytes=', '').split('-')
    if m[0]:
        byte1 = int(m[0])
    if len(m) > 1 and m[1]:
        byte2 = int(m[1])

    if byte2 is None:
        byte2 = file_size - 1

    length = byte2 - byte1 + 1

    def generate_range():
        with open(path, 'rb') as f:
            f.seek(byte1)
            remaining = length
            while remaining > 0:
                chunk_size = min(65536, remaining)
                data = f.read(chunk_size)
                if not data:
                    break
                remaining -= len(data)
                yield data

    resp = Response(
        generate_range(),
        status=206,
        mimetype=content_type,
        direct_passthrough=True
    )
    resp.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
    resp.headers.add('Accept-Ranges', 'bytes')
    resp.headers.add('Content-Length', str(length))
    return resp

@app.route("/api/recordings/<int:rec_id>/upload", methods=["POST"])
def manual_upload(rec_id):
    rec = models.get_recording_by_id(rec_id)
    if not rec or not rec.get("file_path") or not os.path.exists(rec["file_path"]):
        return jsonify({"success": False, "error": "File not found"}), 404

    task_id = rec["task_id"]
    settings = models.get_settings()
    provider = settings.get("cloud_provider", "none")
    
    if provider == "none":
        return jsonify({"success": False, "error": "Cloud provider is set to 'None' in Settings."}), 400

    models.update_recording_cloud_status(task_id, "uploading", cloud_provider=provider)

    def upload_callback(success, cloud_url, err):
        if success:
            models.update_recording_cloud_status(task_id, "uploaded", cloud_url=cloud_url)
        else:
            models.update_recording_cloud_status(task_id, "failed", error_message=err)

    cloud_uploader.upload_file_async(rec["file_path"], callback=upload_callback)
    return jsonify({"success": True, "message": f"Upload to {provider} started in background."})

# --- MEMBERS WATCHLIST ---
@app.route("/api/members", methods=["GET"])
def list_members():
    members = models.get_all_members()
    return jsonify({"members": members})

@app.route("/api/members", methods=["POST"])
def add_new_member():
    data = request.json or {}
    name = data.get("name", "").strip()
    nickname = data.get("nickname", "").strip()
    username = data.get("username", "").strip()
    gen = data.get("generation", "").strip()
    avatar = data.get("avatar_url", "").strip()
    auto_rec = bool(data.get("auto_record", False))

    if not name or not username:
        return jsonify({"success": False, "error": "Name and Username are required"}), 400

    models.add_member(name, nickname, username, generation=gen, avatar_url=avatar, auto_record=auto_rec)
    return jsonify({"success": True})

@app.route("/api/members/<int:mem_id>/toggle", methods=["POST"])
def toggle_member_auto(mem_id):
    data = request.json or {}
    auto_record = data.get("auto_record")
    models.update_member_auto_record(mem_id, auto_record)
    return jsonify({"success": True})

@app.route("/api/members/<int:mem_id>", methods=["DELETE"])
def delete_mem(mem_id):
    models.delete_member(mem_id)
    return jsonify({"success": True})

# --- SETTINGS ---
@app.route("/api/settings", methods=["GET"])
def get_app_settings():
    s = models.get_settings()
    # Mask sensitive keys for display if needed
    return jsonify({"settings": s})

@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.json or {}
    models.update_settings_bulk(data)
    
    # If interval changed, update scheduler
    if "poll_interval" in data:
        try:
            monitor.update_interval(int(data["poll_interval"]))
        except:
            pass

    return jsonify({"success": True, "settings": models.get_settings()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print("=" * 60)
    print("🚀 Rikod Live - JKT48 IDN App Live Recorder Dashboard")
    print(f"🌐 Dashboard URL: http://localhost:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
