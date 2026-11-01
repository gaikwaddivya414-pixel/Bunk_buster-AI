import base64
import json
import os
import uuid
import cv2
import numpy as np
import face_recognition

def decode_image_from_base64(base64_str: str) -> np.ndarray:
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    image_bytes = base64.b64decode(base64_str)
    nparr = np.frombuffer(image_bytes, np.uint8)
    image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Failed to decode image from provided payload")
    return image_bgr

def extract_face_profile_from_image(image_bgr: np.ndarray):
    rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb_image, model="hog")
    if not locations:
        return None, "No face detected in the image"
    if len(locations) > 1:
        locations = sorted(locations, key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]), reverse=True)
    encodings = face_recognition.face_encodings(rgb_image, known_face_locations=[locations[0]])
    if not encodings:
        return None, "Failed to compute face profile"
    return encodings[0].tolist(), None

def annotate_and_match_faces(image_bgr: np.ndarray, registered_students: list, save_dir: str, prefix: str = "capture"):
    rgb_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb_image, model="hog")
    encodings = face_recognition.face_encodings(rgb_image, known_face_locations=locations)
    
    annotated_image = image_bgr.copy()
    matched_students = {}
    unrecognized_faces = []
    
    known_encodings = []
    known_student_map = []
    for s in registered_students:
        try:
            encoding_list = json.loads(s["face_encoding"])
            known_encodings.append(np.array(encoding_list))
            known_student_map.append(s)
        except Exception:
            continue
            
    for (top, right, bottom, left), face_enc in zip(locations, encodings):
        matched_student = None
        best_confidence = 0.0
        
        if known_encodings:
            distances = face_recognition.face_distance(known_encodings, face_enc)
            best_match_idx = int(np.argmin(distances))
            best_distance = float(distances[best_match_idx])
            
            if best_distance < 0.55:
                matched_student = known_student_map[best_match_idx]
                best_confidence = max(0.0, round((1.0 - best_distance) * 100, 1))
                
        if matched_student:
            student_id = matched_student["id"]
            if student_id not in matched_students or best_confidence > matched_students[student_id]["confidence"]:
                matched_students[student_id] = {
                    "student_id": student_id,
                    "name": matched_student["name"],
                    "roll_number": matched_student["roll_number"],
                    "confidence": best_confidence,
                    "location": [top, right, bottom, left]
                }
            cv2.rectangle(annotated_image, (left, top), (right, bottom), (0, 200, 0), 2)
            label = f"{matched_student['name']} ({best_confidence}%)"
            cv2.rectangle(annotated_image, (left, top - 25), (right, top), (0, 200, 0), cv2.FILLED)
            cv2.putText(annotated_image, label, (left + 6, top - 6), cv2.FONT_HERSHEY_DUPLEX, 0.5, (255, 255, 255), 1)
        else:
            face_crop = image_bgr[max(0, top-10):min(image_bgr.shape[0], bottom+10), max(0, left-10):min(image_bgr.shape[1], right+10)]
            crop_filename = f"crop_{uuid.uuid4().hex[:8]}.jpg"
            crop_path = os.path.join(save_dir, crop_filename)
            cv2.imwrite(crop_path, face_crop)
            
            unrecognized_faces.append({
                "bounding_box": [top, right, bottom, left],
                "cropped_face_path": f"/uploads/session_captures/{crop_filename}"
            })
            cv2.rectangle(annotated_image, (left, top), (right, bottom), (0, 0, 220), 2)
            cv2.rectangle(annotated_image, (left, top - 25), (right, top), (0, 0, 220), cv2.FILLED)
            cv2.putText(annotated_image, "UNREGISTERED / PROXY", (left + 6, top - 6), cv2.FONT_HERSHEY_DUPLEX, 0.45, (255, 255, 255), 1)

    filename = f"{prefix}_{uuid.uuid4().hex}.jpg"
    full_path = os.path.join(save_dir, filename)
    cv2.imwrite(full_path, annotated_image)
    
    return {
        "annotated_path": f"/uploads/session_captures/{filename}",
        "matched_students": matched_students,
        "unrecognized_faces": unrecognized_faces,
        "total_faces_detected": len(locations)
    }

