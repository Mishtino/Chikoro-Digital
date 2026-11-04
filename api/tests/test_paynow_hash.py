from app.services.paynow import generate_hash, verify_hash


def test_paynow_hash_verifies_original_payload():
    key = "test-integration-secret"
    payload = {"status": "Paid", "reference": "PN-ABC123", "amount": "25.00"}
    payload["hash"] = generate_hash(payload, key)
    assert verify_hash(payload, key)


def test_paynow_hash_rejects_tampered_payload():
    key = "test-integration-secret"
    payload = {"status": "Paid", "reference": "PN-ABC123", "amount": "25.00"}
    payload["hash"] = generate_hash(payload, key)
    payload["amount"] = "2500.00"
    assert not verify_hash(payload, key)


def test_paynow_hash_rejects_missing_signature():
    assert not verify_hash({"status": "Paid", "amount": "25.00"}, "test-key")


import pytest

from app.services.paynow import _validate_poll_url


@pytest.mark.parametrize("url", [
    "https://paynow.co.zw/interface/checkpayment/?guid=abc",
    "https://www.paynow.co.zw/interface/checkpayment/?guid=abc",
    "https://secure.paynow.co.zw/interface/checkpayment/?guid=abc",
])
def test_poll_url_accepts_https_paynow_hosts(url):
    assert _validate_poll_url(url) == url


@pytest.mark.parametrize("url", [
    "http://paynow.co.zw/poll",
    "https://paynow.co.zw.evil.example/poll",
    "https://evil-paynow.co.zw/poll",
    "https://127.0.0.1/poll",
    "https://localhost/poll",
    "https://user:pass@paynow.co.zw/poll",
    "https://paynow.co.zw:8443/poll",
])
def test_poll_url_rejects_untrusted_destinations(url):
    with pytest.raises(ValueError):
        _validate_poll_url(url)


from types import SimpleNamespace

from app.routers.paynow import _verified_paid_confirmation


def test_paid_confirmation_must_match_local_reference_and_amount():
    attempt = SimpleNamespace(reference="PN-EXPECTED", amount="25.00")
    valid = {"hash_verified": True, "reference": "PN-EXPECTED", "amount": "25.00"}
    assert _verified_paid_confirmation(valid, attempt)
    assert not _verified_paid_confirmation(
        {**valid, "reference": "PN-OTHER"}, attempt
    )
    assert not _verified_paid_confirmation(
        {**valid, "amount": "250.00"}, attempt
    )
    assert not _verified_paid_confirmation(
        {"hash_verified": True, "reference": "PN-EXPECTED"}, attempt
    )

@pytest.mark.parametrize("url", [
    "https://paynow.co.zw/Payment/123",
    "https://www.paynow.co.zw/Payment/123",
    "https://secure.paynow.co.zw/Payment/123",
])
def test_browser_url_accepts_known_paynow_hosts(url):
    from app.services.paynow import _validate_browser_url
    assert _validate_browser_url(url) == url


@pytest.mark.parametrize("url", [
    "https://checkout.paynow.co.zw/Payment/123",
    "https://paynow.co.zw.evil.example/Payment/123",
    "http://www.paynow.co.zw/Payment/123",
    "https://user@www.paynow.co.zw/Payment/123",
])
def test_browser_url_rejects_untrusted_destinations(url):
    from app.services.paynow import _validate_browser_url
    with pytest.raises(ValueError):
        _validate_browser_url(url)
