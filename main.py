import csv
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Integer, String, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    last_name = Column(String(100), nullable=False)
    first_name = Column(String(100), nullable=False)
    faculty = Column(String(20), nullable=False)
    course = Column(String(100), nullable=False)
    grade = Column(Integer, nullable=False)


class StudentDatabase:
    def __init__(self, engine: Engine) -> None:
        self.SessionLocal = sessionmaker(bind=engine)

    def add_student(
        self,
        last_name: str,
        first_name: str,
        faculty: str,
        course: str,
        grade: int,
    ) -> int:
        student = Student(
            last_name=last_name,
            first_name=first_name,
            faculty=faculty,
            course=course,
            grade=grade,
        )

        with self.SessionLocal() as session:
            session.add(student)
            session.commit()
            return student.id

    def get_student(self, student_id: int) -> Student | None:
        with self.SessionLocal() as session:
            return session.get(Student, student_id)

    def get_all_students(self) -> list[Student]:
        with self.SessionLocal() as session:
            query = select(Student).order_by(Student.id)
            return list(session.scalars(query).all())

    def update_student(
        self,
        student_id: int,
        last_name: str,
        first_name: str,
        faculty: str,
        course: str,
        grade: int,
    ) -> bool:
        with self.SessionLocal() as session:
            student = session.get(Student, student_id)

            if student is None:
                return False

            student.last_name = last_name
            student.first_name = first_name
            student.faculty = faculty
            student.course = course
            student.grade = grade

            session.commit()
            return True

    def delete_student(self, student_id: int) -> bool:
        with self.SessionLocal() as session:
            student = session.get(Student, student_id)

            if student is None:
                return False

            session.delete(student)
            session.commit()
            return True

    def load_from_csv(self, file_path: Path) -> int:
        with self.SessionLocal() as session:
            if session.scalar(select(func.count(Student.id))):
                return 0

        students = []

        with open(file_path, encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            for row in reader:
                students.append(
                    Student(
                        last_name=row["Фамилия"],
                        first_name=row["Имя"],
                        faculty=row["Факультет"],
                        course=row["Курс"],
                        grade=int(row["Оценка"]),
                    )
                )

        with self.SessionLocal() as session:
            session.add_all(students)
            session.commit()

        return len(students)

    def get_students_by_faculty(self, faculty: str) -> list[Student]:
        with self.SessionLocal() as session:
            query = select(Student).where(Student.faculty == faculty)
            return list(session.scalars(query).all())

    def get_unique_courses(self) -> list[str]:
        with self.SessionLocal() as session:
            query = select(Student.course).distinct().order_by(Student.course)
            return list(session.scalars(query).all())

    def get_students_below_30(self, course: str) -> list[Student]:
        with self.SessionLocal() as session:
            query = select(Student).where(
                Student.course == course,
                Student.grade < 30,
            )
            return list(session.scalars(query).all())

    def get_average_grade(self, faculty: str) -> float | None:
        with self.SessionLocal() as session:
            query = select(func.avg(Student.grade)).where(Student.faculty == faculty)
            return session.scalar(query)

    def count_students(self) -> int:
        with self.SessionLocal() as session:
            return session.scalar(select(func.count(Student.id))) or 0


class StudentData(BaseModel):
    last_name: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    faculty: str = Field(min_length=1)
    course: str = Field(min_length=1)
    grade: int = Field(ge=0, le=100)


class StudentResponse(StudentData):
    id: int
    model_config = ConfigDict(from_attributes=True)


engine = create_engine("sqlite:///students.db")
Base.metadata.create_all(engine)

db = StudentDatabase(engine)
app = FastAPI(title="Students CRUD API")


@app.post("/students", response_model=StudentResponse, status_code=201)
def create_student(student: StudentData) -> Student:
    student_id = db.add_student(**student.model_dump())
    created = db.get_student(student_id)

    if created is None:
        raise HTTPException(status_code=500, detail="Ошибка сохранения")

    return created


@app.get("/students", response_model=list[StudentResponse])
def get_students(faculty: str | None = None) -> list[Student]:
    if faculty is not None:
        return db.get_students_by_faculty(faculty)

    return db.get_all_students()


@app.get("/students/{student_id}", response_model=StudentResponse)
def get_student(student_id: int) -> Student:
    student = db.get_student(student_id)

    if student is None:
        raise HTTPException(status_code=404, detail="Студент не найден")

    return student


@app.put("/students/{student_id}", response_model=StudentResponse)
def update_student(student_id: int, student: StudentData) -> Student:
    updated = db.update_student(student_id, **student.model_dump())

    if not updated:
        raise HTTPException(status_code=404, detail="Студент не найден")

    result = db.get_student(student_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Студент не найден")

    return result


@app.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: int) -> Response:
    deleted = db.delete_student(student_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Студент не найден")

    return Response(status_code=204)


if __name__ == "__main__":
    csv_path = Path(__file__).resolve().parent / "students.csv"
    loaded = db.load_from_csv(csv_path)

    print(f"Загружено новых записей: {loaded}")
    print(f"Всего записей в БД: {db.count_students()}")
