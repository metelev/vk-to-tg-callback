def _video_link(video: dict) -> str:
    link = f"https://vk.com/video{video.get('owner_id', '')}_{video.get('id', '')}"
    if video.get("access_key"):
        link += "?access_key=" + str(video["access_key"])
    return link


def extract_media(post: dict, vk) -> tuple[list[dict], list[str]]:
    media: list[dict] = []
    notes: list[str] = []
    for attachment in post.get("attachments") or []:
        kind = attachment.get("type")
        if kind == "photo":
            sizes = [size for size in attachment.get("photo", {}).get("sizes", []) if size.get("url")]
            if sizes:
                largest = max(sizes, key=lambda size: size.get("width", 0) * size.get("height", 0))
                media.append({"type": "photo", "url": largest["url"]})
        elif kind in ("video", "clip"):
            video = attachment.get(kind, {})
            resolved = vk.resolve_video(video)
            if resolved:
                media.append({"type": "video", **resolved})
            else:
                notes.append("Видео доступно по ссылке: " + _video_link(video))
        else:
            notes.append(f"Вложение {kind or 'unknown'} доступно в оригинале VK.")
    return media, notes
