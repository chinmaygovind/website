from accounts.santa import derange, mail_assignments

API = "/cis-1600/secret-santa-26/api/"


def test_nobody_draws_themselves_and_everyone_is_drawn():
    for n in range(3, 40):
        pairs = derange(range(n))
        assert all(a != b for a, b in pairs.items())
        assert sorted(pairs.values()) == list(range(n))


def join(client, name):
    return client.post(API + "signup", json={"name": name, "email": name + "@x.com"})


def test_admin_is_added_once_draws_and_nothing_is_emailed(client, logged_in, flask_app, capsys):
    assert join(client, "a").json["ok"]
    assert join(client, "a").json["already"]
    assert join(client, "").status_code == 400
    assert client.get(API + "status").json == {"count": 1, "sent": False, "admin": False}
    assert client.post(API + "draw", json={}).status_code == 404

    join(client, "b")
    logged_in("chinmay")
    for _ in range(2):
        s = client.get(API + "status").json
    assert s["me"] == "Chinmay" and s["count"] == 3 and s["pairs"] == []
    capsys.readouterr()

    assert client.post(API + "draw", json={}).json["ok"]
    s = client.get(API + "status").json
    assert len(s["pairs"]) == 3 and not s["sent"]
    assert "assignment" not in capsys.readouterr().err      # the draw mails nobody

    with flask_app.app_context():
        mail_assignments()
    assert client.get(API + "status").json["sent"]
    assert join(client, "d").status_code == 409
    assert client.post(API + "draw", json={}).status_code == 409


def test_a_late_signup_voids_the_draw(client, logged_in):
    join(client, "a"); join(client, "b")
    logged_in("chinmay")
    client.get(API + "status")
    client.post(API + "draw", json={})
    join(client, "c")
    assert client.get(API + "status").json["pairs"] == []


def test_a_stranger_sees_no_list(client, logged_in):
    logged_in("someone")
    assert client.post(API + "draw", json={}).status_code == 404
    s = client.get(API + "status").json
    assert "people" not in s and "pairs" not in s and "me" not in s
