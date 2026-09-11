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
                return None
            if not items:
                return None
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
            return None
        quality, url = max(choices)
        return {
            "url": url,
            "size": full.get("size"),
            "width": full.get("width"),
            "height": full.get("height") or quality,
            "duration": full.get("duration"),
        }
