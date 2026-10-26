import os
from typing import Literal

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.security_service import is_admin_key_valid
from app.services.system_test_service import run_test_suite


router = APIRouter(
    prefix="/api/system-tests",
    tags=["System Tests"],
)


class SystemTestRequest(BaseModel):
    suite: Literal[
        "quick",
        "ui",
        "regression",
        "all",
    ] = "regression"


@router.post("/run")
def run_system_tests(
    payload: SystemTestRequest,
    x_admin_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    # Chạy kiểm thử tốn tài nguyên (Selenium) nên chỉ quản trị viên được gọi.
    if not is_admin_key_valid(x_admin_key):
        raise HTTPException(
            status_code=403,
            detail="Cần khóa quản trị (X-Admin-Key) để chạy kiểm thử.",
        )

    base_url = os.getenv(
        "CIVICBOT_BASE_URL",
        "http://127.0.0.1:8000",
    )

    return run_test_suite(
        suite=payload.suite,
        db=db,
        base_url=base_url,
    )
