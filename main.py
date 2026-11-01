import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routes_classes import router as classes_router
from .routes_students import router as students_router
from .routes_attendance import router as attendance_router
from .routes_reports import router as reports_router
from .routes_notifications import router as notifications_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    os.makedirs(os.path.join(uploads_dir, "student_faces"), exist_ok=True)
    os.makedirs(os.path.join(uploads_dir, "session_captures"), exist_ok=True)
    yield

app = FastAPI(title="Bunk-Buster AI Attendance Backend", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

app.include_router(classes_router)
app.include_router(students_router)
app.include_router(attendance_router)
app.include_router(reports_router)
app.include_router(notifications_router)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "system": "Bunk-Buster AI Attendance System"}

