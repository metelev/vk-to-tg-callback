from dataclasses import dataclass
import os
from pathlib import Path


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid .env line {number}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


@dataclass(frozen=True)
class Config:
    vk_group_id: int
    vk_callback_secret: str
    vk_confirmation: str
    vk_user_token: str
    telegram_bot_token: str
    telegram_chat_id: str
    callback_path: str = "/vk/callback"
    listen_host: str = "127.0.0.1"
    listen_port: int = 8080
    database_path: str = "data/state.sqlite3"
    media_limit_mb: int = 49

    @classmethod
    def load(cls, path: str = ".env") -> "Config":
        values = _read_env(Path(path))
        values.update(os.environ)
        required = [
            "VK_GROUP_ID", "VK_CALLBACK_SECRET", "VK_CONFIRMATION",
            "VK_USER_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        ]
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError("Missing configuration: " + ", ".join(missing))
        callback_path = values.get("CALLBACK_PATH", "/vk/callback")
        if not callback_path.startswith("/") or "?" in callback_path:
            raise ValueError("CALLBACK_PATH must be an absolute URL path")
        return cls(
            vk_group_id=int(values["VK_GROUP_ID"]),
            vk_callback_secret=values["VK_CALLBACK_SECRET"],
            vk_confirmation=values["VK_CONFIRMATION"],
            vk_user_token=values["VK_USER_TOKEN"],
            telegram_bot_token=values["TELEGRAM_BOT_TOKEN"],
            telegram_chat_id=values["TELEGRAM_CHAT_ID"],
            callback_path=callback_path,
            listen_host=values.get("LISTEN_HOST", "127.0.0.1"),
            listen_port=int(values.get("LISTEN_PORT", "8080")),
            database_path=values.get("DATABASE_PATH", "data/state.sqlite3"),
            media_limit_mb=min(int(values.get("MEDIA_LIMIT_MB", "49")), 49),
        )
