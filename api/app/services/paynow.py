import hashlib
import hmac
import urllib.parse
from urllib.parse import urlsplit

import httpx

INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"


def generate_hash(values: dict, integration_key: str) -> str:
    s = ""
    for key, value in values.items():
        if str(key).upper() == "HASH":
            continue
        s += "" if value is None else str(value)
    s += integration_key
    return hashlib.sha512(s.encode("utf-8")).hexdigest().upper()


def verify_hash(values: dict, integration_key: str) -> bool:
    if "hash" not in values and "Hash" not in values:
        return False
    received = values.get("hash") or values.get("Hash")
    # remove hash key for calc
    calc_values = {k: v for k, v in values.items() if str(k).upper() != "HASH"}
    expected = generate_hash(calc_values, integration_key)
    return hmac.compare_digest(received.upper(), expected)


def _parse_response(text: str) -> dict:
    parsed = urllib.parse.parse_qs(text, keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


def initiate_transaction(
    integration_id: str,
    integration_key: str,
    reference: str,
    amount,
    return_url: str,
    result_url: str,
    additional_info: str = "",
) -> dict:
    values = {
        "id": integration_id,
        "reference": reference,
        "amount": f"{float(amount):.2f}",
        "additionalinfo": additional_info or "",
        "returnurl": return_url,
        "resulturl": result_url,
        "status": "Message",
    }
    values["hash"] = generate_hash(values, integration_key)
    with httpx.Client(timeout=30.0) as client:
        r = client.post(INIT_URL, data=values)
        r.raise_for_status()
    resp = _parse_response(r.text)
    if "hash" in resp or "Hash" in resp:
        resp["hash_verified"] = verify_hash(resp, integration_key)
    return resp


_PAYNOW_HOSTS = {"paynow.co.zw", "www.paynow.co.zw", "secure.paynow.co.zw"}


def _validate_paynow_url(url: str, purpose: str) -> str:
    """Accept only known Paynow HTTPS hosts; never trust provider-returned URLs blindly."""
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        valid_port = parsed.port in (None, 443)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid Paynow {purpose} URL")

    if (
        parsed.scheme != "https"
        or hostname not in _PAYNOW_HOSTS
        or not valid_port
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
    ):
        raise ValueError(f"Paynow {purpose} URL must use an approved HTTPS Paynow host")
    return url


def _validate_poll_url(poll_url: str) -> str:
    return _validate_paynow_url(poll_url, "poll")


def _validate_browser_url(browser_url: str) -> str:
    return _validate_paynow_url(browser_url, "checkout")


def poll_transaction(poll_url: str, integration_key: str) -> dict:
    poll_url = _validate_poll_url(poll_url)
    with httpx.Client(timeout=30.0, follow_redirects=False) as client:
        r = client.get(poll_url)
        r.raise_for_status()
    resp = _parse_response(r.text)
    if "hash" in resp or "Hash" in resp:
        resp["hash_verified"] = verify_hash(resp, integration_key)
    return resp
