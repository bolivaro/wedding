import os
from urllib.parse import urljoin, urlparse


DEFAULT_PUBLIC_SITE_URL = "https://leslieniboli.fr"
INVALID_URL_VALUES = {"", "null", "none", "undefined"}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0"}


def normalize_public_base_url(value, *, debug=False):
    candidate = (value or "").strip().rstrip("/")
    parsed = urlparse(candidate)
    is_valid = (
        candidate.lower() not in INVALID_URL_VALUES
        and parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and (debug or parsed.hostname not in LOCAL_HOSTS)
    )
    if is_valid:
        return candidate

    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain and railway_domain.lower() not in INVALID_URL_VALUES:
        railway_url = (
            railway_domain
            if railway_domain.startswith(("http://", "https://"))
            else f"https://{railway_domain}"
        )
        parsed_railway_url = urlparse(railway_url)
        if parsed_railway_url.netloc:
            return railway_url.rstrip("/")

    return "http://127.0.0.1:8000" if debug else DEFAULT_PUBLIC_SITE_URL


def build_public_url(path, *, base_url, debug=False):
    normalized_base = normalize_public_base_url(base_url, debug=debug)
    return urljoin(f"{normalized_base}/", path.lstrip("/"))


def normalize_public_url(value, *, fallback_path, base_url, debug=False):
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if (
        candidate.lower() not in INVALID_URL_VALUES
        and parsed.scheme in {"http", "https"}
        and parsed.netloc
        and (debug or parsed.hostname not in LOCAL_HOSTS)
    ):
        return candidate
    return build_public_url(fallback_path, base_url=base_url, debug=debug)
