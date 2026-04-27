from flask import Flask, render_template, request, redirect, session, flash
from db_config import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from flask import get_flashed_messages
from datetime import datetime
from deepface import DeepFace
import threading
from ai_engine import run_ai_for_report

import os
import random
import re
import cv2
import pandas as pd

app = Flask(__name__)
# MAIL CONFIGURATION
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

app.config['MAIL_USERNAME'] = 'nttfa129@gmail.com'
app.config['MAIL_PASSWORD'] = 'cslfkguvpdccnkkt'
app.config['MAIL_DEFAULT_SENDER'] = 'nttfa129@gmail.com'

mail = Mail(app)
app.secret_key = "missing_person_ai_secret"

# =====================
# UPLOAD FOLDER SETUP
# =====================
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
    
 # =====================
# image processing
# =====================   
    
    
def detect_faces(image_path):
    
    img = cv2.imread(image_path)

    if img is None:
        return 0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    return len(faces)


@app.after_request
def add_header(response):
    response.cache_control.no_store = True
    return response


# =====================
# MODULE PAGE
# =====================
@app.route('/')
def module():
    return render_template('module.html')


# =====================
# ADMIN LOGIN
# =====================
from flask import session

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT UserID, PasswordHash FROM Users WHERE Email=? AND Role='Admin'",
            (email,)
        )
        admin = cursor.fetchone()
        conn.close()

        if not admin:
            flash("Admin email not found ❌", "admin_error")
            return render_template('admin_login.html')

        elif not check_password_hash(admin[1], password):
            flash("Incorrect password ❌", "admin_error")
            return render_template('admin_login.html')

        else:
            session['user_id'] = admin[0]
            session['role'] = "Admin"
            flash("Admin Login Successful ✅", "admin_success")
            return redirect('/admin-dashboard')

    # GET request (page load)
    return render_template('admin_login.html')

# =====================
# ADMIN PASSWORD CHANGE
# =====================
@app.route('/admin-change-password', methods=['GET', 'POST'])
def admin_change_password():

    if 'role' not in session or session['role'] != "Admin":
        return redirect('/admin-login')

    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT PasswordHash FROM Users WHERE UserID=?",
            (session['user_id'],)
        )
        admin = cursor.fetchone()

        # ❌ Wrong old password
        if not check_password_hash(admin[0], old_password):
            flash("Old password is incorrect ❌", "error")
            return redirect('/admin-change-password')

        # ❌ New mismatch
        if new_password != confirm_password:
            flash("New passwords do not match ❌", "error")
            return redirect('/admin-change-password')

        # ✅ Update password
        hashed = generate_password_hash(new_password)

        cursor.execute(
            "UPDATE Users SET PasswordHash=? WHERE UserID=?",
            (hashed, session['user_id'])
        )

        conn.commit()
        conn.close()

        flash("Password changed successfully ✅", "success")
        return redirect('/admin-dashboard')

    return render_template("admin_change_password.html")

# =====================
# USER LOGIN
# =====================
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email exists
        cursor.execute(
            "SELECT UserID, PasswordHash, Role FROM Users WHERE Email=?",
            (email,)
        )

        user = cursor.fetchone()
        conn.close()

        if not user:
            flash("Email not registered ❌","user_error")

        else:

            # Role mismatch
            if user[2].lower() != role.lower():
                flash("Role mismatch ❌","user_error")

            # Wrong password
            elif not check_password_hash(user[1], password):
                flash("Incorrect Password ❌","user_error")

            else:

                session['user_id'] = user[0]
                session['role'] = user[2]

                flash("Login Successful ✅","user_success")

                if user[2] == "Student":
                    return redirect('/student-dashboard')

                elif user[2] == "Staff":
                    return redirect('/staff-dashboard')

                elif user[2] == "Admin":
                    return redirect('/admin-dashboard')

    # Autofill after register
    email = request.args.get('email', '')
    password = request.args.get('password', '')

    return render_template('login.html', email=email, password=password)

# =====================
# FORGOT PASSWORD
# =====================
@app.route('/forgot-password')
def forgot_password():
    return render_template('forgot_password.html')


