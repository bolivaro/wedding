import re
from urllib.parse import parse_qs, urlparse


YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
YOUTUBE_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}


def extract_youtube_video_id(value):
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        return ""

    video_id = ""
    if parsed.hostname in YOUTUBE_SHORT_HOSTS:
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.hostname in YOUTUBE_HOSTS:
        path_parts = parsed.path.strip("/").split("/")
        if parsed.path.rstrip("/") == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(path_parts) == 2 and path_parts[0] in {"embed", "shorts"}:
            video_id = path_parts[1]

    return video_id if YOUTUBE_ID_RE.fullmatch(video_id) else ""


def youtube_video_context(value):
    video_id = extract_youtube_video_id(value)
    if not video_id:
        return None
    return {
        "id": video_id,
        "watch_url": f"https://youtu.be/{video_id}",
        "embed_url": (
            f"https://www.youtube-nocookie.com/embed/{video_id}"
            "?playsinline=1&rel=0"
        ),
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
    }
