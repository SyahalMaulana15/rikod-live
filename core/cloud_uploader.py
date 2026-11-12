import os
import requests
import subprocess
import threading
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class CloudUploader:
    def __init__(self, settings_getter=None):
        self.settings_getter = settings_getter

    def upload_file_async(self, file_path, metadata=None, callback=None):
        """Runs the upload in a background thread."""
        t = threading.Thread(target=self._upload_worker, args=(file_path, metadata, callback), daemon=True)
        t.start()
        return t

    def _upload_worker(self, file_path, metadata=None, callback=None):
        if not os.path.exists(file_path):
            logger.error(f"[Cloud] File not found for upload: {file_path}")
            if callback:
                callback(False, None, "File does not exist")
            return

        settings = self.settings_getter() if self.settings_getter else {}
        provider = settings.get("cloud_provider", "none")
        
        logger.info(f"[Cloud] Starting upload for {file_path} via provider '{provider}'")
        
        success = False
        cloud_url = None
        error_msg = None

        try:
            if provider == "gdrive":
                success, cloud_url, error_msg = self._upload_gdrive(file_path, settings)
            elif provider == "rclone":
                success, cloud_url, error_msg = self._upload_rclone(file_path, settings)
            elif provider == "s3":
                success, cloud_url, error_msg = self._upload_s3(file_path, settings)
            elif provider == "none":
                logger.info("[Cloud] No cloud provider configured. Skipping upload.")
                if callback:
                    callback(False, None, "Cloud provider not configured")
                return
            else:
                error_msg = f"Unknown provider: {provider}"

            # Auto-delete local copy if enabled and upload was successful
            if success and settings.get("cloud_delete_after_upload") == "1":
                try:
                    os.remove(file_path)
                    logger.info(f"[Cloud] Local file deleted after upload: {file_path}")
                except Exception as del_err:
                    logger.warning(f"[Cloud] Failed to delete local file: {del_err}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Cloud] Upload error: {e}")

        if callback:
            callback(success, cloud_url, error_msg)

    def _upload_gdrive(self, file_path, settings):
        """Uploads file using direct Google Drive Resumable Upload REST API (supports OAuth token & Service Account)."""
        service_account_json = settings.get("gdrive_service_account_json", "").strip()
        folder_id = settings.get("gdrive_folder_id", "").strip()
        oauth_token_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gdrive_token.json")

        access_token = None
        service_email = None

        try:
            import google.auth.transport.requests
            auth_req = google.auth.transport.requests.Request()

            # Priority 1: Personal Google Drive OAuth token (Uses user's own 15GB/Google One quota)
            if os.path.exists(oauth_token_path):
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_file(oauth_token_path, scopes=['https://www.googleapis.com/auth/drive'])
                if creds.expired and creds.refresh_token:
                    creds.refresh(auth_req)
                    with open(oauth_token_path, "w") as f:
                        f.write(creds.to_json())
                access_token = creds.token
                logger.info("[GDrive] Using Personal Account OAuth Credentials.")

            # Priority 2: Service Account JSON
            elif service_account_json:
                from google.oauth2 import service_account
                if os.path.exists(service_account_json):
                    creds = service_account.Credentials.from_service_account_file(
                        service_account_json, scopes=['https://www.googleapis.com/auth/drive']
                    )
                else:
                    info = json.loads(service_account_json)
                    creds = service_account.Credentials.from_service_account_info(
                        info, scopes=['https://www.googleapis.com/auth/drive']
                    )
                creds.refresh(auth_req)
                access_token = creds.token
                service_email = creds.service_account_email
                logger.info(f"[GDrive] Using Service Account: {service_email}")

            else:
                return False, None, "Kredensial Google Drive belum diatur. Masukkan Service Account JSON atau hubungkan akun pribadi."

            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            mime_type = "video/mp4" if ext == ".mp4" else "video/mp2t"

            # Step 1: Initiate Resumable Upload Session (supportsAllDrives=true allows Shared Drives)
            init_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&supportsAllDrives=true&fields=id,name,webViewLink"
            init_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(file_size)
            }

            metadata = {"name": file_name}
            if folder_id:
                metadata["parents"] = [folder_id]

            init_resp = requests.post(init_url, headers=init_headers, json=metadata, timeout=30)
            if init_resp.status_code not in (200, 201):
                err_txt = init_resp.text
                if "storageQuotaExceeded" in err_txt:
                    return False, None, "Google membatasi kuota 0 MB pada Service Account di folder Gmail pribadi biasa. Gunakan Shared Drive (Drive Bersama) atau gunakan Rclone / login akun pribadi."
                elif "File not found" in err_txt or "notFound" in err_txt or "insufficientFilePermissions" in err_txt:
                    return False, None, f"Folder ID '{folder_id}' belum dibagikan ke email Service Account ({service_email or 'bot'}) dengan akses Editor."
                return False, None, f"Google Drive Init Error ({init_resp.status_code}): {err_txt}"

            upload_location = init_resp.headers.get("Location")
            if not upload_location:
                return False, None, "Google Drive tidak mengembalikan URL upload."

            # Step 2: Upload file in 5MB chunks (resumable)
            chunk_size = 5 * 1024 * 1024
            with open(file_path, "rb") as f:
                start = 0
                while start < file_size:
                    chunk = f.read(chunk_size)
                    chunk_len = len(chunk)
                    end = start + chunk_len - 1

                    chunk_headers = {
                        "Content-Length": str(chunk_len),
                        "Content-Range": f"bytes {start}-{end}/{file_size}"
                    }

                    chunk_resp = requests.put(upload_location, headers=chunk_headers, data=chunk, timeout=180)

                    if chunk_resp.status_code in (200, 201):
                        res_data = chunk_resp.json()
                        file_id = res_data.get("id")
                        web_view_link = res_data.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
                        logger.info(f"[GDrive] Upload selesai: {file_name} -> {web_view_link}")
                        return True, web_view_link, None
                    elif chunk_resp.status_code == 308:
                        start = end + 1
                        pct = int((start / file_size) * 100)
                        logger.info(f"[GDrive] Uploading {file_name}: {pct}% ({start}/{file_size} B)")
                    else:
                        return False, None, f"GDrive Upload Error ({chunk_resp.status_code}): {chunk_resp.text}"

            return False, None, "Upload selesai namun tidak menerima konfirmasi file dari Google Drive."

        except Exception as e:
            logger.error(f"[GDrive] Upload failed: {e}")
            return False, None, str(e)

    def _upload_rclone(self, file_path, settings):
        """Uploads file using rclone CLI."""
        remote = settings.get("rclone_remote_name", "gdrive:JKT48_Live").strip()
        if not remote:
            return False, None, "Rclone remote destination is empty in Settings."

        import shutil
        local_rclone = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rclone.exe")
        rclone_bin = local_rclone if os.path.exists(local_rclone) else (shutil.which("rclone") or "rclone")

        cmd = [rclone_bin, "copy", file_path, remote, "--progress"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode == 0:
                logger.info(f"[Rclone] Uploaded to {remote}")
                return True, f"Rclone: {remote}/{os.path.basename(file_path)}", None
            else:
                return False, None, f"Rclone failed: {res.stderr[:200]}"
        except FileNotFoundError:
            return False, None, "rclone executable was not found on the system PATH or in app directory."
        except Exception as e:
            return False, None, str(e)

    def _upload_s3(self, file_path, settings):
        """Uploads file to S3 or Cloudflare R2."""
        endpoint = settings.get("s3_endpoint_url", "").strip()
        bucket = settings.get("s3_bucket_name", "").strip()
        access_key = settings.get("s3_access_key", "").strip()
        secret_key = settings.get("s3_secret_key", "").strip()
        region = settings.get("s3_region", "auto").strip() or "auto"

        if not bucket or not access_key or not secret_key:
            return False, None, "S3 Bucket, Access Key, or Secret Key is missing."

        try:
            import boto3
            session = boto3.session.Session()
            client_kwargs = {
                'service_name': 's3',
                'aws_access_key_id': access_key,
                'aws_secret_access_key': secret_key,
                'region_name': region
            }
            if endpoint:
                client_kwargs['endpoint_url'] = endpoint

            s3 = session.client(**client_kwargs)
            file_name = os.path.basename(file_path)
            s3_key = f"jkt48_recordings/{file_name}"
            
            s3.upload_file(file_path, bucket, s3_key)
            
            if endpoint:
                url = f"{endpoint}/{bucket}/{s3_key}"
            else:
                url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
                
            return True, url, None
        except ImportError:
            return False, None, "boto3 library is not installed. Run 'pip install boto3' to use S3."
        except Exception as e:
            return False, None, str(e)