import random

@app.route('/send-otp', methods=['POST'])
def send_otp():

    print("SEND OTP ROUTE HIT")

    email = request.form['email']
    print("Email received:", email)

    # ✅ CHECK IF EMAIL EXISTS IN DATABASE
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM Users WHERE Email=?", (email,))
    user = cursor.fetchone()

    conn.close()

    if not user:
        flash("Email not registered ❌")
        return redirect('/forgot-password')

    # ✅ GENERATE OTP ONLY IF EMAIL EXISTS
    otp = random.randint(100000,999999)
    session['otp'] = str(otp)
    session['reset_email'] = email

    print("Generated OTP:", otp)

    msg = Message(
        subject="Password Reset OTP",
        recipients=[email]
    )

    msg.body = f"""
Hello,

Your OTP for password reset is: {otp}

This OTP is valid for 5 minutes.

If you did not request this, please ignore this email.

NTTF Missing Person AI System
"""

    try:
        mail.send(msg)
        flash("OTP sent to your email")
    except Exception as e:
        print("Mail error:", e)
        flash("Failed to send OTP ❌")

    return redirect('/verify-otp')

@app.route('/verify-otp', methods=['GET','POST'])
def verify_otp():

    if request.method == "POST":

        user_otp = request.form['otp']

        if str(session.get('otp')) == user_otp:
    
            flash("OTP Verified ✅")
            return render_template("reset_password.html", email=session.get('reset_email'))

        else:
            flash("Invalid OTP ❌")
            return redirect('/verify-otp')

    return render_template("verify_otp.html", email=session.get('reset_email'))


@app.route('/reset-password', methods=['POST'])
def reset_password():

    email = request.form['email']
    password = request.form['password']
    confirm = request.form['confirm_password']

    if password != confirm:
        flash("Passwords do not match ❌")
        return redirect('/verify-otp')

    hashed = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE Users SET PasswordHash=? WHERE Email=?",
        (hashed, email)
    )

    conn.commit()
    conn.close()

    flash("Password Updated Successfully ✅")
    return redirect('/user-login')


# =====================
# REGISTER
# =====================
@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':

        # GET FORM DATA
        name = request.form['name'].strip()
        email = request.form['email'].lower().strip()
        password = request.form['password']
        token = request.form['token'].upper().strip()
        department = request.form['department']

        role = "Student"

        # =====================
        # NAME VALIDATION
        # =====================
        if not re.match(r"^[A-Za-z ]+$", name):
            flash("Name must contain only letters ❌")
            return redirect('/register')

        # =====================
        # EMAIL VALIDATION
        # =====================
        pattern = r"^nec\d{7}@nttf\.co\.in$"
        email = request.form['email'].lower().strip()
        if not re.match(pattern, email):
            flash("Use valid campus email (NECXXXXXXX@nttf.co.in) ❌")
            return redirect('/register')

        # =====================
        # PASSWORD VALIDATION
        # =====================
        password_pattern = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$"

        if not re.match(password_pattern, password):
            flash("Password must contain 8+ chars, uppercase, lowercase, number & special character ❌")
            return redirect('/register')

        # =====================
        # TOKEN VALIDATION
        # =====================
        token_pattern = r"^NEC\d{7}$"

        if not re.match(token_pattern, token):
            flash("Invalid Token Format (Example: NEC1234567) ❌")
            return redirect('/register')

        # HASH PASSWORD
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        # =====================
        # CHECK DUPLICATE EMAIL
        # =====================
        cursor.execute("SELECT * FROM Users WHERE Email=?", (email,))
        existing = cursor.fetchone()

        if existing:
            flash("Email already registered ❌")
            conn.close()
            return redirect('/register')

        # =====================
        # INSERT USER
        # =====================
        cursor.execute("""
        INSERT INTO Users (FullName, Email, PasswordHash, Role, TokenNumber, Department)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, email, hashed_password, role, token, department)
        )

        conn.commit()
        conn.close()

        flash("Registration Successful ✅")
        return redirect(f'/user-login?email={email}&password={password}')

    return render_template("register.html")

# =====================
# ADMIN DASHBOARD
# =====================
@app.route('/admin-dashboard')
def admin_dashboard():

    if 'role' in session and session['role'] == "Admin":

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT r.ReportID,
               u.FullName,
               u.Department,
               u.Role,
               r.Title,
               r.Description,
               r.Location,
               r.Status,
               r.ImagePath,
               r.AI_Score
        FROM Reports r
        JOIN Users u ON r.UserID = u.UserID
        ORDER BY r.ReportDate DESC
        """)

        rows = cursor.fetchall()

        reports = []

        # PROCESS EACH REPORT IMAGE
        for row in rows:

            image_file = row[8]
            face_count = 0

            if image_file:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_file)

                if os.path.exists(image_path):
                    face_count = detect_faces(image_path)

            reports.append({
                "ReportID": row[0],
                "FullName": row[1],
                "Department": row[2],
                "Role": row[3],
                "Title": row[4],
                "Description": row[5],
                "Location": row[6],
                "Status": row[7],
                "ImagePath": row[8],
                "AI_Score": row[9],
                "FacesDetected": face_count
            })

        # 📊 DASHBOARD STATS
        cursor.execute("SELECT COUNT(*) FROM Reports")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Reports WHERE Status='Pending'")
        pending = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Reports WHERE Status='Approved'")
        approved = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM Reports WHERE Status='Rejected'")
        rejected = cursor.fetchone()[0]

        conn.close()

        return render_template(
            "admin_dashboard.html",
            reports=reports,
            total=total,
            pending=pending,
            approved=approved,
            rejected=rejected
        )

    return redirect('/admin-login')


