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
    "https://www.paynow.co.zw/interface/checkpayment/?guid=abc",
])
def test_poll_url_accepts_https_paynow_hosts(url):
    assert _validate_poll_url(url) == url


@pytest.mark.parametrize("url", [
    "http://paynow.co.zw/poll",
    "https://paynow.co.zw/poll",
    "https://secure.paynow.co.zw/poll",
    "https://www.paynow.co.zw:7106/poll",
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
    "https://www.paynow.co.zw/Payment/123",
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

def test_paid_confirmation_rejects_fractional_cent_amount_and_non_finite_values():
    from types import SimpleNamespace
    from app.routers.paynow import _verified_paid_confirmation

    attempt = SimpleNamespace(reference="PN-EXACT", amount="25.00")
    assert not _verified_paid_confirmation(
        {"hash_verified": True, "reference": "PN-EXACT", "amount": "25.001"},
        attempt,
    )
    assert not _verified_paid_confirmation(
        {"hash_verified": True, "reference": "PN-EXACT", "amount": "NaN"},
        attempt,
    )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0.10", "0.10"),
        ("0.30", "0.30"),
        ("10.000", "10.00"),
    ],
)
def test_paynow_amount_formatting_preserves_decimal_cents(amount, expected):
    from decimal import Decimal
    from app.services.paynow import _format_amount

    assert _format_amount(Decimal(amount)) == expected


@pytest.mark.parametrize("amount", ["0", "-1.00", "1.001", "NaN", "Infinity"])
def test_paynow_amount_formatting_rejects_invalid_precision_or_value(amount):
    from app.services.paynow import _format_amount

    with pytest.raises(ValueError):
        _format_amount(amount)


def test_polling_uses_post_and_disables_redirects(monkeypatch):
    from app.services import paynow as paynow_service

    calls = {}

    class FakeResponse:
        text = "Status=Paid&reference=PN-POST&amount=5.00"

        @staticmethod
        def raise_for_status():
            return None

    class FakeClient:
        def __init__(self, timeout, follow_redirects):
            calls["timeout"] = timeout
            calls["follow_redirects"] = follow_redirects

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url):
            calls["method"] = "POST"
            calls["url"] = url
            return FakeResponse()

        def get(self, _url):
            raise AssertionError("Paynow polling must use POST, not GET")

    monkeypatch.setattr(paynow_service.httpx, "Client", FakeClient)
    result = paynow_service.poll_transaction(
        "https://www.paynow.co.zw/interface/checkpayment/?guid=abc",
        "test-key",
    )

    assert calls["method"] == "POST"
    assert calls["follow_redirects"] is False
    assert calls["url"].startswith("https://www.paynow.co.zw/")
    assert result["Status"] == "Paid"
