import sys

from sqlalchemy import select

from main import User, auth_db

if len(sys.argv) != 2:
    print("Использование: py set_read_only.py username")
    sys.exit(1)

with auth_db.SessionLocal() as session:
    user = session.scalar(select(User).where(User.username == sys.argv[1]))
    if user is None:
        print("Пользователь не найден")
        sys.exit(1)
    user.is_read_only = True
    session.commit()
    print("Права пользователя изменены: только чтение")