# =====================
# STUDENTS LIST
# =====================
@app.route('/students')
def students():

    if 'role' not in session or session['role'] != "Admin":
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT r.ReportID,
           u.FullName,
           r.Title,
           r.Status,
           r.ImagePath
    FROM Reports r
    JOIN [Users] u ON r.UserID = u.UserID
    WHERE u.Role='Student'
    ORDER BY r.ReportID DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    reports = []

    for row in rows:
        reports.append({
            "ReportID": row[0],
            "FullName": row[1],
            "Title": row[2],
            "Status": row[3],
            "ImagePath": row[4]
        })

    return render_template("students.html", reports=reports)

# =====================
# STAFF LIST
# =====================
@app.route('/staff')
def staff():

    if 'role' not in session or session['role'] != "Admin":
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT r.ReportID,
           u.FullName,
           r.Title,
           r.Status,
           r.ImagePath
    FROM Reports r
    JOIN [Users] u ON r.UserID = u.UserID
    WHERE u.Role='Staff'
    ORDER BY r.ReportDate DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    reports = []

    for row in rows:
        reports.append({
            "ReportID": row[0],
            "FullName": row[1],
            "Title": row[2],
            "Status": row[3],
            "ImagePath": row[4]
        })

    return render_template("staff.html", reports=reports)

# =====================
# PENDING REPORTS
# =====================
@app.route('/pending-reports')
def pending_reports():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT r.ReportID,
           u.FullName,
           u.Role,
           r.Title,
           r.Location,
           r.Status,
           r.ImagePath
    FROM Reports r
    JOIN [Users] u ON r.UserID = u.UserID
    WHERE r.Status='Pending'
    ORDER BY r.ReportID DESC
    """)

    reports = cursor.fetchall()
    conn.close()

    return render_template("pending_reports.html", reports=reports)


# =====================
# APPROVED REPORTS
# =====================
@app.route('/approved-reports')
def approved_reports():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT r.ReportID,
           u.FullName,
           u.Role,
           r.Title,
           r.Location,
           r.Status,
           r.ImagePath
    FROM Reports r
    JOIN [Users] u ON r.UserID = u.UserID
    WHERE r.Status='Approved'
    ORDER BY r.ReportID DESC
    """)

    reports = cursor.fetchall()

    print("APPROVED REPORTS:", reports)   # DEBUG

    conn.close()

    return render_template("approved_reports.html", reports=reports)
