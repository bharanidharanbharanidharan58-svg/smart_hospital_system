import os
import json
import uuid
import queue
import datetime
from flask import Flask, request, jsonify, render_template, session, Response, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from database import (
    get_db_connection, init_db, add_patient, authenticate_patient,
    get_hospitals, get_doctors_by_hospital, get_all_doctors
)
from ai_engine import (
    ai_chatbot_response, detect_double_booking, predict_waiting_time,
    suggest_best_slots, smart_queue_manager_token
)
from notification_manager import send_appointment_notifications, update_notifications_config, get_notifications_config

import tempfile

app = Flask(__name__)
app.secret_key = 'smart_hospital_super_secret_key_for_session_management'

UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

listeners = []

def send_realtime_event(event_type, data):
    payload = json.dumps({"event": event_type, "data": data})
    for q in listeners[:]:
        try:
            q.put(payload)
        except Exception:
            listeners.remove(q)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/realtime-updates')
def realtime_updates():
    def event_stream():
        q = queue.Queue()
        listeners.append(q)
        try:
            while True:
                msg = q.get()
                yield f"data: {msg}\n\n"
        except GeneratorExit:
            listeners.remove(q)
            
    return Response(event_stream(), mimetype="text/event-stream")

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    phone = data.get('phone')
    gender = data.get('gender')
    dob = data.get('dob')
    
    if not all([name, email, password, phone]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400
        
    patient_id = add_patient(name, email, password, phone, gender, dob)
    if patient_id:
        return jsonify({"success": True, "message": "Registration successful! Please log in."})
    return jsonify({"success": False, "message": "Email address already registered"}), 400

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    
    if not email or not password:
        return jsonify({"success": False, "message": "Missing email or password"}), 400
        
    if role == 'patient':
        patient = authenticate_patient(email, password)
        if patient:
            session['role'] = 'patient'
            session['user_id'] = patient['id']
            session['name'] = patient['name']
            session['email'] = patient['email']
            return jsonify({"success": True, "user": {"id": patient['id'], "name": patient['name'], "role": "patient"}})
            
    elif role == 'doctor':
        if email.startswith('doctor') and email.endswith('@hospital.com'):
            try:
                doc_id_str = email.replace('doctor', '').replace('@hospital.com', '')
                doc_id = int(doc_id_str)
            except ValueError:
                return jsonify({"success": False, "message": "Invalid doctor email format"}), 400
                
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM doctors WHERE id = ?', (doc_id,))
            doctor = cursor.fetchone()
            conn.close()
            
            if doctor and password == 'doctor123':
                session['role'] = 'doctor'
                session['user_id'] = doctor['id']
                session['doctor_id'] = doctor['id']
                session['name'] = doctor['name']
                return jsonify({"success": True, "user": {"id": doctor['id'], "name": doctor['name'], "role": "doctor"}})
                
    elif role == 'admin':
        if email == 'admin@hospital.com' and password == 'admin123':
            session['role'] = 'admin'
            session['user_id'] = 'admin'
            session['name'] = 'System Administrator'
            return jsonify({"success": True, "user": {"id": "admin", "name": "System Administrator", "role": "admin"}})
            
    return jsonify({"success": False, "message": "Invalid email, password, or role selection."}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully"})

@app.route('/api/auth/session', methods=['GET'])
def get_session():
    if 'role' in session:
        return jsonify({
            "authenticated": True, 
            "user": {
                "id": session.get('user_id'), 
                "name": session.get('name'), 
                "role": session.get('role')
            }
        })
    return jsonify({"authenticated": False})

@app.route('/api/hospitals', methods=['GET'])
def list_hospitals():
    city = request.args.get('city')
    return jsonify(get_hospitals(city))

@app.route('/api/departments', methods=['GET'])
def list_departments():
    hospital_id = request.args.get('hospital_id')
    if not hospital_id:
        return jsonify([])
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments WHERE hospital_id = ?', (hospital_id,))
    depts = [dict(d) for d in cursor.fetchall()]
    conn.close()
    return jsonify(depts)

@app.route('/api/doctors', methods=['GET'])
def list_doctors():
    hospital_id = request.args.get('hospital_id')
    specialization = request.args.get('specialization')
    if hospital_id:
        return jsonify(get_doctors_by_hospital(hospital_id, specialization))
    return jsonify(get_all_doctors(specialization))

@app.route('/api/doctor-slots', methods=['GET', 'POST'])
def doctor_slots():
    doctor_id = request.args.get('doctor_id')
    date = request.args.get('date')
    
    if not doctor_id or not date:
         return jsonify({"success": False, "message": "Missing doctor_id or date"}), 400
         
    if request.method == 'GET':
        patient_id = session.get('user_id') if session.get('role') == 'patient' else None
        slots, ai_best = suggest_best_slots(doctor_id, date, patient_id)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, date))
        row = cursor.fetchone()
        conn.close()
        
        slot_status = json.loads(row['slots_json']) if row else {}
        
        slot_details = []
        for slot in slots:
            wait_time, wait_msg = predict_waiting_time(doctor_id, date, slot)
            slot_details.append({
                "time": slot,
                "wait_time": wait_time,
                "wait_message": wait_msg,
                "is_ai_recommended": (slot == ai_best),
                "status": slot_status.get(slot, 'free')
            })
            
        return jsonify({"slots": slot_details, "ai_best_slot": ai_best})
        
    else:
        if session.get('role') != 'doctor':
             return jsonify({"success": False, "message": "Unauthorized"}), 403
             
        data = request.get_json() or {}
        slots_to_update = data.get('slots')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, date))
        row = cursor.fetchone()
        
        if row:
             existing = json.loads(row['slots_json'])
             existing.update(slots_to_update)
             cursor.execute('UPDATE doctor_slots SET slots_json = ? WHERE doctor_id = ? AND date = ?', 
                            (json.dumps(existing), doctor_id, date))
        else:
             cursor.execute('INSERT INTO doctor_slots (doctor_id, date, slots_json) VALUES (?, ?, ?)', 
                            (doctor_id, date, json.dumps(slots_to_update)))
                             
        conn.commit()
        conn.close()
        
        send_realtime_event("availability_change", {"doctor_id": doctor_id, "date": date})
        return jsonify({"success": True, "message": "Time slots updated successfully!"})

