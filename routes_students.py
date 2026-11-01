import json
import os
import uuid
import cv2
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from .database import get_db
from .face_engine import decode_image_from_base64, extract_face_profile_from_image

router = APIRouter(prefix="/api/students", tags=["students"])

UPLOAD_STUDENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "student_faces")
os.makedirs(UPLOAD_STUDENTS_DIR, exist_ok=True)

class StudentRegister(BaseModel):
    name: str
    roll_number: str
    class_id: int
    email: Optional[str] = None
    photo_base64: str

@router.get("")
def list_students(class_id: Optional[int] = Query(None)):
    with get_db() as conn:
        cursor = conn.cursor()
        if class_id:
            cursor.execute("""
                SELECT s.id, s.name, s.roll_number, s.email, s.class_id, s.photo_path, s.created_at,
                       c.name as class_name, c.subject, c.section
                FROM students s
                JOIN classes c ON c.id = s.class_id
                WHERE s.class_id = ?
                ORDER BY s.roll_number ASC
            """, (class_id,))
        else:
            cursor.execute("""
                SELECT s.id, s.name, s.roll_number, s.email, s.class_id, s.photo_path, s.created_at,
                       c.name as class_name, c.subject, c.section
                FROM students s
                JOIN classes c ON c.id = s.class_id
                ORDER BY s.created_at DESC
            """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

@router.post("")
def register_student(payload: StudentRegister):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM classes WHERE id = ?", (payload.class_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Selected class does not exist")
        
        cursor.execute("SELECT id FROM students WHERE roll_number = ? AND class_id = ?", (payload.roll_number.strip(), payload.class_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="A student with this roll number already exists in this class")
        
        try:
            image_bgr = decode_image_from_base64(payload.photo_base64)
            if float(image_bgr.mean()) < 2.0 and float(image_std := image_bgr.std()) < 2.0:
                raise ValueError("Captured image is completely black or blank. Camera feed failed.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")
        
        encoding, err = extract_face_profile_from_image(image_bgr)
        if err:
            raise HTTPException(status_code=400, detail=err)
        
        photo_filename = f"{uuid.uuid4().hex}.jpg"
        photo_path = os.path.join(UPLOAD_STUDENTS_DIR, photo_filename)
        cv2.imwrite(photo_path, image_bgr)
        relative_photo_path = f"/uploads/student_faces/{photo_filename}"
        
        cursor.execute("""
            INSERT INTO students (name, roll_number, email, class_id, photo_path, face_encoding)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            payload.name.strip(),
            payload.roll_number.strip(),
            payload.email.strip() if payload.email else None,
            payload.class_id,
            relative_photo_path,
            json.dumps(encoding)
        ))
        student_id = cursor.lastrowid
        cursor.execute("""
            SELECT s.id, s.name, s.roll_number, s.email, s.class_id, s.photo_path, s.created_at,
                   c.name as class_name, c.subject, c.section
            FROM students s
            JOIN classes c ON c.id = s.class_id
            WHERE s.id = ?
        """, (student_id,))
        return dict(cursor.fetchone())

@router.delete("/{student_id}")
def delete_student(student_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT photo_path FROM students WHERE id = ?", (student_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")
        
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_abs_path = os.path.join(base_dir, row["photo_path"].lstrip("/"))
            if os.path.exists(file_abs_path):
                os.remove(file_abs_path)
        except Exception:
            pass
            
        cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
        return {"status": "success", "message": "Student deleted"}

