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
