from pathlib import Path

import pytest
from main import Base, StudentDatabase
from sqlalchemy import create_engine


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return StudentDatabase(engine)


def test_csv_import(db):
    path = Path(__file__).resolve().parent / "students.csv"

    assert db.load_from_csv(path) == 215
    assert db.count_students() == 215
    assert db.load_from_csv(path) == 0
    assert db.count_students() == 215


def test_insert(db):
    db.add_student("Иванов", "Петр", "ФПМИ", "Физика", 85)

    students = db.get_students_by_faculty("ФПМИ")

    assert len(students) == 1
    assert students[0].grade == 85


def test_faculty_filter(db):
    path = Path(__file__).resolve().parent / "students.csv"
    db.load_from_csv(path)

    assert len(db.get_students_by_faculty("ФПМИ")) == 40
    assert db.get_students_by_faculty("НЕИЗВЕСТНЫЙ") == []


def test_unique_courses(db):
    path = Path(__file__).resolve().parent / "students.csv"
    db.load_from_csv(path)

    assert db.get_unique_courses() == [
        "Информатика",
        "История",
        "Мат. Анализ",
        "Психология",
        "Теор. Механика",
        "Физика",
    ]


def test_low_grades(db):
    path = Path(__file__).resolve().parent / "students.csv"
    db.load_from_csv(path)

    students = db.get_students_below_30("Мат. Анализ")

    assert len(students) == 13
    assert all(s.grade < 30 and s.course == "Мат. Анализ" for s in students)


def test_average(db):
    path = Path(__file__).resolve().parent / "students.csv"
    db.load_from_csv(path)

    assert db.get_average_grade("ФПМИ") == pytest.approx(49.225)
    assert db.get_average_grade("НЕИЗВЕСТНЫЙ") is None