@app.route('/api/doctor/status', methods=['POST'])
def update_doctor_status():
    if session.get('role') != 'doctor':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    doctor_id = session.get('doctor_id')
    data = request.get_json() or {}
    status = data.get('status')
    emergency_leave = data.get('emergency_leave', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE doctors 
        SET availability_status = ?, emergency_leave = ? 
        WHERE id = ?
    ''', (status, emergency_leave, doctor_id))
    conn.commit()
    conn.close()
    
    send_realtime_event("doctor_status_change", {
        "doctor_id": doctor_id, 
        "status": status, 
        "emergency_leave": emergency_leave
    })
    
    return jsonify({"success": True, "message": f"Status updated to {status}"})

@app.route('/api/appointments/book', methods=['POST'])
def book_appointment():
    if session.get('role') != 'patient':
        return jsonify({"success": False, "message": "Only registered patients can book appointments"}), 403
        
    patient_id = session.get('user_id')
    data = request.get_json() or {}
    doctor_id = data.get('doctor_id')
    department_id = data.get('department_id')
    date = data.get('date')
    time_slot = data.get('time_slot')
    priority = data.get('priority', 'Standard')
    
    if not all([doctor_id, department_id, date, time_slot]):
        return jsonify({"success": False, "message": "Missing booking details"}), 400
        
    if detect_double_booking(patient_id, date, time_slot):
        return jsonify({"success": False, "message": "AI Alert: You already have another appointment booked at this exact date and time slot."}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, date))
    slot_row = cursor.fetchone()
    if not slot_row:
        conn.close()
        return jsonify({"success": False, "message": "Selected date is unavailable."}), 400
        
    slots = json.loads(slot_row['slots_json'])
    if slots.get(time_slot) != 'free':
        conn.close()
        return jsonify({"success": False, "message": "This slot has already been booked. Please choose another slot."}), 400
        
    is_emergency = (priority == 'Emergency')
    token_number = smart_queue_manager_token(doctor_id, date, is_emergency)
    qr_data = f"APPT-{uuid.uuid4().hex[:8].upper()}-{doctor_id}-{token_number}"
    
    cursor.execute('''
        INSERT INTO appointments (patient_id, doctor_id, department_id, date, time_slot, token_number, priority, qr_code_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (patient_id, doctor_id, department_id, date, time_slot, token_number, priority, qr_data))
    appointment_id = cursor.lastrowid
    
    slots[time_slot] = 'booked'
    cursor.execute('UPDATE doctor_slots SET slots_json = ? WHERE doctor_id = ? AND date = ?', 
                   (json.dumps(slots), doctor_id, date))
    
    conn.commit()
    conn.close()
    
    send_appointment_notifications(appointment_id)
    send_realtime_event("slot_booked", {"doctor_id": doctor_id, "date": date, "slot": time_slot})
    
    return jsonify({
        "success": True, 
        "message": "Appointment booked successfully!", 
        "appointment": {
            "id": appointment_id,
            "token": token_number,
            "qr_code": qr_data
        }
    })

@app.route('/api/appointments/reschedule', methods=['POST'])
def reschedule_appointment():
    user_role = session.get('role')
    if not user_role:
         return jsonify({"success": False, "message": "Unauthorized"}), 401
         
    data = request.get_json() or {}
    appt_id = data.get('appointment_id')
    new_date = data.get('date')
    new_slot = data.get('time_slot')
    
    if not all([appt_id, new_date, new_slot]):
         return jsonify({"success": False, "message": "Missing rescheduling details"}), 400
         
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM appointments WHERE id = ?', (appt_id,))
    appt = cursor.fetchone()
    if not appt:
        conn.close()
        return jsonify({"success": False, "message": "Appointment not found."}), 404
        
    old_date = appt['date']
    old_slot = appt['time_slot']
    doctor_id = appt['doctor_id']
    
    cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, old_date))
    old_row = cursor.fetchone()
    if old_row:
        old_slots = json.loads(old_row['slots_json'])
        if old_slots.get(old_slot) == 'booked':
             old_slots[old_slot] = 'free'
             cursor.execute('UPDATE doctor_slots SET slots_json = ? WHERE doctor_id = ? AND date = ?', 
                            (json.dumps(old_slots), doctor_id, old_date))
             
    cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, new_date))
    new_row = cursor.fetchone()
    if not new_row:
        conn.close()
        return jsonify({"success": False, "message": "Target date unavailable"}), 400
        
    new_slots = json.loads(new_row['slots_json'])
    if new_slots.get(new_slot) != 'free':
        conn.close()
        return jsonify({"success": False, "message": "Target slot is already booked"}), 400
        
    new_slots[new_slot] = 'booked'
    cursor.execute('UPDATE doctor_slots SET slots_json = ? WHERE doctor_id = ? AND date = ?', 
                   (json.dumps(new_slots), doctor_id, new_date))
                   
    is_emergency = (appt['priority'] == 'Emergency')
    new_token = smart_queue_manager_token(doctor_id, new_date, is_emergency)
    
    cursor.execute('''
        UPDATE appointments 
        SET date = ?, time_slot = ?, token_number = ?, status = 'Rescheduled'
        WHERE id = ?
    ''', (new_date, new_slot, new_token, appt_id))
    
    conn.commit()
    conn.close()
    
    send_appointment_notifications(appt_id)
    send_realtime_event("slot_booked", {"doctor_id": doctor_id, "date": new_date, "slot": new_slot})
    send_realtime_event("availability_change", {"doctor_id": doctor_id, "date": old_date})
    
    return jsonify({"success": True, "message": "Appointment rescheduled successfully!"})

