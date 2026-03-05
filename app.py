from flask import Flask, render_template, request, redirect, flash, session
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2
import psycopg2.extras
from models import init_db, get_db, generate_hospital_id
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'carepoint_secret_2026')
init_db()

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def query(sql, args=(), one=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Convert SQLite ? placeholders to PostgreSQL %s
    sql = sql.replace('?', '%s')
    cur.execute(sql, args)
    try:
        rv = cur.fetchall()
    except psycopg2.ProgrammingError:
        rv = []
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def staff_required(role=None):
    if 'staff_id' not in session:
        return False
    if role and session.get('role') != role:
        return False
    return True

def patient_required():
    return 'patient_id' in session

def get_current_staff():
    if 'staff_id' in session:
        return query("SELECT * FROM staff WHERE id=?", [session['staff_id']], one=True)
    return None

def get_current_patient():
    if 'patient_id' in session:
        return query("SELECT * FROM patients WHERE id=?", [session['patient_id']], one=True)
    return None

# ─────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        staff = query("SELECT * FROM staff WHERE username=? AND password=?",
                      [username, password], one=True)
        if staff:
            session['staff_id'] = staff['id']
            session['role'] = staff['role']
            session['name'] = staff['name']
            return redirect('/dashboard')
        flash('Invalid username or password', 'error')
    return render_template('staff_login.html')

