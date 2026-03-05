import psycopg2
import psycopg2.extras
import random
import string
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host':     os.getenv('DB_HOST', 'localhost'),
    'port':     int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'carepoint'),
    'user':     os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}

def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn

def generate_hospital_id():
    year = datetime.now().year
    code = ''.join(random.choices(string.digits, k=4))
    return f"CP-{year}-{code}"

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS staff (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        specialization TEXT,
        contact TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS patients (
        id SERIAL PRIMARY KEY,
        hospital_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        age INTEGER,
        gender TEXT,
        contact TEXT,
        email TEXT,
        blood_group TEXT,
        address TEXT,
        medical_history TEXT,
        allergies TEXT,
        emergency_contact TEXT,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS appointments (
        id SERIAL PRIMARY KEY,
        patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
        doctor_id INTEGER REFERENCES staff(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        status TEXT DEFAULT 'scheduled',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS availability (
        id SERIAL PRIMARY KEY,
        staff_id INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
        day TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS visits (
        id SERIAL PRIMARY KEY,
        patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
        doctor_id INTEGER REFERENCES staff(id) ON DELETE CASCADE,
        visit_date TEXT NOT NULL,
        diagnosis TEXT,
        prescription TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute("SELECT * FROM staff WHERE username='admin'")
    if not c.fetchone():
        c.execute('''INSERT INTO staff (name, username, password, role)
                     VALUES (%s, %s, %s, %s)''',
                  ('Administrator', 'admin', 'admin123', 'admin'))

    conn.commit()
    conn.close()
    init_pharmacy()

def init_pharmacy():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS pharmacy (
        id SERIAL PRIMARY KEY,
        drug_name TEXT NOT NULL,
        quantity INTEGER DEFAULT 0,
        unit TEXT DEFAULT 'tablets',
        price NUMERIC(10,2) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS prescriptions (
        id SERIAL PRIMARY KEY,
        patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
        visit_id INTEGER REFERENCES visits(id) ON DELETE CASCADE,
        drug_name TEXT NOT NULL,
        dosage TEXT,
        status TEXT DEFAULT 'pending',
        dispensed_by INTEGER REFERENCES staff(id),
        dispensed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()