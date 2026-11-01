from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from .database import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.get("")
def list_notifications(unread_only: bool = Query(False)):
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE is_read = 0"
        query += " ORDER BY created_at DESC LIMIT 50"
        
        cursor.execute(query)
        notifications = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT COUNT(*) as count FROM notifications WHERE is_read = 0")
        unread_count = cursor.fetchone()["count"]
        
        return {
            "notifications": notifications,
            "unread_count": unread_count
        }

@router.post("/{notification_id}/read")
def mark_read(notification_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
        return {"status": "success"}

@router.post("/read-all")
def mark_all_read():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
        return {"status": "success"}

@router.delete("/clear")
def clear_all():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notifications")
        return {"status": "success"}