@app.route('/api/appointments/cancel', methods=['POST'])
def cancel_appointment():
    if not session.get('role'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    data = request.get_json() or {}
    appt_id = data.get('appointment_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM appointments WHERE id = ?', (appt_id,))
    appt = cursor.fetchone()
    if not appt:
        conn.close()
        return jsonify({"success": False, "message": "Appointment not found."}), 404
        
    date = appt['date']
    slot = appt['time_slot']
    doctor_id = appt['doctor_id']
    
    cursor.execute('SELECT slots_json FROM doctor_slots WHERE doctor_id = ? AND date = ?', (doctor_id, date))
    row = cursor.fetchone()
    if row:
        slots = json.loads(row['slots_json'])
        if slots.get(slot) == 'booked':
            slots[slot] = 'free'
            cursor.execute('UPDATE doctor_slots SET slots_json = ? WHERE doctor_id = ? AND date = ?', 
                           (json.dumps(slots), doctor_id, date))
            
    cursor.execute("UPDATE appointments SET status = 'Cancelled' WHERE id = ?", (appt_id,))
    conn.commit()
    conn.close()
    
    send_realtime_event("availability_change", {"doctor_id": doctor_id, "date": date})
    return jsonify({"success": True, "message": "Appointment cancelled successfully."})

@app.route('/api/appointments/complete', methods=['POST'])
def complete_appointment():
    if session.get('role') != 'doctor':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    appt_id = data.get('appointment_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE appointments SET status = 'Completed' WHERE id = ?", (appt_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Appointment marked as completed."})

@app.route('/api/appointments/history', methods=['GET'])
def appointment_history():
    role = session.get('role')
    user_id = session.get('user_id')
    
    if not role:
         return jsonify([])
         
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if role == 'patient':
         cursor.execute('''
             SELECT appointments.*, doctors.name as doctor_name, doctors.specialization,
                    hospitals.name as hospital_name, hospitals.address as hospital_address
             FROM appointments
             JOIN doctors ON appointments.doctor_id = doctors.id
             JOIN hospitals ON doctors.hospital_id = hospitals.id
             WHERE appointments.patient_id = ?
             ORDER BY appointments.date DESC, appointments.time_slot DESC
         ''', (user_id,))
         
    elif role == 'doctor':
         cursor.execute('''
             SELECT appointments.*, patients.name as patient_name, patients.phone as patient_phone, patients.dob, patients.gender
             FROM appointments
             JOIN patients ON appointments.patient_id = patients.id
             WHERE appointments.doctor_id = ?
             ORDER BY appointments.date DESC, appointments.time_slot DESC
         ''', (user_id,))
         
    elif role == 'admin':
         cursor.execute('''
             SELECT appointments.*, patients.name as patient_name, doctors.name as doctor_name, hospitals.name as hospital_name
             FROM appointments
             JOIN patients ON appointments.patient_id = patients.id
             JOIN doctors ON appointments.doctor_id = doctors.id
             JOIN hospitals ON doctors.hospital_id = hospitals.id
             ORDER BY appointments.created_at DESC
         ''')
         
    appts = [dict(a) for a in cursor.fetchall()]
    conn.close()
    return jsonify(appts)

@app.route('/api/upload-report', methods=['POST'])
def upload_report():
    if session.get('role') != 'patient':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    patient_id = session.get('user_id')
    report_name = request.form.get('report_name')
    report_type = request.form.get('report_type', 'Prescription')
    
    if 'file' not in request.files or not report_name:
        return jsonify({"success": False, "message": "File or report name is missing"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "No file selected"}), 400
        
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        secure_name = secure_filename(f"{patient_id}_{uuid.uuid4().hex[:8]}.{ext}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_name)
        file.save(file_path)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO medical_history (patient_id, report_name, report_type, file_path)
            VALUES (?, ?, ?, ?)
        ''', (patient_id, report_name, report_type, f"/uploads/{secure_name}"))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "message": "Report uploaded successfully!"})
        
    return jsonify({"success": False, "message": "Invalid file type. Allowed formats: pdf, png, jpg, jpeg"}), 400

@app.route('/api/medical-history', methods=['GET'])
def get_medical_history():
    patient_id = request.args.get('patient_id')
    role = session.get('role')
    
    if not role:
         return jsonify([])
         
    if role == 'patient':
        patient_id = session.get('user_id')
        
    if not patient_id:
        return jsonify([])
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM medical_history WHERE patient_id = ? ORDER BY date_uploaded DESC', (patient_id,))
    history = [dict(h) for h in cursor.fetchall()]
    conn.close()
    return jsonify(history)

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    data = request.get_json() or {}
    query = data.get('query', '')
    hospital_id = data.get('hospital_id')
    
    response = ai_chatbot_response(query, hospital_id)
    return jsonify(response)

@app.route('/api/reviews', methods=['GET', 'POST'])
def doctor_reviews():
    doctor_id = request.args.get('doctor_id')
    if not doctor_id:
        return jsonify([])
        
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT reviews.*, patients.name as patient_name 
            FROM reviews 
            JOIN patients ON reviews.patient_id = patients.id 
            WHERE doctor_id = ? 
            ORDER BY created_at DESC
        ''', (doctor_id,))
        revs = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(revs)
        
    else:
        if session.get('role') != 'patient':
             return jsonify({"success": False, "message": "Only patients can submit reviews"}), 403
             
        patient_id = session.get('user_id')
        data = request.get_json() or {}
        rating = data.get('rating')
        comment = data.get('comment')
        
        if not rating:
             return jsonify({"success": False, "message": "Rating is required"}), 400
             
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reviews (doctor_id, patient_id, rating, comment)
            VALUES (?, ?, ?, ?)
        ''', (doctor_id, patient_id, rating, comment))
        
        cursor.execute('SELECT AVG(rating) FROM reviews WHERE doctor_id = ?', (doctor_id,))
        avg_rating = cursor.fetchone()[0] or 4.5
        cursor.execute('UPDATE doctors SET rating = ? WHERE id = ?', (round(avg_rating, 1), doctor_id))
        
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Review submitted successfully!"})

@app.route('/api/admin/hospitals', methods=['POST'])
def admin_add_hospital():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    name = data.get('name')
    city = data.get('city')
    address = data.get('address')
    image = data.get('image', '/static/images/hospital_generic.jpg')
    
    if not all([name, city, address]):
        return jsonify({"success": False, "message": "Missing fields"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO hospitals (name, city, address, image)
        VALUES (?, ?, ?, ?)
    ''', (name, city, address, image))
    hospital_id = cursor.lastrowid
    
    cursor.executemany('''
        INSERT INTO departments (hospital_id, name) VALUES (?, ?)
    ''', [(hospital_id, "General Medicine"), (hospital_id, "Cardiology"), (hospital_id, "Pediatrics")])
    
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Hospital added successfully!"})

@app.route('/api/admin/hospitals/<int:hosp_id>', methods=['PUT', 'DELETE'])
def admin_edit_delete_hospital(hosp_id):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'PUT':
        data = request.get_json() or {}
        name = data.get('name')
        city = data.get('city')
        address = data.get('address')
        
        cursor.execute('''
            UPDATE hospitals SET name = ?, city = ?, address = ? WHERE id = ?
        ''', (name, city, address, hosp_id))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Hospital details updated successfully!"})
        
    else:
        cursor.execute('DELETE FROM hospitals WHERE id = ?', (hosp_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Hospital removed successfully."})

@app.route('/api/admin/config', methods=['GET', 'POST'])
def admin_config():
    if session.get('role') != 'admin':
         return jsonify({"success": False, "message": "Unauthorized"}), 403
         
    if request.method == 'GET':
         return jsonify(get_notifications_config())
    else:
         data = request.get_json() or {}
         update_notifications_config(
              data.get('smtp_host'),
              data.get('smtp_port'),
              data.get('smtp_user'),
              data.get('smtp_pass'),
              data.get('wa_api_key'),
              data.get('wa_phone_number')
         )
         return jsonify({"success": True, "message": "System notification settings updated securely!"})

@app.route('/api/admin/analytics', methods=['GET'])
def admin_analytics():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM patients")
    total_patients = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM doctors")
    total_doctors = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM hospitals")
    total_hospitals = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM appointments")
    total_appointments = cursor.fetchone()[0]
    
    cursor.execute("SELECT status, COUNT(*) as count FROM appointments GROUP BY status")
    status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
    
    cursor.execute("SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count FROM appointments GROUP BY month ORDER BY month DESC LIMIT 6")
    monthly_data = [dict(m) for m in cursor.fetchall()]
    
    today = datetime.date.today().isoformat()
    cursor.execute("SELECT COUNT(*) FROM appointments WHERE date = ?", (today,))
    daily_appointments = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT doctors.specialization, COUNT(*) as count 
        FROM appointments 
        JOIN doctors ON appointments.doctor_id = doctors.id
        GROUP BY doctors.specialization
    ''')
    dept_distribution = [dict(d) for d in cursor.fetchall()]
    
    cursor.execute("SELECT COUNT(*) FROM appointments WHERE status = 'Completed'")
    completed_count = cursor.fetchone()[0]
    revenue = completed_count * 500
    
    conn.close()
    
    return jsonify({
        "total_patients": total_patients,
        "total_doctors": total_doctors,
        "total_hospitals": total_hospitals,
        "total_appointments": total_appointments,
        "daily_appointments": daily_appointments,
        "revenue": revenue,
        "status_counts": status_counts,
        "monthly_data": monthly_data,
        "dept_distribution": dept_distribution
    })

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
