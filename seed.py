import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import get_db, init_db

init_db()

with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM classes")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("""
            INSERT INTO classes (
                name, subject, section, academic_year, teacher_name, 
                teacher_email, lecture_days, start_time, end_time, interval_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Computer Science 3rd Year",
            "Machine Learning & AI",
            "A",
            "2026-2027",
            "Prof. Alan Turing",
            "turing@university.edu",
            "Mon, Wed, Fri",
            "09:00",
            "10:00",
            30
        ))
        cls1_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO classes (
                name, subject, section, academic_year, teacher_name, 
                teacher_email, lecture_days, start_time, end_time, interval_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Information Technology 2nd Year",
            "Data Structures & Algorithms",
            "B",
            "2026-2027",
            "Dr. Ada Lovelace",
            "lovelace@university.edu",
            "Tue, Thu",
            "11:00",
            "12:30",
            300
        ))
        cls2_id = cursor.lastrowid
        print(f"Sample classes created successfully: IDs {cls1_id}, {cls2_id}")
    else:
        print("Classes already exist in database.")

