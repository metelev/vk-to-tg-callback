import requests


class VKError(Exception):
    pass


class VK:
    def __init__(self, token: str, session=None):
        self.token = token
        self.session = session or requests.Session()

    def call(self, method: str, **params):
        response = self.session.post(
            f"https://api.vk.com/method/{method}",
            data={**params, "access_token": self.token, "v": "5.199"},
            timeout=(10, 30),
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise VKError(f"VK API error {data['error'].get('error_code', 'unknown')}")
        return data["response"]

    def resolve_video(self, video: dict):
        full = video
        if not video.get("files"):
            identity = f"{video['owner_id']}_{video['id']}"
            if video.get("access_key"):
                identity += f"_{video['access_key']}"
            try:
                items = self.call("video.get", videos=identity).get("items", [])
            except (VKError, requests.RequestException, ValueError):
                return self._resolve_video_with_ytdlp(video)
            if not items:
                return self._resolve_video_with_ytdlp(video)
            full = items[0]
        files = full.get("files") or {}
        choices = []
        for name, url in files.items():
            if name.startswith("mp4_") and isinstance(url, str):
                try:
                    quality = int(name.split("_", 1)[1])
                except ValueError:
                    continue
                choices.append((quality, url))
        if not choices:
            return self._resolve_video_with_ytdlp(video)
        quality, url = max(choices)
        return {
            "url": url,
            "size": full.get("size"),
            "width": full.get("width"),
            "height": full.get("height") or quality,
            "duration": full.get("duration"),
        }

    @staticmethod
    def _resolve_video_with_ytdlp(video: dict):
        """Resolve public VK Video links when the VK API omits direct files."""
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            return None
        identity = f"{video.get('owner_id', '')}_{video.get('id', '')}"
        if video.get("access_key"):
            identity += f"_{video['access_key']}"
        url = "https://vkvideo.ru/video" + identity
        options = {"quiet": True, "no_warnings": True, "skip_download": True}
        try:
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
        except Exception:
            return None
        formats = []
        for item in info.get("formats") or []:
            if not isinstance(item, dict) or not item.get("url") or item.get("ext") != "mp4":
                continue
            if item.get("vcodec") in (None, "none") or item.get("acodec") in (None, "none"):
                continue
            height = item.get("height") or 0
            if height and height > 720:
                continue
            formats.append(item)
        if not formats:
            return None
        chosen = max(formats, key=lambda item: (item.get("height") or 0, item.get("tbr") or 0))
        return {
            "url": chosen["url"],
            "size": chosen.get("filesize") or chosen.get("filesize_approx"),
            "width": chosen.get("width"),
            "height": chosen.get("height"),
            "duration": info.get("duration"),
        }
