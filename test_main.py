import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    main.Base.metadata.create_all(engine)

    monkeypatch.setattr(main, "db", main.StudentDatabase(engine))

    with TestClient(main.app) as test_client:
        yield test_client

    engine.dispose()


@pytest.fixture
def student_data():
    return {
        "last_name": "Иванов",
        "first_name": "Пётр",
        "faculty": "ФПМИ",
        "course": "Физика",
        "grade": 85,
    }


def test_create_and_read(client, student_data):
    response = client.post("/students", json=student_data)

    assert response.status_code == 201
    assert response.json()["id"] == 1

    response = client.get("/students/1")

    assert response.status_code == 200
    assert response.json()["grade"] == 85


def test_read_list_and_filter(client, student_data):
    client.post("/students", json=student_data)

    other = {**student_data, "faculty": "АВТФ"}
    client.post("/students", json=other)

    response = client.get("/students")
    assert len(response.json()) == 2

    response = client.get("/students?faculty=ФПМИ")
    assert len(response.json()) == 1
    assert response.json()[0]["faculty"] == "ФПМИ"


def test_update(client, student_data):
    response = client.post("/students", json=student_data)
    student_id = response.json()["id"]

    updated = {**student_data, "grade": 99, "course": "История"}
    response = client.put(f"/students/{student_id}", json=updated)

    assert response.status_code == 200
    assert response.json()["grade"] == 99

    response = client.get(f"/students/{student_id}")
    assert response.json()["course"] == "История"


def test_delete(client, student_data):
    response = client.post("/students", json=student_data)
    student_id = response.json()["id"]

    response = client.delete(f"/students/{student_id}")

    assert response.status_code == 204
    assert response.content == b""

    response = client.get(f"/students/{student_id}")
    assert response.status_code == 404


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_student(client, student_data, method):
    if method == "put":
        response = client.put("/students/999", json=student_data)
    elif method == "delete":
        response = client.delete("/students/999")
    else:
        response = client.get("/students/999")

    assert response.status_code == 404


def test_bad_grade(client, student_data):
    invalid = {**student_data, "grade": 101}

    response = client.post("/students", json=invalid)

    assert response.status_code == 422
    assert client.get("/students").json() == []
