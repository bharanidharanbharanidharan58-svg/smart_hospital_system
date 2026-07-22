import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'hospital.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, city TEXT NOT NULL, address TEXT NOT NULL,
        rating REAL DEFAULT 4.5, image TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER NOT NULL, name TEXT NOT NULL,
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id) ON DELETE CASCADE)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, hospital_id INTEGER NOT NULL,
        specialization TEXT NOT NULL, experience INTEGER NOT NULL, rating REAL DEFAULT 4.5,
        availability_status TEXT DEFAULT 'Online', working_hours TEXT DEFAULT '09:00-17:00',
        break_time TEXT DEFAULT '13:00-14:00', emergency_leave INTEGER DEFAULT 0,
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id) ON DELETE CASCADE)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, phone TEXT NOT NULL, gender TEXT, dob TEXT,
        language TEXT DEFAULT 'English')''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL, department_id INTEGER NOT NULL, date TEXT NOT NULL,
        time_slot TEXT NOT NULL, token_number INTEGER NOT NULL, status TEXT DEFAULT 'Booked',
        priority TEXT DEFAULT 'Standard', qr_code_data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE CASCADE)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS medical_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        report_name TEXT NOT NULL, report_type TEXT NOT NULL, file_path TEXT NOT NULL,
        date_uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, doctor_id INTEGER NOT NULL,
        patient_id INTEGER NOT NULL, rating INTEGER NOT NULL, comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS notifications_config (
        key TEXT PRIMARY KEY, smtp_host TEXT, smtp_port INTEGER,
        smtp_user TEXT, smtp_pass TEXT, wa_api_key TEXT, wa_phone_number TEXT)''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS doctor_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, doctor_id INTEGER NOT NULL, date TEXT NOT NULL,
        slots_json TEXT NOT NULL,
        FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE CASCADE,
        UNIQUE(doctor_id, date))''')
        
    cursor.execute('''INSERT OR IGNORE INTO notifications_config
        (key, smtp_host, smtp_port, smtp_user, smtp_pass, wa_api_key, wa_phone_number)
        VALUES ('default','smtp.mailtrap.io',2525,'mock_user','mock_password','mock_wa_key','+1234567890')''')
        
    conn.commit()
    conn.close()

def add_patient(name, email, password, phone, gender=None, dob=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    pwd_hash = generate_password_hash(password)
    try:
        cursor.execute(
            'INSERT INTO patients (name, email, password_hash, phone, gender, dob) VALUES (?,?,?,?,?,?)',
            (name, email, pwd_hash, phone, gender, dob))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def authenticate_patient(email, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM patients WHERE email = ?', (email,))
    patient = cursor.fetchone()
    conn.close()
    if patient and check_password_hash(patient['password_hash'], password):
        return dict(patient)
    return None

def get_hospitals(city=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if city:
        cursor.execute('SELECT * FROM hospitals WHERE city LIKE ?', (f'%{city}%',))
    else:
        cursor.execute('SELECT * FROM hospitals')
    hospitals = [dict(h) for h in cursor.fetchall()]
    conn.close()
    return hospitals

def get_doctors_by_hospital(hospital_id, specialization=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if specialization:
        cursor.execute('SELECT * FROM doctors WHERE hospital_id=? AND specialization=?', (hospital_id, specialization))
    else:
        cursor.execute('SELECT * FROM doctors WHERE hospital_id=?', (hospital_id,))
    doctors = [dict(d) for d in cursor.fetchall()]
    conn.close()
    return doctors

def get_all_doctors(specialization=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if specialization:
        cursor.execute('''SELECT doctors.*, hospitals.name as hospital_name, hospitals.city
            FROM doctors JOIN hospitals ON doctors.hospital_id = hospitals.id
            WHERE specialization = ?''', (specialization,))
    else:
        cursor.execute('''SELECT doctors.*, hospitals.name as hospital_name, hospitals.city
            FROM doctors JOIN hospitals ON doctors.hospital_id = hospitals.id''')
    doctors = [dict(d) for d in cursor.fetchall()]
    conn.close()
    return doctors