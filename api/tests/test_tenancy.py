def _login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_tenancy_isolation(client, seed_two_schools):
    data = seed_two_schools
    token1 = _login(client, "owner1@test.com", "pass123")
    token2 = _login(client, "owner2@test.com", "pass123")
    h1 = {"Authorization": f"Bearer {token1}"}
    h2 = {"Authorization": f"Bearer {token2}"}

    # user1 can see own school
    r = client.get(f"/schools/{data['s1'].id}", headers=h1)
    assert r.status_code == 200
    # user1 cannot see other school
    r = client.get(f"/schools/{data['s2'].id}", headers=h1)
    assert r.status_code == 403

    # user list scoped to own school
    r = client.get("/users", headers=h1)
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "owner1@test.com" in emails
    assert "owner2@test.com" not in emails

    # admin can see both
    admin_token = _login(client, "admin@test.com", "admin123")
    ha = {"Authorization": f"Bearer {admin_token}"}
    r = client.get(f"/schools/{data['s2'].id}", headers=ha)
    assert r.status_code == 200
    r = client.get("/schools", headers=ha)
    assert r.status_code == 200
    assert len(r.json()) == 2
