"""Browser pages served by the API: /school (school staff dashboard)."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)
WEB = Path(__file__).resolve().parent.parent / "web"


@router.get("/school", response_class=HTMLResponse)
def school_page():
    return (WEB / "school.html").read_text(encoding="utf-8")


@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return (WEB / "admin.html").read_text(encoding="utf-8")
