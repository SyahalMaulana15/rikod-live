import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Multi-Source Endpoints
CRST_IDN_LIVES_ENDPOINT = "https://api.crstlnz.my.id/api/idn_lives"
IDN_GRAPHQL_ENDPOINT = "https://api.idn.app/graphql"

GRAPHQL_QUERY = """
query GetLivestreams {
  getLivestreams {
    slug
    title
    image_url
    view_count
    playback_url
    status
    live_at
    creator {
      uuid
      name
      username
      avatar
      is_verified
    }
  }
}
"""

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://www.idn.app",
    "Referer": "https://www.idn.app/",
    "Accept": "application/json, text/plain, */*"
}

class IDNClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_active_livestreams(self, timeout=8):
        """
        Fetches active live streams using multi-source fallbacks:
        1. JKT48 Community Live API (api.crstlnz.my.id)
        2. IDN App Official GraphQL API (api.idn.app/graphql)
        Merges results and eliminates duplicates.
        """
        all_streams = []
        seen_slugs = set()

        # --- Source 1: JKT48 Live Tracker API ---
        try:
            resp = self.session.get(CRST_IDN_LIVES_ENDPOINT, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                # Could be a list directly or inside 'data'
                items = data if isinstance(data, list) else data.get("data", [])
                if isinstance(items, list):
                    for item in items:
                        normalized = self._normalize_crst_stream(item)
                        if normalized and normalized.get("slug"):
                            slug = normalized["slug"]
                            if slug not in seen_slugs:
                                seen_slugs.add(slug)
                                all_streams.append(normalized)
                    logger.info(f"[IDNClient] Source 1 (crstlnz) returned {len(all_streams)} JKT48 live streams.")
            else:
                logger.warning(f"[IDNClient] Source 1 returned status {resp.status_code}")
        except Exception as e:
            logger.info(f"[IDNClient] Source 1 (crstlnz) check note: {e}")

        # --- Source 2: Official IDN App GraphQL ---
        try:
            payload = {"query": GRAPHQL_QUERY}
            resp = self.session.post(IDN_GRAPHQL_ENDPOINT, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and "getLivestreams" in data["data"]:
                    items = data["data"]["getLivestreams"] or []
                    for item in items:
                        slug = item.get("slug", "")
                        if slug and slug not in seen_slugs:
                            seen_slugs.add(slug)
                            all_streams.append(item)
                    logger.info(f"[IDNClient] Source 2 (api.idn.app) fetched {len(items)} streams.")
                elif "errors" in data:
                    logger.warning(f"[IDNClient] GraphQL errors: {data['errors']}")
            else:
                logger.warning(f"[IDNClient] Source 2 HTTP {resp.status_code}")
        except Exception as e:
            logger.info(f"[IDNClient] Source 2 (api.idn.app) check note: {e}")

        return all_streams

    def _normalize_crst_stream(self, item):
        """Maps crstlnz JSON structure to standard stream structure."""
        if not isinstance(item, dict):
            return None

        # User / Creator info
        user = item.get("user") or item.get("creator") or item.get("member") or {}
        name = user.get("name") or item.get("name") or "JKT48 Member"
        username = (user.get("username") or item.get("username") or "").lower()
        avatar = user.get("avatar") or user.get("avatar_url") or user.get("img_url") or ""

        title = item.get("title") or "Live Streaming"
        slug = item.get("slug") or item.get("room_id") or str(item.get("id", ""))
        playback_url = item.get("playback_url") or item.get("stream_url") or item.get("streaming_url") or ""
        image_url = item.get("image_url") or item.get("image") or item.get("cover") or avatar
        view_count = item.get("view_count") or item.get("viewers") or item.get("views") or 0

        # If username doesn't have _jkt48, append if it's from this tracker
        if username and not username.endswith("jkt48"):
            username = f"{username}_jkt48"

        return {
            "slug": slug,
            "title": title,
            "image_url": image_url,
            "view_count": view_count,
            "playback_url": playback_url,
            "status": "live",
            "live_at": item.get("live_at") or item.get("started_at") or datetime.now().isoformat(),
            "creator": {
                "uuid": user.get("uuid") or user.get("id") or "",
                "name": name,
                "username": username,
                "avatar": avatar,
                "is_verified": True
            },
            # Explicitly mark as JKT48 because it came from the JKT48 tracker
            "is_jkt48_source": True
        }

    def parse_and_match_streams(self, raw_streams, member_watchlist):
        """
        Enriches streams with JKT48 detection and watchlist matching.
        member_watchlist: dict of lowercase username -> member_data
        """
        parsed = []
        
        # Build quick nickname / normalized lookup map
        nick_map = {}
        for u, m in member_watchlist.items():
            nick = (m.get("nickname") or "").lower()
            name_parts = (m.get("name") or "").lower().split()
            if nick:
                nick_map[nick] = m
            for p in name_parts:
                if len(p) >= 3 and p not in ("jkt48", "the", "van"):
                    nick_map[p] = m

        for s in raw_streams:
            creator = s.get("creator") or {}
            c_name = creator.get("name", "")
            c_username = (creator.get("username", "") or "").lower()
            title = s.get("title", "")
            slug = s.get("slug", "")
            playback_url = s.get("playback_url", "")
            
            # Clean username tokens: remove "_jkt48", "jkt48-", "jkt48_"
            clean_user = c_username.replace("_jkt48", "").replace("jkt48_", "").replace("jkt48-", "").replace("-jkt48", "").strip()

            is_jkt48 = s.get("is_jkt48_source", False)
            matched_member = None

            # 1. Direct match with watchlist username or clean username
            if c_username in member_watchlist:
                is_jkt48 = True
                matched_member = member_watchlist[c_username]
            elif clean_user and f"{clean_user}_jkt48" in member_watchlist:
                is_jkt48 = True
                matched_member = member_watchlist[f"{clean_user}_jkt48"]
            elif clean_user in nick_map:
                is_jkt48 = True
                matched_member = nick_map[clean_user]
            
            # 2. Check "jkt48" keyword anywhere
            if not is_jkt48:
                if "jkt48" in c_username or "jkt48" in c_name.lower() or "jkt48" in title.lower():
                    is_jkt48 = True

            # 3. Match by nickname or parts of full name in creator name/title
            if not matched_member:
                for nick, m in nick_map.items():
                    if nick in c_name.lower() or nick in c_username or (len(nick) >= 4 and nick in title.lower()):
                        is_jkt48 = True
                        matched_member = m
                        break

            # If JKT48 but not matched to a specific roster item, create a pseudo match
            auto_rec = False
            if matched_member:
                auto_rec = bool(matched_member.get("auto_record", False))
                # Update creator avatar if available
                if not creator.get("avatar") and matched_member.get("avatar_url"):
                    creator["avatar"] = matched_member["avatar_url"]

            parsed.append({
                "slug": slug,
                "title": title,
                "image_url": s.get("image_url", ""),
                "view_count": s.get("view_count", 0),
                "playback_url": playback_url,
                "status": s.get("status", "live"),
                "live_at": s.get("live_at", datetime.now().isoformat()),
                "creator": {
                    "uuid": creator.get("uuid", ""),
                    "name": c_name or (matched_member.get("name") if matched_member else "JKT48 Member"),
                    "username": c_username,
                    "avatar": creator.get("avatar", ""),
                    "is_verified": creator.get("is_verified", False)
                },
                "is_jkt48": is_jkt48,
                "matched_member": matched_member,
                "auto_record": auto_rec
            })

        # Sort: JKT48 members first, then by view count
        parsed.sort(key=lambda x: (not x["is_jkt48"], -x["view_count"]))
        return parsed

    def extract_from_page_url(self, page_url, timeout=10):
        """
        Extracts stream metadata and playback_url directly from an IDN App live web page HTML
        by parsing __NEXT_DATA__ JSON or page regex.
        Supports URLs like: https://www.idn.app/@freya_jkt48/live/xyz or https://www.idn.app/live/xyz
        """
        try:
            resp = self.session.get(page_url, timeout=timeout)
            if resp.status_code != 200:
                logger.warning(f"[IDNClient] Page URL returned HTTP {resp.status_code}")
                return None

            html = resp.text
            
            # 1. Search for Next.js __NEXT_DATA__
            import re
            match = re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>', html, re.DOTALL)
            if match:
                try:
                    next_data = json.loads(match.group(1))
                    page_props = next_data.get("props", {}).get("pageProps", {})
                    # Check common keys for live data
                    live_obj = (
                        page_props.get("livestream") or 
                        page_props.get("live") or 
                        page_props.get("liveData") or 
                        page_props.get("data") or 
                        page_props
                    )
                    
                    playback_url = (
                        live_obj.get("playback_url") or 
                        live_obj.get("stream_url") or 
                        live_obj.get("streaming_url") or ""
                    )
                    
                    creator = live_obj.get("creator") or live_obj.get("user") or {}
                    name = creator.get("name") or "JKT48 Member"
                    username = (creator.get("username") or "").lower()
                    title = live_obj.get("title") or "Live Stream"
                    slug = live_obj.get("slug") or page_url.split("/")[-1]

                    if playback_url:
                        logger.info(f"[IDNClient] Successfully extracted stream from __NEXT_DATA__: {name} ({playback_url})")
                        return {
                            "slug": slug,
                            "title": title,
                            "playback_url": playback_url,
                            "creator": {"name": name, "username": username},
                            "image_url": live_obj.get("image_url", "")
                        }
                except Exception as json_err:
                    logger.warning(f"[IDNClient] Error parsing __NEXT_DATA__: {json_err}")

            # 2. Direct regex search for m3u8
            m3u8_match = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m3u8_match:
                m3u8_url = m3u8_match.group(1)
                logger.info(f"[IDNClient] Found m3u8 in page HTML regex: {m3u8_url}")
                return {
                    "slug": page_url.split("/")[-1],
                    "title": "Live Stream",
                    "playback_url": m3u8_url,
                    "creator": {"name": "JKT48 Member", "username": "idn_member"},
                    "image_url": ""
                }

        except Exception as e:
            logger.error(f"[IDNClient] Failed to extract from page URL: {e}")

        return None

