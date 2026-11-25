import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    main.Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "db", main.StudentDatabase(engine))
    monkeypatch.setattr(main, "auth_db", main.UserDatabase(engine))
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()


@pytest.fixture
def student_data():
    return {
        "last_name": "Иванов", "first_name": "Петр", "faculty": "ФПМИ",
        "course": "Физика", "grade": 85,
    }


def register_and_login(
    client, username="ivanov", password="strongpassword123"
):
    credentials = {"username": username, "password": password}
    register = client.post("/auth/register", json=credentials)
    assert register.status_code == 201
    login = client.post("/auth/login", json=credentials)
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


def test_unauthorized_student_routes(client, student_data):
    requests = [
        ("get", "/students", None),
        ("get", "/students/1", None),
        ("post", "/students", student_data),
        ("put", "/students/1", student_data),
        ("delete", "/students/1", None),
    ]
    for method, path, body in requests:
        response = client.request(method, path, json=body)
        assert response.status_code == 401


def test_register_login_and_get_profile(client):
    credentials = {"username": "petr", "password": "strongpassword123"}
    response = client.post("/auth/register", json=credentials)
    assert response.status_code == 201
    assert "password" not in response.json()
    assert response.json()["username"] == "petr"
    assert client.post("/auth/register", json=credentials).status_code == 409
    bad = {"username": "petr", "password": "wrongpassword123"}
    assert client.post("/auth/login", json=bad).status_code == 401
    headers, _ = register_and_login(client, username="otheruser")
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_login_bad_password(client):
    data = {"username": "petr", "password": "correctpassword"}
    assert client.post("/auth/register", json=data).status_code == 201
    data["password"] = "incorrectpassword"
    assert client.post("/auth/login", json=data).status_code == 401


def test_crud_authorized(client, student_data):
    headers, _ = register_and_login(client)
    created = client.post("/students", json=student_data, headers=headers)
    assert created.status_code == 201
    sid = created.json()["id"]
    assert client.get(f"/students/{sid}", headers=headers).status_code == 200
    assert len(client.get("/students", headers=headers).json()) == 1
    filtered = client.get("/students?faculty=ФПМИ", headers=headers)
    assert len(filtered.json()) == 1
    changed = {**student_data, "grade": 95}
    updated = client.put(f"/students/{sid}", json=changed, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["grade"] == 95
    deleted = client.delete(f"/students/{sid}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/students/{sid}", headers=headers).status_code == 404


def test_logout_invalidates_token(client):
    headers, token = register_and_login(client)
    assert client.post("/auth/logout", headers=headers).status_code == 200
    assert client.get("/students", headers=headers).status_code == 401
    assert client.get("/students", headers=headers).status_code == 401


def test_invalid_token_and_expiration(client):
    headers, token = register_and_login(client)
    bad = client.get(
        "/students", headers={"Authorization": "Bearer bad"}
    )
    assert bad.status_code == 401
    with main.auth_db.SessionLocal() as session:
        login = session.scalar(select(main.LoginSession))
        login.expires_at = int(time.time()) - 10
        session.commit()
    assert client.get("/students", headers=headers).status_code == 401


def test_read_only_role(client, student_data):
    headers, _ = register_and_login(client, "reader")
    with main.auth_db.SessionLocal() as session:
        query = select(main.User).where(main.User.username == "reader")
        user = session.scalar(query)
        user.is_read_only = True
        session.commit()
    assert client.get("/students", headers=headers).status_code == 200
    response = client.post("/students", json=student_data, headers=headers)
    assert response.status_code == 403
    response = client.put("/students/1", json=student_data, headers=headers)
    assert response.status_code == 403
    assert client.delete("/students/1", headers=headers).status_code == 403


def test_validation_and_not_found(client, student_data):
    headers, _ = register_and_login(client)
    invalid = {**student_data, "grade": 999}
    response = client.post("/students", json=invalid, headers=headers)
    assert response.status_code == 422
    assert client.get("/students/999", headers=headers).status_code == 404
    response = client.put("/students/999", json=student_data, headers=headers)
    assert response.status_code == 404
    assert client.delete("/students/999", headers=headers).status_code == 404


def test_password_is_salted_and_not_stored_as_plaintext(client):
    data = {"username": "secureuser", "password": "strongpassword123"}
    assert client.post("/auth/register", json=data).status_code == 201

    with main.auth_db.SessionLocal() as session:
        user = session.scalar(
            select(main.User).where(main.User.username == "secureuser")
        )
        assert user.password_hash.startswith("$argon2id$")
        assert user.password_hash != data["password"]
        assert main.check_password(data["password"], user.password_hash)

    assert main.hash_password(data["password"]) != main.hash_password(
        data["password"]
    )
