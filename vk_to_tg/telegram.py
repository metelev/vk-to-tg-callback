import json
import os
from pathlib import Path
import tempfile
import requests


class TelegramError(Exception):
    pass


class RetryableSend(TelegramError):
    pass


class AmbiguousSend(TelegramError):
    pass


def split_utf16(text: str, limit: int) -> tuple[str, str]:
    units = 0
    for index, char in enumerate(text):
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > limit:
            return text[:index], text[index:]
        units += size
    return text, ""


def _chunks(text: str, limit: int = 4096) -> list[str]:
    parts = []
    while text:
        head, text = split_utf16(text, limit)
        parts.append(head)
    return parts


class Telegram:
    def __init__(self, token: str, chat_id: str, media_limit_mb: int = 49, session=None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.media_limit = media_limit_mb * 1024 * 1024
        self.session = session or requests.Session()

    def _post(self, method: str, data: dict, files=None):
        try:
            response = self.session.post(
                f"{self.base}/{method}", data=data, files=files, timeout=(10, 120)
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise AmbiguousSend(type(exc).__name__) from None
        try:
            payload = response.json()
        except ValueError:
            raise AmbiguousSend("invalid Telegram response") from None
        if response.status_code == 429 or payload.get("error_code") == 429:
            raise RetryableSend("Telegram rate limit")
        if response.status_code >= 500:
            raise AmbiguousSend(f"Telegram HTTP {response.status_code}")
        if not response.ok or not payload.get("ok"):
            raise TelegramError(f"Telegram API error {payload.get('error_code', response.status_code)}")
        return payload["result"]

    def _download(self, item: dict, directory: str, index: int) -> Path:
        suffix = ".mp4" if item["type"] == "video" else ".jpg"
        path = Path(directory) / f"media-{index}{suffix}"
        limit = self.media_limit if item["type"] == "video" else min(self.media_limit, 9 * 1024 * 1024)
        try:
            with self.session.get(item["url"], stream=True, timeout=(10, 120)) as response:
                response.raise_for_status()
                length = int(response.headers.get("Content-Length", "0"))
                if length > limit:
                    raise TelegramError(f"{item['type']} exceeds upload limit")
                size = 0
                with path.open("wb") as target:
                    for chunk in response.iter_content(1024 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > limit:
                            raise TelegramError(f"{item['type']} exceeds upload limit")
                        target.write(chunk)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 429 or status >= 500:
                raise RetryableSend(f"media server HTTP {status}") from None
            raise TelegramError(f"media is unavailable: HTTP {status}") from None
        except requests.RequestException as exc:
            raise RetryableSend(f"media download failed: {type(exc).__name__}") from None
        return path

    def publish(self, text: str, media: list[dict]):
        if not media:
            return [self._post("sendMessage", {"chat_id": self.chat_id, "text": part}) for part in _chunks(text)]
        if len(media) > 10:
            raise TelegramError("a post may contain at most 10 supported media items")
        results = []
        with tempfile.TemporaryDirectory(prefix="vk-to-tg-") as directory:
            paths = [self._download(item, directory, index) for index, item in enumerate(media)]
            for batch_start in range(0, len(media), 10):
                batch = media[batch_start:batch_start + 10]
                batch_paths = paths[batch_start:batch_start + 10]
                caption, remainder = split_utf16(text, 1024) if batch_start == 0 else ("", "")
                if len(batch) == 1:
                    item = batch[0]
                    method = "sendVideo" if item["type"] == "video" else "sendPhoto"
                    field = "video" if item["type"] == "video" else "photo"
                    with batch_paths[0].open("rb") as handle:
                        data = {"chat_id": self.chat_id, "caption": caption}
                        if item["type"] == "video":
                            data["supports_streaming"] = "true"
                        results.append(self._post(method, data, {field: handle}))
                else:
                    description = []
                    handles = []
                    files = {}
                    try:
                        for offset, (item, path) in enumerate(zip(batch, batch_paths)):
                            handle = path.open("rb")
                            handles.append(handle)
                            name = f"f{offset}"
                            files[name] = (path.name, handle, "video/mp4" if item["type"] == "video" else "image/jpeg")
                            entry = {"type": item["type"], "media": f"attach://{name}"}
                            if offset == 0 and caption:
                                entry["caption"] = caption
                            if item["type"] == "video":
                                entry["supports_streaming"] = True
                            description.append(entry)
                        results.extend(self._post("sendMediaGroup", {
                            "chat_id": self.chat_id,
                            "media": json.dumps(description, ensure_ascii=False),
                        }, files))
                    finally:
                        for handle in handles:
                            handle.close()
        if media and remainder:
            for part in _chunks(remainder):
                results.append(self._post("sendMessage", {"chat_id": self.chat_id, "text": part}))
        return results

    def check(self):
        me = self._post("getMe", {})
        member = self._post("getChatMember", {"chat_id": self.chat_id, "user_id": me["id"]})
        if member.get("status") != "administrator" or not member.get("can_post_messages"):
            raise TelegramError("bot must be a channel administrator with posting permission")
        return me
