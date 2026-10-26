import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app import models
from app.database import Base, engine, ensure_schema_upgrades
from app.routers import chat
from app.routers import procedures
from app.routers import system_tests
from app.services.security_service import build_chat_rate_limiter
from app.services.ai_service import (
    check_gemini_connection,
)


BASE_DIR = Path(
    __file__
).resolve().parent

TEMPLATES_DIR = BASE_DIR / "templates"

templates = Jinja2Templates(
    directory=str(
        TEMPLATES_DIR
    )
)


app = FastAPI(
    title="CivicBot",
    description=(
        "Chatbot hỗ trợ tra cứu thủ tục cư trú "
        "và giấy tờ tùy thân"
    ),
    version="1.0.0",
)


# Cho phép React gọi API FastAPI.
# Khi triển khai cloud, đặt CORS_ORIGINS=https://ten-mien-frontend
# (nhiều địa chỉ cách nhau bằng dấu phẩy).
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Giới hạn số câu hỏi mỗi IP gửi trong 1 phút
# (chống spam và bảo vệ hạn mức Gemini API).
chat_rate_limiter = build_chat_rate_limiter()


@app.middleware("http")
async def rate_limit_chat(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/chat":
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )

        if not chat_rate_limiter.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        "Bạn gửi quá nhiều câu hỏi. "
                        "Vui lòng thử lại sau ít phút."
                    )
                },
            )

    return await call_next(request)


def seed_procedures_if_empty() -> None:
    """
    Lần chạy đầu (CSDL MySQL trống): tự nạp các thủ tục từ
    data/procedures/*.docx để hệ thống dùng được ngay sau docker compose up.
    Tắt bằng AUTO_IMPORT_DOCX=false.
    """

    if os.getenv("AUTO_IMPORT_DOCX", "true").lower() != "true":
        return

    from app.database import SessionLocal
    from app.services.docx_import_service import parse_docx, upsert_procedure

    db = SessionLocal()

    try:
        if db.query(models.Procedure).count() > 0:
            return

        folder = BASE_DIR.parent / "data" / "procedures"

        for path in sorted(folder.glob("[12]*.docx")):
            try:
                upsert_procedure(db, parse_docx(str(path)))
                db.commit()
                print(f"Đã nạp thủ tục: {path.name}")
            except Exception as error:
                db.rollback()
                print(f"Không nạp được {path.name}: {error}")
    finally:
        db.close()


# Đảm bảo SQLAlchemy nhận diện toàn bộ model
_ = models


try:
    Base.metadata.create_all(
        bind=engine
    )
    ensure_schema_upgrades()
    seed_procedures_if_empty()
except Exception as error:
    print(
        "Không thể khởi tạo cơ sở dữ liệu."
    )
    print(
        f"Chi tiết lỗi: {error}"
    )


app.include_router(
    chat.router
)

app.include_router(
    procedures.router
)

app.include_router(
    system_tests.router
)


@app.get("/")
def home():
    return {
        "message": "CivicBot API đang hoạt động."
    }


# Route này chỉ giữ lại để chạy giao diện cũ
# trong thời gian chuyển sang React.
@app.get("/chat")
def chat_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "request": request,
        },
    )


@app.get("/health")
def health():
    database_status = "error"

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        database_status = "ok"

    except Exception as error:
        print(
            "Kiểm tra cơ sở dữ liệu thất bại."
        )
        print(
            f"Chi tiết lỗi: {error}"
        )

    return {
        "status": "ok",
        "database": database_status,
    }


@app.get("/api/status")
def api_status():
    database_status = "error"

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT 1")
            )

        database_status = "ok"

    except Exception as error:
        print(
            "Kiểm tra cơ sở dữ liệu thất bại."
        )
        print(
            f"Chi tiết lỗi: {error}"
        )

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    ).strip()

    return {
        "backend": "ok",
        "database": database_status,
        "gemini": (
            "configured"
            if api_key
            else "missing"
        ),
        "model": model_name,
    }


@app.get("/api/check-gemini")
def check_gemini():
    try:
        result = check_gemini_connection()

        if isinstance(result, dict):
            return result

        if result is True:
            return {
                "ok": True,
                "message": (
                    "Gemini API đang hoạt động."
                ),
            }

        return {
            "ok": False,
            "message": (
                "Không thể kết nối Gemini API."
            ),
        }

    except Exception as error:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "message": (
                    "Kiểm tra Gemini thất bại: "
                    f"{error}"
                ),
            },
        )