import re
from urllib.parse import urlparse


PAYPAL_HOSTS = {"paypal.me", "www.paypal.me"}
IBAN_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")
BIC_RE = re.compile(r"^[A-Z0-9]{8}([A-Z0-9]{3})?$")


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


def normalize_iban(value):
    compact = re.sub(r"\s+", "", (value or "")).upper()
    if not IBAN_RE.fullmatch(compact):
        return ""
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(
        character if character.isdigit() else str(ord(character) - 55)
        for character in rearranged
    )
    if int(numeric) % 97 != 1:
        return ""
    return " ".join(compact[index:index + 4] for index in range(0, len(compact), 4))


def normalize_bic(value):
    compact = re.sub(r"\s+", "", (value or "")).upper()
    return compact if not compact or BIC_RE.fullmatch(compact) else ""


def gift_options(settings):
    iban = normalize_iban(settings.GIFT_BANK_IBAN)
    return {
        "paypal_url": normalize_paypal_url(settings.GIFT_PAYPAL_URL),
        "bank": {
            "account_holder": settings.GIFT_BANK_ACCOUNT_HOLDER.strip(),
            "iban": iban,
            "bic": normalize_bic(settings.GIFT_BANK_BIC),
        } if iban else None,
    }