@app.route('/patient/login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        hospital_id = request.form['hospital_id'].strip().upper()
        password = request.form['password']
        patient = query("SELECT * FROM patients WHERE hospital_id=? AND password=?",
                        [hospital_id, password], one=True)
        if patient:
            session['patient_id'] = patient['id']
            session['patient_name'] = patient['name']
            session['hospital_id'] = patient['hospital_id']
            return redirect('/patient/portal')
        flash('Invalid Hospital ID or password', 'error')
    return render_template('patient_login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ─────────────────────────────────────────
# STAFF DASHBOARD
# ─────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if not staff_required():
        return redirect('/staff/login')
    patients_count     = query("SELECT COUNT(*) as c FROM patients", one=True)['c']
    doctors_count      = query("SELECT COUNT(*) as c FROM staff WHERE role='doctor'", one=True)['c']
    nurses_count       = query("SELECT COUNT(*) as c FROM staff WHERE role='nurse'", one=True)['c']
    appointments_count = query("SELECT COUNT(*) as c FROM appointments WHERE date=?",
                               [datetime.now().strftime('%Y-%m-%d')], one=True)['c']
    recent_patients    = query("SELECT * FROM patients ORDER BY created_at DESC LIMIT 5")
    upcoming           = query('''SELECT a.*, p.name as patient_name, s.name as doctor_name
                                  FROM appointments a
                                  JOIN patients p ON a.patient_id = p.id
                                  JOIN staff s ON a.doctor_id = s.id
                                  WHERE a.date >= ? ORDER BY a.date, a.time LIMIT 5''',
                               [datetime.now().strftime('%Y-%m-%d')])
    return render_template('dashboard.html',
                           patients_count=patients_count,
                           doctors_count=doctors_count,
                           nurses_count=nurses_count,
                           appointments_count=appointments_count,
                           recent_patients=recent_patients,
                           upcoming=upcoming,
                           staff=get_current_staff())

# ─────────────────────────────────────────
# PATIENTS
# ─────────────────────────────────────────

@app.route('/patients')
def patients():
    if not staff_required():
        return redirect('/staff/login')
    search = request.args.get('search', '')
    if search:
        rows = query("SELECT * FROM patients WHERE name ILIKE ? OR hospital_id ILIKE ?",
                     (f'%{search}%', f'%{search}%'))
    else:
        rows = query("SELECT * FROM patients ORDER BY created_at DESC")
    return render_template('patients.html', patients=rows,
                           search=search, staff=get_current_staff())

@app.route('/patients/<int:id>')
def patient_detail(id):
    if not staff_required():
        return redirect('/staff/login')
    patient = query("SELECT * FROM patients WHERE id=?", [id], one=True)
    visits  = query('''SELECT v.*, s.name as doctor_name FROM visits v
                       JOIN staff s ON v.doctor_id = s.id
                       WHERE v.patient_id=? ORDER BY v.visit_date DESC''', [id])
    appts   = query('''SELECT a.*, s.name as doctor_name FROM appointments a
                       JOIN staff s ON a.doctor_id = s.id
                       WHERE a.patient_id=? ORDER BY a.date DESC''', [id])
    return render_template('patient_detail.html', patient=patient,
                           visits=visits, appts=appts, staff=get_current_staff())

@app.route('/add_patient', methods=['GET', 'POST'])
def add_patient():
    if not staff_required():
        return redirect('/staff/login')
    if request.method == 'POST':
        hospital_id = generate_hospital_id()
        while query("SELECT id FROM patients WHERE hospital_id=?", [hospital_id], one=True):
            hospital_id = generate_hospital_id()
        password = request.form.get('password') or hospital_id[-4:]
        query('''INSERT INTO patients
                 (hospital_id, name, age, gender, contact, email, blood_group,
                  address, medical_history, allergies, emergency_contact, password)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
              (hospital_id, request.form['name'], request.form.get('age'),
               request.form.get('gender'), request.form.get('contact'),
               request.form.get('email'), request.form.get('blood_group'),
               request.form.get('address'), request.form.get('medical_history'),
               request.form.get('allergies'), request.form.get('emergency_contact'),
               password))
        patient = query("SELECT * FROM patients WHERE hospital_id=?", [hospital_id], one=True)
        return render_template('patient_id_card.html', patient=patient,
                               password=password, staff=get_current_staff())
    return render_template('add_patient.html', staff=get_current_staff())

@app.route('/edit_patient/<int:id>', methods=['GET', 'POST'])
def edit_patient(id):
    if not staff_required():
        return redirect('/staff/login')
    patient = query("SELECT * FROM patients WHERE id=?", [id], one=True)
    if request.method == 'POST':
        query('''UPDATE patients SET name=?, age=?, gender=?, contact=?, email=?,
                 blood_group=?, address=?, medical_history=?, allergies=?,
                 emergency_contact=? WHERE id=?''',
              (request.form['name'], request.form.get('age'), request.form.get('gender'),
               request.form.get('contact'), request.form.get('email'),
               request.form.get('blood_group'), request.form.get('address'),
               request.form.get('medical_history'), request.form.get('allergies'),
               request.form.get('emergency_contact'), id))
        flash('Patient updated successfully', 'success')
        return redirect(f'/patients/{id}')
    return render_template('edit_patient.html', patient=patient, staff=get_current_staff())

@app.route('/delete_patient/<int:id>')
def delete_patient(id):
    if not staff_required():
        return redirect('/staff/login')
    query("DELETE FROM patients WHERE id=?", [id])
    flash('Patient removed', 'success')
    return redirect('/patients')

# ─────────────────────────────────────────
# STAFF MANAGEMENT
# ─────────────────────────────────────────

@app.route('/staff')
def staff_list():
    if not staff_required():
        return redirect('/staff/login')
    members = query("SELECT * FROM staff WHERE role != 'admin' ORDER BY role, name")
    return render_template('staff_list.html', members=members, staff=get_current_staff())

@app.route('/add_staff', methods=['GET', 'POST'])
def add_staff():
    if not staff_required():
        return redirect('/staff/login')
    if request.method == 'POST':
        existing = query("SELECT id FROM staff WHERE username=?",
                         [request.form['username']], one=True)
        if existing:
            flash('Username already taken', 'error')
        else:
            query('''INSERT INTO staff (name, username, password, role, specialization, contact)
                     VALUES (?,?,?,?,?,?)''',
                  (request.form['name'], request.form['username'],
                   request.form['password'], request.form['role'],
                   request.form.get('specialization'), request.form.get('contact')))
            flash(f"{request.form['role'].title()} added successfully", 'success')
            return redirect('/staff')
    return render_template('add_staff.html', staff=get_current_staff())

@app.route('/delete_staff/<int:id>')
def delete_staff(id):
    if not staff_required():
        return redirect('/staff/login')
    query("DELETE FROM staff WHERE id=?", [id])
    flash('Staff member removed', 'success')
    return redirect('/staff')

# ─────────────────────────────────────────
# APPOINTMENTS
# ─────────────────────────────────────────

@app.route('/appointments')
def appointments():
    if not staff_required():
        return redirect('/staff/login')
    appts = query('''SELECT a.*, p.name as patient_name, p.hospital_id,
                            s.name as doctor_name
                     FROM appointments a
                     JOIN patients p ON a.patient_id = p.id
                     JOIN staff s ON a.doctor_id = s.id
                     ORDER BY a.date DESC, a.time DESC''')
    patients_list = query("SELECT id, name, hospital_id FROM patients ORDER BY name")
    doctors_list  = query("SELECT id, name, specialization FROM staff WHERE role='doctor' ORDER BY name")
    return render_template('appointments.html', appointments=appts,
                           patients=patients_list, doctors=doctors_list,
                           staff=get_current_staff())

@app.route('/add_appointment', methods=['POST'])
def add_appointment():
    if not staff_required():
        return redirect('/staff/login')
    query('''INSERT INTO appointments (patient_id, doctor_id, date, time, notes)
             VALUES (?,?,?,?,?)''',
          (request.form['patient_id'], request.form['doctor_id'],
           request.form['date'], request.form['time'], request.form.get('notes')))
    flash('Appointment scheduled', 'success')
    return redirect('/appointments')

@app.route('/appointment/status/<int:id>/<status>')
def update_appointment_status(id, status):
    if not staff_required():
        return redirect('/staff/login')
    query("UPDATE appointments SET status=? WHERE id=?", [status, id])
    return redirect('/appointments')

# ─────────────────────────────────────────
# AVAILABILITY
# ─────────────────────────────────────────

@app.route('/availability')
def availability():
    if not staff_required():
        return redirect('/staff/login')
    slots = query('''SELECT av.*, s.name, s.role FROM availability av
                     JOIN staff s ON av.staff_id = s.id
                     ORDER BY s.role, s.name''')
    members = query("SELECT * FROM staff WHERE role IN ('doctor','nurse') ORDER BY name")
    return render_template('availability.html', slots=slots,
                           members=members, staff=get_current_staff())

@app.route('/add_availability', methods=['POST'])
def add_availability():
    if not staff_required():
        return redirect('/staff/login')
    query('''INSERT INTO availability (staff_id, day, start_time, end_time)
             VALUES (?,?,?,?)''',
          (request.form['staff_id'], request.form['day'],
           request.form['start_time'], request.form['end_time']))
    flash('Availability added', 'success')
    return redirect('/availability')

@app.route('/delete_availability/<int:id>')
def delete_availability(id):
    if not staff_required():
        return redirect('/staff/login')
    query("DELETE FROM availability WHERE id=?", [id])
    return redirect('/availability')

# ─────────────────────────────────────────
# VISITS
# ─────────────────────────────────────────

@app.route('/add_visit/<int:patient_id>', methods=['GET', 'POST'])
def add_visit(patient_id):
    if not staff_required():
        return redirect('/staff/login')
    patient = query("SELECT * FROM patients WHERE id=?", [patient_id], one=True)
    doctors = query("SELECT * FROM staff WHERE role='doctor'")
    if request.method == 'POST':
        query('''INSERT INTO visits (patient_id, doctor_id, visit_date, diagnosis, prescription, notes)
                 VALUES (?,?,?,?,?,?)''',
              (patient_id, request.form['doctor_id'], request.form['visit_date'],
               request.form.get('diagnosis'), request.form.get('prescription'),
               request.form.get('notes')))
        flash('Visit recorded', 'success')
        return redirect(f'/patients/{patient_id}')
    return render_template('add_visit.html', patient=patient,
                           doctors=doctors, staff=get_current_staff(),
                           now=datetime.now().strftime('%Y-%m-%d'))

# ─────────────────────────────────────────
# PATIENT PORTAL
# ─────────────────────────────────────────

@app.route('/patient/portal')
def patient_portal():
    if not patient_required():
        return redirect('/patient/login')
    patient = get_current_patient()
    visits  = query('''SELECT v.*, s.name as doctor_name FROM visits v
                       JOIN staff s ON v.doctor_id = s.id
                       WHERE v.patient_id=? ORDER BY v.visit_date DESC''',
                    [session['patient_id']])
    appts   = query('''SELECT a.*, s.name as doctor_name FROM appointments a
                       JOIN staff s ON a.doctor_id = s.id
                       WHERE a.patient_id=? ORDER BY a.date DESC''',
                    [session['patient_id']])
    return render_template('patient_portal.html', patient=patient,
                           visits=visits, appts=appts)

# ─────────────────────────────────────────
# PHARMACY
# ─────────────────────────────────────────

@app.route('/pharmacy')
def pharmacy():
    if not staff_required():
        return redirect('/staff/login')
    drugs = query("SELECT * FROM pharmacy ORDER BY drug_name")
    pending = query('''SELECT pr.*, p.name as patient_name, p.hospital_id
                       FROM prescriptions pr
                       JOIN patients p ON pr.patient_id = p.id
                       WHERE pr.status = 'pending'
                       ORDER BY pr.created_at DESC''')
    dispensed = query('''SELECT pr.*, p.name as patient_name, s.name as dispensed_by_name
                         FROM prescriptions pr
                         JOIN patients p ON pr.patient_id = p.id
                         LEFT JOIN staff s ON pr.dispensed_by = s.id
                         WHERE pr.status = 'dispensed'
                         ORDER BY pr.dispensed_at DESC LIMIT 20''')
    return render_template('pharmacy.html', drugs=drugs, pending=pending,
                           dispensed=dispensed, staff=get_current_staff())

@app.route('/pharmacy/add_drug', methods=['POST'])
def add_drug():
    if not staff_required():
        return redirect('/staff/login')
    query('''INSERT INTO pharmacy (drug_name, quantity, unit, price)
             VALUES (?,?,?,?)''',
          (request.form['drug_name'], request.form.get('quantity', 0),
           request.form.get('unit', 'tablets'), request.form.get('price', 0)))
    flash('Drug added to inventory', 'success')
    return redirect('/pharmacy')

@app.route('/pharmacy/restock/<int:id>', methods=['POST'])
def restock_drug(id):
    if not staff_required():
        return redirect('/staff/login')
    qty = int(request.form.get('quantity', 0))
    query("UPDATE pharmacy SET quantity = quantity + ? WHERE id=?", [qty, id])
    flash(f'Stock updated', 'success')
    return redirect('/pharmacy')

@app.route('/pharmacy/delete_drug/<int:id>')
def delete_drug(id):
    if not staff_required():
        return redirect('/staff/login')
    query("DELETE FROM pharmacy WHERE id=?", [id])
    flash('Drug removed', 'success')
    return redirect('/pharmacy')

@app.route('/pharmacy/dispense/<int:id>')
def dispense(id):
    if not staff_required():
        return redirect('/staff/login')
    query('''UPDATE prescriptions SET status='dispensed',
             dispensed_by=?, dispensed_at=CURRENT_TIMESTAMP WHERE id=?''',
          [session['staff_id'], id])
    flash('Prescription dispensed', 'success')
    return redirect('/pharmacy')

if __name__ == '__main__':
    app.run(debug=True)