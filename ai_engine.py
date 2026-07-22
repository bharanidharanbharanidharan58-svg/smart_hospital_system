import json
import sqlite3
import datetime
from database import get_db_connection

CHATBOT_KNOWLEDGE = {
    "greetings": ["hello", "hi", "hey", "good morning", "good afternoon", "greetings"],
    "symptoms": {
        "cardiology": ["chest pain", "heart", "palpitations", "shortness of breath", "bp", "blood pressure"],
        "pediatrics": ["child", "baby", "fever in kid", "vaccination", "pediatric", "infant"],
        "neurology": ["headache", "migraine", "dizziness", "numbness", "seizure", "brain", "stroke"],
        "orthopedics": ["bone", "joint pain", "fracture", "knee pain", "back pain", "arthritis"],
        "dermatology": ["skin", "rash", "itching", "acne", "hair fall", "dermatitis"],
        "general medicine": ["fever", "cough", "cold", "flu", "weakness", "body pain", "vomiting"]
    }
}

def ai_chatbot_response(user_text, hospital_id=None):
    text = user_text.lower()
    
    for g in CHATBOT_KNOWLEDGE["greetings"]:
        if g in text:
            return {
                "message": "Hello! I am AuraCare's AI Healthcare Assistant. Please describe your symptoms (e.g. chest pain, headache, child fever) so I can connect you with the right specialist.",
                "suggested_department": None,
                "recommended_doctors": []
            }

    detected_dept = None
    for dept, keywords in CHATBOT_KNOWLEDGE["symptoms"].items():
        for kw in keywords:
            if kw in text:
                detected_dept = dept
                break
        if detected_dept:
            break

    if not detected_dept:
        detected_dept = "general medicine"

    conn = get_db_connection()
    cursor = conn.cursor()
    if hospital_id:
        cursor.execute('''SELECT doctors.*, hospitals.name as hospital_name FROM doctors 
                          JOIN hospitals ON doctors.hospital_id = hospitals.id 
                          WHERE LOWER(specialization) LIKE ? AND hospital_id = ?''', 
                       (f'%{detected_dept}%', hospital_id))
    else:
        cursor.execute('''SELECT doctors.*, hospitals.name as hospital_name FROM doctors 
                          JOIN hospitals ON doctors.hospital_id = hospitals.id 
                          WHERE LOWER(specialization) LIKE ?''', 
                       (f'%{detected_dept}%',))
    
    doctors = [dict(d) for d in cursor.fetchall()]
    conn.close()

    msg = f"Based on your symptoms, we strongly recommend consulting our **{detected_dept.title()}** department."
    if doctors:
        msg += f" Found {len(doctors)} recommended specialist(s):"
    else:
        msg += " No specialists are currently listed for this specific department."

    return {
        "message": msg,
        "suggested_department": detected_dept,
        "recommended_doctors": doctors
    }

def detect_double_booking(patient_id, date, time_slot):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT id FROM appointments 
                      WHERE patient_id = ? AND date = ? AND time_slot = ? AND status != 'Cancelled' ''',
                   (patient_id, date, time_slot))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def predict_waiting_time(doctor_id, date, time_slot):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''SELECT COUNT(*) FROM appointments 
                      WHERE doctor_id = ? AND date = ? AND status IN ('Booked', 'Rescheduled') 
                      AND time_slot < ?''', (doctor_id, date, time_slot))
    prior_count = cursor.fetchone()[0]
    conn.close()

    avg_consultation_mins = 15
    estimated_wait = prior_count * avg_consultation_mins

    if estimated_wait == 0:
        message = "No waiting queue! Your appointment is ready to proceed."
    else:
        message = f"Estimated wait time: ~{estimated_wait} mins ({prior_count} patient(s) ahead of you)."

    return estimated_wait, message

def suggest_best_slots(doctor_id, date, patient_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, date))
    row = cursor.fetchone()
    conn.close()

    default_slots = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "14:00", "14:30", "15:00", "15:30", "16:00"]
    if not row:
        return default_slots, "10:00"

    slot_dict = json.loads(row['slots_json'])
    free_slots = [slot for slot, status in slot_dict.items() if status == 'free']

    best_slot = free_slots[0] if free_slots else None
    for s in ["10:00", "10:30", "11:00", "14:30"]:
        if s in free_slots:
            best_slot = s
            break

    return free_slots, best_slot

def smart_queue_manager_token(doctor_id, date, is_emergency=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM appointments WHERE doctor_id = ? AND date = ?', (doctor_id, date))
    count = cursor.fetchone()[0]
    conn.close()

    if is_emergency:
        return 1
    return count + 1