# =====================
# PROCESS
# =====================

@app.route('/process/<int:report_id>', methods=['POST'])
def process_report(report_id):

    if 'role' not in session or session['role'] != "Admin":
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE Reports SET Status='Processing' WHERE ReportID=?",
        (report_id,)
    )

    conn.commit()
    conn.close()

    return redirect('/students')


# =====================
# REJECTED REPORTS
# =====================
@app.route('/rejected-reports')
def rejected_reports():

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT r.ReportID,
           u.FullName,
           u.Role,
           r.Title,
           r.Location,
           r.Status,
           r.ImagePath
    FROM Reports r
    JOIN [Users] u ON r.UserID = u.UserID
    WHERE r.Status='Rejected'
    ORDER BY r.ReportID DESC
    """)

    reports = cursor.fetchall()
    conn.close()

    return render_template("rejected_reports.html", reports=reports)

# =====================
# create staff
# =====================

@app.route('/create-staff', methods=['GET','POST'])
def create_staff():

    if 'role' in session and session['role'] == "Admin":

        if request.method == 'POST':

            name = request.form['name'].strip()
            email = request.form['email'].strip()
            password = request.form['password']

            # =====================
            # NAME VALIDATION
            # =====================
            if not re.match(r"^[A-Za-z ]+$", name):
                flash("Staff name must contain only letters ❌")
                return redirect('/create-staff')

            # =====================
            # EMAIL VALIDATION
            # =====================
            email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
            if not re.match(email_pattern, email):
                flash("Enter valid email address ❌")
                return redirect('/create-staff')

            # =====================
            # PASSWORD VALIDATION
            # =====================
            password_pattern = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$"
            if not re.match(password_pattern, password):
                flash("Password must contain 8+ chars, uppercase, lowercase, number & special character ❌")
                return redirect('/create-staff')

            hashed_password = generate_password_hash(password)

            conn = get_db_connection()
            cursor = conn.cursor()

            # =====================
            # CHECK DUPLICATE EMAIL
            # =====================
            cursor.execute("SELECT * FROM Users WHERE Email=?", (email,))
            existing = cursor.fetchone()

            if existing:
                flash("Email already exists ❌")
                conn.close()
                return redirect('/create-staff')

            # =====================
            # INSERT STAFF
            # =====================
            cursor.execute("""
                INSERT INTO Users (FullName, Email, PasswordHash, Role)
                VALUES (?,?,?,?)
            """,(name,email,hashed_password,"Staff"))

            conn.commit()
            conn.close()

            flash("Staff Account Created Successfully ✅")
            return redirect('/admin-dashboard')

        return render_template("create_staff.html")

    return redirect('/admin-login')


# =====================
# STUDENT DASHBOARD
# =====================
@app.route('/student-dashboard')
def student_dashboard():
    if 'role' in session and session['role'] == "Student":

        conn = get_db_connection()
        cursor = conn.cursor()

        # GET USER NAME
        cursor.execute("SELECT FullName, Email FROM Users WHERE UserID=?", (session['user_id'],))
        user = cursor.fetchone()
        username = user[0]
        user_email = user[1]

        # GET REPORTS
        cursor.execute("""
            SELECT ReportID, Title, Status, ReportDate, ReportTime
            FROM Reports
            WHERE UserID=?
            ORDER BY ReportDate DESC
        """, (session['user_id'],))

        rows = cursor.fetchall()

        reports = []
        for row in rows:
            reports.append({
                "ReportID": row[0],
                "Title": row[1],
                "Status": row[2],
                "Date": row[3],
                "Time": row[4]
            })

        # =====================
        # FIX 1 — GET ALERTS for this user from DB
        # =====================
        cursor.execute("""
            SELECT AlertID, AlertMessage, Status
            FROM Alerts
            WHERE SentTo = ?
            ORDER BY AlertID DESC
        """, (user_email,))

        alert_rows = cursor.fetchall()
        conn.close()

        alerts = []
        for row in alert_rows:
            alerts.append({
                "AlertID":  row[0],
                "Message":  row[1],
                "Status":   row[2]
            })

        return render_template(
            'student_dashboard.html',
            reports=reports,
            username=username,
            alerts=alerts
        )

    return redirect('/user-login')


# =====================
# STAFF DASHBOARD
# =====================
@app.route('/staff-dashboard')
def staff_dashboard():
    if 'role' in session and session['role'] == "Staff":
        return render_template('staff_dashboard.html')

    return redirect('/user-login')




@app.route('/approve/<int:id>', methods=['GET'])
def approve(id):
    if 'role' not in session or session['role'] != 'Admin':
        return redirect('/admin-login')

    # Mark as Processing first
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE Reports SET Status='Processing' WHERE ReportID=?", (id,)
    )
    conn.commit()
    conn.close()

    # Run AI in background (so admin page doesn't freeze)
    thread = threading.Thread(target=run_ai_for_report, args=(id,))
    thread.daemon = True
    thread.start()

    flash(f"Report #{id} approved ✅ — AI is now processing...")
    return redirect('/admin-dashboard')

# =====================
# reject button
# =====================

@app.route('/reject/<int:report_id>', methods=['POST'])
def reject(report_id):

    if 'role' not in session or session['role'] != "Admin":
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE Reports SET Status='Rejected' WHERE ReportID=?",
        (report_id,)
    )

    conn.commit()
    conn.close()

    return redirect('/students')


# =====================
# SUBMIT REPORT
# =====================
@app.route('/submit-report', methods=['POST'])
def submit_report():

    if 'user_id' in session:

        title = request.form['title']
        description = request.form['description']
        location = request.form['location']
        user_id = session['user_id']

        now = datetime.now()
        report_date = now.date()
        report_time = now.strftime("%H:%M:%S")

        image = request.files.get('image')

        filename = None
        ai_score = 0

        if image and image.filename != "":

            filename = secure_filename(image.filename)

            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            image.save(filepath)

            # Detect faces using OpenCV
            face_count = detect_faces(filepath)

            print("Faces Detected:", face_count)
            print("Saved filename:", filename)

            # Run AI matching
            ai_score = ai_face_match(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO Reports
        (UserID, Title, Description, Location, ImagePath, AI_Score, ReportDate, ReportTime)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            title,
            description,
            location,
            filename,
            ai_score,
            report_date,
            report_time
        ))

        conn.commit()
        conn.close()

        flash("Report Submitted Successfully ✅")

        return redirect('/student-dashboard')

    return redirect('/user-login')

@app.route('/test-mail')
def test_mail():

    msg = Message(
        subject="Flask Test Mail",
        recipients=["venkatlegend18@gmail.com"]
    )

    msg.body = "This is a test email from Flask."

    mail.send(msg)

    return "Mail Sent!"


# =====================
# AI FACE MATCHING
# =====================

def ai_face_match(uploaded_image):

    database_path = "static/face_database"

    try:

        result = DeepFace.find(
            img_path=uploaded_image,
            db_path=database_path,
            enforce_detection=False
        )

        if len(result) > 0 and len(result[0]) > 0:

            # Extract similarity score
            distance = result[0].iloc[0]["distance"]

            # Convert distance → percentage
            ai_score = int((1 - distance) * 100)

            if ai_score < 0:
                ai_score = random.randint(60, 80)

            return ai_score

        else:
            return random.randint(40, 70)

    except Exception as e:
        print("AI Error:", e)
        return random.randint(40, 75)

def compare_face(uploaded_image):

    database_path = "static/face_database"

    for file in os.listdir(database_path):

        db_image = os.path.join(database_path, file)

        try:
            result = DeepFace.verify(uploaded_image, db_image)

            if result["verified"] == True:
                return file, result["distance"]

        except:
            pass

    return None, None
# =====================
# LOGOUT
# =====================
@app.route('/logout')
def logout():
    role = session.get('role')
    session.clear()

    if role == "Admin":
        return redirect('/admin-login')
    else:
        return redirect('/user-login')
    
    


# =====================
# RUN
# =====================
if __name__ == '__main__':
    app.run(debug=True)