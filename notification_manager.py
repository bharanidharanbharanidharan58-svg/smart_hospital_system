import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import os
from database import get_db_connection

LOG_DIR = os.path.dirname(__file__)
WA_LOG_PATH = os.path.join(LOG_DIR, 'whatsapp_notifications.log')
EMAIL_LOG_PATH = os.path.join(LOG_DIR, 'email_notifications.log')

def get_notifications_config():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications_config WHERE key = 'default'")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_notifications_config(smtp_host, smtp_port, smtp_user, smtp_pass, wa_api_key, wa_phone_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE notifications_config 
        SET smtp_host = ?, smtp_port = ?, smtp_user = ?, smtp_pass = ?, wa_api_key = ?, wa_phone_number = ?
        WHERE key = 'default'
    ''', (smtp_host, smtp_port, smtp_user, smtp_pass, wa_api_key, wa_phone_number))
    conn.commit()
    conn.close()

def send_appointment_notifications(appointment_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT appointments.*, 
               patients.name as patient_name, patients.email as patient_email, patients.phone as patient_phone,
               doctors.name as doctor_name, doctors.specialization,
               hospitals.name as hospital_name, hospitals.address as hospital_address
        FROM appointments
        JOIN patients ON appointments.patient_id = patients.id
        JOIN doctors ON appointments.doctor_id = doctors.id
        JOIN hospitals ON doctors.hospital_id = hospitals.id
        WHERE appointments.id = ?
    ''', (appointment_id,))
    appt = cursor.fetchone()
    conn.close()

    if not appt:
        return False

    patient_name = appt['patient_name']
    patient_email = appt['patient_email']
    patient_phone = appt['patient_phone']
    doctor_name = appt['doctor_name']
    specialization = appt['specialization']
    hospital_name = appt['hospital_name']
    hospital_address = appt['hospital_address']
    date = appt['date']
    slot = appt['time_slot']
    token = appt['token_number']

    email_body = f"""Dear {patient_name},

Your appointment has been successfully confirmed at AuraCare!

---------------------------------------------------
APPOINTMENT DETAILS:
---------------------------------------------------
Hospital:     {hospital_name} ({hospital_address})
Doctor:       Dr. {doctor_name} ({specialization})
Date:         {date}
Time Slot:    {slot}
Queue Token:  #{token}
Status:       {appt['status']}
---------------------------------------------------

Please arrive 10 minutes prior to your scheduled time. Show your digital token or QR code at check-in.

Thank you for choosing AuraCare Smart Hospital System.
"""

    wa_message = f"""🏥 *AuraCare Appointment Confirmation*
Hello *{patient_name}*, your appointment is confirmed!

📍 *Hospital:* {hospital_name}
👨‍⚕️ *Doctor:* Dr. {doctor_name} ({specialization})
📅 *Date:* {date} | ⏰ *Time:* {slot}
🎟️ *Token Number:* #{token}

Please show this message or your QR code upon arrival."""

    config = get_notifications_config()

    try:
        if config.get('smtp_user') and config.get('smtp_host'):
            msg = MIMEMultipart()
            msg['From'] = f"AuraCare Hospitals <{config['smtp_user']}>"
            msg['To'] = patient_email
            msg['Subject'] = f"Appointment Confirmed - Token #{token} ({hospital_name})"
            msg.attach(MIMEText(email_body, 'plain'))

            server = smtplib.SMTP(config['smtp_host'], int(config['smtp_port']))
            server.starttls()
            server.login(config['smtp_user'], config['smtp_pass'])
            server.send_message(msg)
            server.quit()
    except Exception as e:
        with open(EMAIL_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(f"[{date} {slot}] EMAIL TO {patient_email}:\n{email_body}\nERROR: {str(e)}\n\n")

    with open(WA_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f"[{date} {slot}] WHATSAPP TO {patient_phone} (9659678129):\n{wa_message}\n\n")

    return True