import csv
import io
from fastapi import APIRouter, Query, Response
from typing import Optional
from .database import get_db

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/dashboard-stats")
def get_dashboard_stats():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM students")
        total_students = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM classes")
        total_classes = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM attendance_sessions WHERE status = 'completed'")
        total_sessions = cursor.fetchone()["count"]
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_records,
                SUM(CASE WHEN status = 'PRESENT' THEN 1 ELSE 0 END) as total_present,
                SUM(CASE WHEN status = 'BUNK_SUSPECT' THEN 1 ELSE 0 END) as total_bunks,
                SUM(CASE WHEN status = 'LATE_SUSPECT' THEN 1 ELSE 0 END) as total_late,
                SUM(CASE WHEN status = 'ABSENT' THEN 1 ELSE 0 END) as total_absent
            FROM attendance_records
        """)
        stats = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) as count FROM unrecognized_detections")
        total_unrecognized = cursor.fetchone()["count"]
        
        cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE is_read = 0")
        unread_notifications = cursor.fetchone()["count"]
        
        total_records = stats["total_records"] or 0
        total_present = stats["total_present"] or 0
        total_bunks = stats["total_bunks"] or 0
        total_late = stats["total_late"] or 0
        attendance_rate = round((total_present / total_records * 100), 1) if total_records > 0 else 0.0
        bunk_rate = round((total_bunks / total_records * 100), 1) if total_records > 0 else 0.0
        
        return {
            "total_students": total_students,
            "total_classes": total_classes,
            "total_sessions": total_sessions,
            "total_present": total_present,
            "total_bunks": total_bunks,
            "total_late": total_late,
            "total_unrecognized_proxies": total_unrecognized,
            "attendance_rate": attendance_rate,
            "bunk_rate": bunk_rate,
            "unread_notifications": unread_notifications
        }

@router.get("/sessions")
def list_sessions(class_id: Optional[int] = Query(None)):
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT s.*, c.name as class_name, c.subject, c.section, c.teacher_name
            FROM attendance_sessions s
            JOIN classes c ON c.id = s.class_id
        """
        params = []
        if class_id:
            query += " WHERE s.class_id = ?"
            params.append(class_id)
        query += " ORDER BY s.created_at DESC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

@router.get("/discrepancies")
def list_discrepancies(class_id: Optional[int] = Query(None), status_filter: Optional[str] = Query(None)):
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT r.*, st.name as student_name, st.roll_number, st.photo_path as student_photo,
                   s.session_date, s.class_id, c.name as class_name, c.subject, c.section
            FROM attendance_records r
            JOIN students st ON st.id = r.student_id
            JOIN attendance_sessions s ON s.id = r.session_id
            JOIN classes c ON c.id = s.class_id
            WHERE r.status IN ('BUNK_SUSPECT', 'LATE_SUSPECT', 'PROXY_SUSPECT')
        """
        params = []
        if class_id:
            query += " AND s.class_id = ?"
            params.append(class_id)
        if status_filter:
            query += " AND r.status = ?"
            params.append(status_filter)
        query += " ORDER BY s.created_at DESC"
        
        cursor.execute(query, tuple(params))
        records = [dict(r) for r in cursor.fetchall()]
        
        unrec_query = """
            SELECT u.*, s.session_date, s.class_id, c.name as class_name, c.subject
            FROM unrecognized_detections u
            JOIN attendance_sessions s ON s.id = u.session_id
            JOIN classes c ON c.id = s.class_id
        """
        unrec_params = []
        if class_id:
            unrec_query += " WHERE s.class_id = ?"
            unrec_params.append(class_id)
        unrec_query += " ORDER BY u.created_at DESC"
        cursor.execute(unrec_query, tuple(unrec_params))
        unrecognized = [dict(u) for u in cursor.fetchall()]
        
        return {
            "discrepant_records": records,
            "unrecognized_detections": unrecognized
        }

@router.get("/export-csv")
def export_csv(class_id: Optional[int] = Query(None)):
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                c.name as class_name,
                c.subject,
                c.section,
                s.session_date,
                s.id as session_id,
                st.roll_number,
                st.name as student_name,
                r.photo1_detected,
                r.photo1_confidence,
                r.photo2_detected,
                r.photo2_confidence,
                r.status as attendance_status,
                r.review_status,
                r.teacher_notes,
                r.reviewed_at
            FROM attendance_records r
            JOIN students st ON st.id = r.student_id
            JOIN attendance_sessions s ON s.id = r.session_id
            JOIN classes c ON c.id = s.class_id
        """
        params = []
        if class_id:
            query += " WHERE s.class_id = ?"
            params.append(class_id)
        query += " ORDER BY s.session_date DESC, st.roll_number ASC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Class Name", "Subject", "Section", "Date", "Session ID",
            "Roll Number", "Student Name", "Photo 1 Detected", "Photo 1 Conf (%)",
            "Photo 2 Detected", "Photo 2 Conf (%)", "System Status", "Teacher Review Status", "Notes", "Reviewed At"
        ])
        
        for row in rows:
            writer.writerow([
                row["class_name"],
                row["subject"],
                row["section"],
                row["session_date"],
                row["session_id"],
                row["roll_number"],
                row["student_name"],
                "YES" if row["photo1_detected"] else "NO",
                f"{row['photo1_confidence']}%" if row["photo1_detected"] else "-",
                "YES" if row["photo2_detected"] else "NO",
                f"{row['photo2_confidence']}%" if row["photo2_detected"] else "-",
                row["attendance_status"],
                row["review_status"],
                row["teacher_notes"] or "",
                row["reviewed_at"] or ""
            ])
            
        csv_data = output.getvalue()
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=bunk_buster_attendance_report.csv"}
        )

