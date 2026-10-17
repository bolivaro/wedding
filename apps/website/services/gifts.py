from urllib.parse import urlparse


PAYPAL_HOSTS = {"paypal.me", "www.paypal.me"}


def normalize_paypal_url(value):
    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in PAYPAL_HOSTS
        or not parsed.path.strip("/")
        or parsed.username
        or parsed.password
        or parsed.port
    ):
        return ""
    return candidate


def gift_options(settings):
    accounts = []
    for label, url in (
        (settings.GIFT_PAYPAL_LABEL_1, settings.GIFT_PAYPAL_URL_1),
        (settings.GIFT_PAYPAL_LABEL_2, settings.GIFT_PAYPAL_URL_2),
    ):
        normalized_url = normalize_paypal_url(url)
        if normalized_url:
            accounts.append({"label": label.strip(), "url": normalized_url})
    return {"paypal_accounts": accounts}
