import sqlite3
import os
import json
from database import DB_PATH, init_db, get_db_connection

def seed_data():
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM hospitals')
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    hospitals = [
        ("Apollo Multi-Specialty Hospital", "Chennai", "Greams Road, Thousand Lights, Chennai", 4.8, "/static/images/hospital_apollo.jpg"),
        ("Fortis Malar Hospital", "Chennai", "Adyar, Gandhi Nagar, Chennai", 4.7, "/static/images/hospital_fortis.jpg"),
        ("Kauvery Hospital", "Chennai", "Mylapore, Luz Church Road, Chennai", 4.6, "/static/images/hospital_kauvery.jpg"),
        ("KMC Specialty Hospital", "Trichy", "Thillai Nagar, Trichy", 4.5, "/static/images/hospital_kmc.jpg")
    ]

    cursor.executemany('''
        INSERT INTO hospitals (name, city, address, rating, image) VALUES (?, ?, ?, ?, ?)
    ''', hospitals)

    departments_map = {
        1: ["Cardiology", "Neurology", "General Medicine", "Pediatrics"],
        2: ["Orthopedics", "Dermatology", "Cardiology"],
        3: ["General Medicine", "Neurology", "Pediatrics"],
        4: ["General Medicine", "Orthopedics", "Dermatology"]
    }

    for hosp_id, depts in departments_map.items():
        for dept_name in depts:
            cursor.execute('INSERT INTO departments (hospital_id, name) VALUES (?, ?)', (hosp_id, dept_name))

    doctors = [
        ("Dr. Ashwin Kumar", 1, "Cardiology", 14, 4.9),
        ("Dr. Meera Vasudevan", 1, "Neurology", 11, 4.8),
        ("Dr. Rajesh Sharma", 1, "General Medicine", 8, 4.6),
        ("Dr. Ananya Ramesh", 1, "Pediatrics", 9, 4.7),
        ("Dr. Vikramaditya Reddy", 2, "Orthopedics", 16, 4.9),
        ("Dr. Sneha Paul", 2, "Dermatology", 7, 4.5),
        ("Dr. Karthik Sundaram", 2, "Cardiology", 12, 4.8),
        ("Dr. Priya Swaminathan", 3, "General Medicine", 10, 4.7),
        ("Dr. Siddharth Sen", 3, "Neurology", 13, 4.8),
        ("Dr. Shalini Mukund", 3, "Pediatrics", 6, 4.6),
        ("Dr. Balaji Natarajan", 4, "General Medicine", 15, 4.9),
        ("Dr. Gayatri Mohan", 4, "Orthopedics", 8, 4.7),
        ("Dr. Deepa Chandran", 4, "Dermatology", 5, 4.4)
    ]

    cursor.executemany('''
        INSERT INTO doctors (name, hospital_id, specialization, experience, rating) VALUES (?, ?, ?, ?, ?)
    ''', doctors)

    default_slots = {
        "09:00": "free", "09:30": "free", "10:00": "booked", "10:30": "free",
        "11:00": "free", "11:30": "free", "13:00": "break", "14:00": "free",
        "14:30": "free", "15:00": "free", "15:30": "free", "16:00": "free"
    }

    import datetime
    today = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    for doc_id in range(1, len(doctors) + 1):
        cursor.execute('INSERT INTO doctor_slots (doctor_id, date, slots_json) VALUES (?, ?, ?)',
                       (doc_id, today, json.dumps(default_slots)))
        cursor.execute('INSERT INTO doctor_slots (doctor_id, date, slots_json) VALUES (?, ?, ?)',
                       (doc_id, tomorrow, json.dumps(default_slots)))

    conn.commit()
    conn.close()

if __name__ == '__main__':
    seed_data()