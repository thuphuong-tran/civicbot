import os
from urllib.parse import quote_plus
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def get_database_url() -> str:
    """
    Lấy chuỗi kết nối CSDL.

    Khi chạy Docker:
        MYSQL_HOST=mysql

    Khi chạy trực tiếp trên Windows:
        MYSQL_HOST=127.0.0.1
    """

    database_url = os.getenv("DATABASE_URL", "").strip()

    if database_url:
        return database_url

    mysql_host = os.getenv(
        "MYSQL_HOST",
        "127.0.0.1",
    )

    mysql_port = os.getenv(
        "MYSQL_PORT",
        "3306",
    )

    mysql_database = os.getenv(
        "MYSQL_DATABASE",
        "civicbot",
    )

    mysql_user = os.getenv(
        "MYSQL_USER",
        "civicbot",
    )

    mysql_password = os.getenv(
        "MYSQL_PASSWORD",
        "civicbot_password",
    )

    return (
        "mysql+pymysql://"
        f"{quote_plus(mysql_user)}:{quote_plus(mysql_password)}"
        f"@{mysql_host}:{mysql_port}"
        f"/{mysql_database}"
        "?charset=utf8mb4"
    )


DATABASE_URL = get_database_url()


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
    echo=False,
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


Base = declarative_base()


def get_db() -> Generator:
    """
    Tạo một phiên làm việc với CSDL
    cho mỗi request FastAPI.
    """

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

def ensure_schema_upgrades() -> None:
    """
    Nâng cấp lược đồ cho CSDL đã tạo từ phiên bản cũ.

    Base.metadata.create_all() không tự thêm cột mới
    vào bảng đã tồn tại, nên hàm này bổ sung các cột
    session_id và procedure_code cho bảng chat_history.
    """

    from sqlalchemy import inspect, text

    try:
        inspector = inspect(engine)

        if "chat_history" not in inspector.get_table_names():
            return

        columns = {
            column["name"]
            for column in inspector.get_columns("chat_history")
        }

        statements = []

        if "session_id" not in columns:
            statements.append(
                "ALTER TABLE chat_history "
                "ADD COLUMN session_id VARCHAR(64) NULL"
            )

        if "procedure_code" not in columns:
            statements.append(
                "ALTER TABLE chat_history "
                "ADD COLUMN procedure_code VARCHAR(32) NULL"
            )

        if not statements:
            return

        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

        print("Đã nâng cấp bảng chat_history.")

    except Exception as error:
        print("Không thể nâng cấp lược đồ CSDL.")
        print(f"Chi tiết lỗi: {error}")
