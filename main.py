import csv
import hashlib
import secrets
import time
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, create_engine, func, select
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String(150), nullable=False)
    is_read_only = Column(Boolean, nullable=False, default=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(Integer, nullable=False)


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
                Student.course == course, Student.grade < 30
            )
            return list(session.scalars(query).all())

    def get_average_grade(self, faculty: str) -> float | None:
        with self.SessionLocal() as session:
            query = select(func.avg(Student.grade)).where(
                Student.faculty == faculty
            )
            return session.scalar(query)

    def count_students(self) -> int:
        with self.SessionLocal() as session:
            return session.scalar(select(func.count(Student.id))) or 0


password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def check_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hasher.verify(stored_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class UserDatabase:
    def __init__(self, engine: Engine) -> None:
        self.SessionLocal = sessionmaker(bind=engine)

    def register(
        self, username: str, password: str
    ) -> "UserInfo | None":
        with self.SessionLocal() as session:
            user = User(
                username=username,
                password_hash=hash_password(password),
                is_read_only=False,
            )
            session.add(user)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return None
            return UserInfo.model_validate(user)

    def login(self, username: str, password: str) -> str | None:
        with self.SessionLocal() as session:
            query = select(User).where(User.username == username)
            user = session.scalar(query)
            if user is None:
                return None
            if not check_password(password, user.password_hash):
                return None
            token = secrets.token_urlsafe(32)
            login_session = LoginSession(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=int(time.time()) + 3600,
            )
            session.add(login_session)
            session.commit()
            return token

    def find_by_token(self, token: str) -> "UserInfo | None":
        with self.SessionLocal() as session:
            login = session.scalar(
                select(LoginSession).where(
                    LoginSession.token_hash == hash_token(token)
                )
            )
            if login is None or login.expires_at <= int(time.time()):
                return None
            user = session.get(User, login.user_id)
            if user is None:
                return None
            return UserInfo.model_validate(user)

    def logout(self, token: str) -> None:
        with self.SessionLocal() as session:
            login = session.scalar(
                select(LoginSession).where(
                    LoginSession.token_hash == hash_token(token)
                )
            )
            if login is not None:
                session.delete(login)
                session.commit()


class StudentData(BaseModel):
    last_name: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    faculty: str = Field(min_length=1)
    course: str = Field(min_length=1)
    grade: int = Field(ge=0, le=100)


class StudentResponse(StudentData):
    id: int
    model_config = ConfigDict(from_attributes=True)


class UserCredentials(BaseModel):
    username: str = Field(
        min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$"
    )
    password: str = Field(min_length=8, max_length=128)


class UserInfo(BaseModel):
    id: int
    username: str
    is_read_only: bool
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


engine = create_engine("sqlite:///students.db")
Base.metadata.create_all(engine)

db = StudentDatabase(engine)
auth_db = UserDatabase(engine)
app = FastAPI(title="Students CRUD with Authentication")
auth_router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserInfo:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    user = auth_db.find_by_token(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    return user


def require_editor(user: UserInfo = Depends(get_current_user)) -> UserInfo:
    if user.is_read_only:
        raise HTTPException(status_code=403, detail="Доступно только чтение")
    return user


@auth_router.post("/register", status_code=201, response_model=UserInfo)
def register_user(data: UserCredentials) -> UserInfo:
    user = auth_db.register(data.username, data.password)
    if user is None:
        raise HTTPException(status_code=409, detail="Имя уже занято")
    return user


@auth_router.post("/login", response_model=TokenResponse)
def login_user(data: UserCredentials) -> TokenResponse:
    token = auth_db.login(data.username, data.password)
    if token is None:
        raise HTTPException(
            status_code=401, detail="Неверный логин или пароль"
        )
    return TokenResponse(access_token=token)


@auth_router.get("/me", response_model=UserInfo)
def read_me(user: UserInfo = Depends(get_current_user)) -> UserInfo:
    return user


@auth_router.post("/logout")
def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user: UserInfo = Depends(get_current_user),
) -> dict[str, str]:
    auth_db.logout(credentials.credentials)
    return {"message": "Выход выполнен"}


app.include_router(auth_router)


@app.post("/students", response_model=StudentResponse, status_code=201)
def create_student(
    student: StudentData, user: UserInfo = Depends(require_editor)
) -> Student:
    student_id = db.add_student(**student.model_dump())
    created = db.get_student(student_id)
    if created is None:
        raise HTTPException(status_code=500, detail="Ошибка сохранения")
    return created


@app.get("/students", response_model=list[StudentResponse])
def get_students(
    faculty: str | None = None,
    user: UserInfo = Depends(get_current_user),
) -> list[Student]:
    if faculty is not None:
        return db.get_students_by_faculty(faculty)
    return db.get_all_students()


@app.get("/students/{student_id}", response_model=StudentResponse)
def get_student(
    student_id: int, user: UserInfo = Depends(get_current_user)
) -> Student:
    student = db.get_student(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Студент не найден")
    return student


@app.put("/students/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    student: StudentData,
    user: UserInfo = Depends(require_editor),
) -> Student:
    updated = db.update_student(student_id, **student.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Студент не найден")
    result = db.get_student(student_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Студент не найден")
    return result


@app.delete("/students/{student_id}", status_code=204)
def delete_student(
    student_id: int, user: UserInfo = Depends(require_editor)
) -> Response:
    if not db.delete_student(student_id):
        raise HTTPException(status_code=404, detail="Студент не найден")
    return Response(status_code=204)


if __name__ == "__main__":
    csv_path = Path(__file__).resolve().parent / "students.csv"
    loaded = db.load_from_csv(csv_path)
    print(f"Загружено новых записей: {loaded}")
    print(f"Всего записей в БД: {db.count_students()}")
