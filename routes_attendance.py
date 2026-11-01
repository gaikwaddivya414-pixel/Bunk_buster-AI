import json
import os
import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from .database import get_db
from .face_engine import decode_image_from_base64, annotate_and_match_faces

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

UPLOAD_CAPTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "session_captures")
os.makedirs(UPLOAD_CAPTURES_DIR, exist_ok=True)

class StartAttendanceRequest(BaseModel):
    class_id: int
    photo1_base64: str
    custom_interval_seconds: Optional[int] = None

class CaptureSecondRequest(BaseModel):
    photo2_base64: str

class ReviewRecordRequest(BaseModel):
    record_id: int
    review_status: str
    teacher_notes: Optional[str] = ""

class ReviewUnrecognizedRequest(BaseModel):
    detection_id: int
    review_status: str
    teacher_notes: Optional[str] = ""

@router.post("/start")
def start_attendance(payload: StartAttendanceRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM classes WHERE id = ?", (payload.class_id,))
        cls = cursor.fetchone()
        if not cls:
            raise HTTPException(status_code=404, detail="Class not found")
        
        cursor.execute("SELECT * FROM students WHERE class_id = ?", (payload.class_id,))
        students = [dict(s) for s in cursor.fetchall()]
        if not students:
            raise HTTPException(status_code=400, detail="Cannot start attendance: No students enrolled in this class.")
            
        try:
            image_bgr = decode_image_from_base64(payload.photo1_base64)
            mean_intensity = float(image_bgr.mean())
            std_intensity = float(image_bgr.std())
            if mean_intensity < 2.0 and std_intensity < 2.0:
                raise ValueError("Captured Photo 1 is completely black or blank. Camera feed failed.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decode photo: {str(e)}")
            
        match_result = annotate_and_match_faces(
            image_bgr=image_bgr,
            registered_students=students,
            save_dir=UPLOAD_CAPTURES_DIR,
            prefix=f"class_{payload.class_id}_p1"
        )
        
        now = datetime.datetime.now().isoformat()
        today = datetime.date.today().isoformat()
        interval = payload.custom_interval_seconds if payload.custom_interval_seconds and payload.custom_interval_seconds > 0 else cls["interval_seconds"]
        
        cursor.execute("""
            INSERT INTO attendance_sessions (
                class_id, session_date, status, interval_seconds,
                photo1_path, photo1_time, total_enrolled
            ) VALUES (?, ?, 'photo1_captured', ?, ?, ?, ?)
        """, (
            payload.class_id,
            today,
            interval,
            match_result["annotated_path"],
            now,
            len(students)
        ))
        session_id = cursor.lastrowid
        
        for s in students:
            matched = match_result["matched_students"].get(s["id"])
            p1_detected = 1 if matched else 0
            p1_conf = matched["confidence"] if matched else 0.0
            
            cursor.execute("""
                INSERT INTO attendance_records (
                    session_id, student_id, photo1_detected, photo1_confidence, status
                ) VALUES (?, ?, ?, ?, 'PENDING_PHOTO2')
            """, (session_id, s["id"], p1_detected, p1_conf))
            
        for unrec in match_result["unrecognized_faces"]:
            cursor.execute("""
                INSERT INTO unrecognized_detections (
                    session_id, capture_phase, bounding_box, cropped_face_path
                ) VALUES (?, 'PHOTO_1', ?, ?)
            """, (session_id, json.dumps(unrec["bounding_box"]), unrec["cropped_face_path"]))
            
        return {
            "session_id": session_id,
            "status": "photo1_captured",
            "interval_seconds": interval,
            "photo1_path": match_result["annotated_path"],
            "total_enrolled": len(students),
            "photo1_detected_count": len(match_result["matched_students"]),
            "unrecognized_faces_count": len(match_result["unrecognized_faces"]),
            "message": "First photo captured and processed. Countdown started."
        }

@router.post("/{session_id}/capture-second")
def capture_second(session_id: int, payload: CaptureSecondRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Attendance session not found")
            
        if session["status"] == "completed":
            raise HTTPException(status_code=400, detail="This session is already completed")
            
        cursor.execute("SELECT * FROM classes WHERE id = ?", (session["class_id"],))
        cls = cursor.fetchone()
        
        cursor.execute("SELECT * FROM students WHERE class_id = ?", (session["class_id"],))
        students = [dict(s) for s in cursor.fetchall()]
        
        try:
            image_bgr = decode_image_from_base64(payload.photo2_base64)
            mean_intensity = float(image_bgr.mean())
            std_intensity = float(image_bgr.std())
            if mean_intensity < 2.0 and std_intensity < 2.0:
                raise ValueError("Captured Photo 2 is completely black or blank. Camera feed failed.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decode photo: {str(e)}")
            
        match_result = annotate_and_match_faces(
            image_bgr=image_bgr,
            registered_students=students,
            save_dir=UPLOAD_CAPTURES_DIR,
            prefix=f"class_{session['class_id']}_p2"
        )
        
        now = datetime.datetime.now().isoformat()
        
        for unrec in match_result["unrecognized_faces"]:
            cursor.execute("""
                INSERT INTO unrecognized_detections (
                    session_id, capture_phase, bounding_box, cropped_face_path
                ) VALUES (?, 'PHOTO_2', ?, ?)
            """, (session_id, json.dumps(unrec["bounding_box"]), unrec["cropped_face_path"]))
            
        cursor.execute("SELECT * FROM attendance_records WHERE session_id = ?", (session_id,))
        existing_records = cursor.fetchall()
        
        present_count = 0
        bunk_count = 0
        late_count = 0
        absent_count = 0
        
        bunk_students = []
        late_students = []
        
        for rec in existing_records:
            s_id = rec["student_id"]
            p1_det = rec["photo1_detected"]
            matched_p2 = match_result["matched_students"].get(s_id)
            p2_det = 1 if matched_p2 else 0
            p2_conf = matched_p2["confidence"] if matched_p2 else 0.0
            
            cursor.execute("SELECT name, roll_number FROM students WHERE id = ?", (s_id,))
            student_info = cursor.fetchone()
            
            if p1_det == 1 and p2_det == 1:
                final_status = "PRESENT"
                present_count += 1
            elif p1_det == 1 and p2_det == 0:
                final_status = "BUNK_SUSPECT"
                bunk_count += 1
                bunk_students.append(f"{student_info['name']} ({student_info['roll_number']})")
            elif p1_det == 0 and p2_det == 1:
                final_status = "LATE_SUSPECT"
                late_count += 1
                late_students.append(f"{student_info['name']} ({student_info['roll_number']})")
            else:
                final_status = "ABSENT"
                absent_count += 1
                
            cursor.execute("""
                UPDATE attendance_records
                SET photo2_detected = ?, photo2_confidence = ?, status = ?
                WHERE id = ?
            """, (p2_det, p2_conf, final_status, rec["id"]))
            
        cursor.execute("SELECT COUNT(*) as count FROM unrecognized_detections WHERE session_id = ?", (session_id,))
        total_unknown = cursor.fetchone()["count"]
        
        cursor.execute("""
            UPDATE attendance_sessions
            SET status = 'completed',
                photo2_path = ?,
                photo2_time = ?,
                total_present = ?,
                total_bunks = ?,
                total_proxies = ?,
                total_absent = ?,
                unknown_faces_count = ?
            WHERE id = ?
        """, (
            match_result["annotated_path"],
            now,
            present_count,
            bunk_count,
            late_count + total_unknown,
            absent_count,
            total_unknown,
            session_id
        ))
        
        class_name = cls["name"] if cls else "Class"
        
        if bunk_count > 0:
            cursor.execute("""
                INSERT INTO notifications (session_id, class_id, title, message, type, severity)
                VALUES (?, ?, ?, ?, 'BUNK_ALERT', 'danger')
            """, (
                session_id,
                session["class_id"],
                f"Bunk Detected in {class_name}",
                f"{bunk_count} student(s) left the lecture before second capture: {', '.join(bunk_students)}."
            ))
            
        if late_count > 0:
            cursor.execute("""
                INSERT INTO notifications (session_id, class_id, title, message, type, severity)
                VALUES (?, ?, ?, ?, 'LATE_ALERT', 'warning')
            """, (
                session_id,
                session["class_id"],
                f"Late Entry Flag in {class_name}",
                f"{late_count} student(s) appeared only in the second capture: {', '.join(late_students)}."
            ))
            
        if total_unknown > 0:
            cursor.execute("""
                INSERT INTO notifications (session_id, class_id, title, message, type, severity)
                VALUES (?, ?, ?, ?, 'PROXY_ALERT', 'danger')
            """, (
                session_id,
                session["class_id"],
                f"Suspected Proxy / Unknown Person in {class_name}",
                f"{total_unknown} unrecognized face(s) detected during attendance session. Teacher verification required."
            ))
            
        cursor.execute("""
            INSERT INTO notifications (session_id, class_id, title, message, type, severity)
            VALUES (?, ?, ?, ?, 'SESSION_COMPLETED', 'success')
        """, (
            session_id,
            session["class_id"],
            f"Attendance Completed: {class_name}",
            f"Attendance verified. Present: {present_count}, Missing in 2nd photo: {bunk_count}, Absent: {absent_count}."
        ))
        
        cursor.execute("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,))
        updated_session = dict(cursor.fetchone())
        
        return {
            "session": updated_session,
            "summary": {
                "present": present_count,
                "bunks": bunk_count,
                "late": late_count,
                "absent": absent_count,
                "unknown_faces": total_unknown
            },
            "photo2_path": match_result["annotated_path"]
        }

@router.get("/{session_id}")
def get_session_details(session_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, c.name as class_name, c.subject, c.section, c.teacher_name
            FROM attendance_sessions s
            JOIN classes c ON c.id = s.class_id
            WHERE s.id = ?
        """, (session_id,))
        session = cursor.fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Attendance session not found")
            
        cursor.execute("""
            SELECT r.*, st.name as student_name, st.roll_number, st.email, st.photo_path as student_photo
            FROM attendance_records r
            JOIN students st ON st.id = r.student_id
            WHERE r.session_id = ?
            ORDER BY st.roll_number ASC
        """, (session_id,))
        records = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute("""
            SELECT * FROM unrecognized_detections
            WHERE session_id = ?
            ORDER BY created_at ASC
        """, (session_id,))
        unknowns = [dict(u) for u in cursor.fetchall()]
        
        res = dict(session)
        res["records"] = records
        res["unrecognized_detections"] = unknowns
        return res

@router.post("/review-record")
def review_record(payload: ReviewRecordRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attendance_records WHERE id = ?", (payload.record_id,))
        record = cursor.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="Attendance record not found")
            
        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            UPDATE attendance_records
            SET review_status = ?, teacher_notes = ?, reviewed_at = ?
            WHERE id = ?
        """, (payload.review_status, payload.teacher_notes or "", now, payload.record_id))
        
        cursor.execute("""
            SELECT r.*, st.name as student_name, st.roll_number, st.email, st.photo_path as student_photo
            FROM attendance_records r
            JOIN students st ON st.id = r.student_id
            WHERE r.id = ?
        """, (payload.record_id,))
        return dict(cursor.fetchone())

@router.post("/review-unrecognized")
def review_unrecognized(payload: ReviewUnrecognizedRequest):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM unrecognized_detections WHERE id = ?", (payload.detection_id,))
        item = cursor.fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Unrecognized detection not found")
            
        cursor.execute("""
            UPDATE unrecognized_detections
            SET review_status = ?, teacher_notes = ?
            WHERE id = ?
        """, (payload.review_status, payload.teacher_notes or "", payload.detection_id))
        
        cursor.execute("SELECT * FROM unrecognized_detections WHERE id = ?", (payload.detection_id,))
        return dict(cursor.fetchone())

