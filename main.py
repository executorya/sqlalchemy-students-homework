import csv
from pathlib import Path

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
    ) -> None:
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

    def load_from_csv(self, file_path: Path) -> int:
        with self.SessionLocal() as session:
            existing = session.scalar(select(func.count(Student.id)))
            if existing:
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


if __name__ == "__main__":
    engine = create_engine("sqlite:///students.db")
    Base.metadata.create_all(engine)
    db = StudentDatabase(engine)

    csv_path = Path(__file__).resolve().parent / "students.csv"
    loaded = db.load_from_csv(csv_path)

    print(f"Новых записей загружено: {loaded}")
    print(f"Всего записей в БД: {db.count_students()}")

    students = db.get_students_by_faculty("ФПМИ")
    print(f"\nФПМИ — записей: {len(students)}")

    for student in students[:5]:
        print(student.last_name, student.first_name, student.grade)

    print("\nУникальные курсы:")
    for course in db.get_unique_courses():
        print(course)

    low_grades = db.get_students_below_30("Мат. Анализ")
    print(f"\nМат. Анализ, оценка ниже 30: {len(low_grades)}")

    for student in low_grades:
        print(student.last_name, student.first_name, student.grade)

    average = db.get_average_grade("ФПМИ")
    if average is not None:
        print(f"\nСредняя оценка ФПМИ: {average:.2f}")
