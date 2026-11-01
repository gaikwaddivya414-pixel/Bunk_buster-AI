import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "attendance.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                subject TEXT NOT NULL,
                section TEXT NOT NULL,
                academic_year TEXT NOT NULL,
                teacher_name TEXT NOT NULL,
                teacher_email TEXT NOT NULL,
                lecture_days TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 300,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                roll_number TEXT NOT NULL,
                email TEXT,
                class_id INTEGER NOT NULL,
                photo_path TEXT NOT NULL,
                face_encoding TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
                UNIQUE(roll_number, class_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'photo1_pending',
                interval_seconds INTEGER NOT NULL,
                photo1_path TEXT,
                photo2_path TEXT,
                photo1_time TIMESTAMP,
                photo2_time TIMESTAMP,
                total_enrolled INTEGER DEFAULT 0,
                total_present INTEGER DEFAULT 0,
                total_bunks INTEGER DEFAULT 0,
                total_proxies INTEGER DEFAULT 0,
                total_absent INTEGER DEFAULT 0,
                unknown_faces_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                photo1_detected INTEGER NOT NULL DEFAULT 0,
                photo2_detected INTEGER NOT NULL DEFAULT 0,
                photo1_confidence REAL DEFAULT 0.0,
                photo2_confidence REAL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'ABSENT',
                review_status TEXT NOT NULL DEFAULT 'PENDING',
                teacher_notes TEXT DEFAULT '',
                reviewed_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unrecognized_detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                capture_phase TEXT NOT NULL,
                bounding_box TEXT NOT NULL,
                cropped_face_path TEXT,
                status TEXT NOT NULL DEFAULT 'SUSPECTED_PROXY',
                review_status TEXT NOT NULL DEFAULT 'PENDING',
                teacher_notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                class_id INTEGER,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'warning',
                is_read INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            )
        """)

