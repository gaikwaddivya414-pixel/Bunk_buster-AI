from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from .database import get_db

router = APIRouter(prefix="/api/classes", tags=["classes"])

class ClassCreate(BaseModel):
    name: str
    subject: str
    section: str
    academic_year: str
    teacher_name: str
    teacher_email: str
    lecture_days: str
    start_time: str
    end_time: str
    interval_seconds: int = 300

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    section: Optional[str] = None
    academic_year: Optional[str] = None
    teacher_name: Optional[str] = None
    teacher_email: Optional[str] = None
    lecture_days: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    interval_seconds: Optional[int] = None

@router.get("")
def list_classes():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, 
                   COUNT(DISTINCT s.id) as enrolled_count,
                   COUNT(DISTINCT a.id) as session_count
            FROM classes c
            LEFT JOIN students s ON s.class_id = c.id
            LEFT JOIN attendance_sessions a ON a.class_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

@router.post("")
def create_class(payload: ClassCreate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO classes (
                name, subject, section, academic_year, teacher_name, 
                teacher_email, lecture_days, start_time, end_time, interval_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.name.strip(),
            payload.subject.strip(),
            payload.section.strip(),
            payload.academic_year.strip(),
            payload.teacher_name.strip(),
            payload.teacher_email.strip(),
            payload.lecture_days.strip(),
            payload.start_time.strip(),
            payload.end_time.strip(),
            max(5, payload.interval_seconds)
        ))
        class_id = cursor.lastrowid
        cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
        return dict(cursor.fetchone())

@router.get("/{class_id}")
def get_class(class_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
        c = cursor.fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Class not found")
        
        cursor.execute("SELECT id, name, roll_number, email, photo_path, created_at FROM students WHERE class_id = ? ORDER BY roll_number ASC", (class_id,))
        students = [dict(s) for s in cursor.fetchall()]
        
        cursor.execute("""
            SELECT * FROM attendance_sessions 
            WHERE class_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (class_id,))
        recent_sessions = [dict(s) for s in cursor.fetchall()]
        
        res = dict(c)
        res["students"] = students
        res["enrolled_count"] = len(students)
        res["recent_sessions"] = recent_sessions
        return res

@router.put("/{class_id}")
def update_class(class_id: int, payload: ClassUpdate):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
        c = cursor.fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Class not found")
        
        update_fields = []
        params = []
        for field, value in payload.model_dump(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = ?")
                params.append(value)
        
        if update_fields:
            params.append(class_id)
            query = f"UPDATE classes SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, tuple(params))
        
        cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
        return dict(cursor.fetchone())

@router.delete("/{class_id}")
def delete_class(class_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM classes WHERE id = ?", (class_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Class not found")
        cursor.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        return {"status": "success", "message": "Class and associated data deleted"}

