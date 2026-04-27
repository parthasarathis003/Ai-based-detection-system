import cv2
import os
import numpy as np
from PIL import Image
from ultralytics import YOLO
from deepface import DeepFace
from db_config import get_db_connection
from datetime import datetime

# =====================
# EMAIL (reuse same SMTP as app.py OTP)
# =====================
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

MAIL_USERNAME = 'nttfa129@gmail.com'
MAIL_PASSWORD = 'cslfkguvpdccnkkt'

def send_alert_email(to_email, subject, body):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = MAIL_USERNAME
        msg['To']      = to_email

        # Plain-text fallback
        part1 = MIMEText(body, 'plain', 'utf-8')

        # FIX 1 — removed emoji from html_body (was causing ascii error)
        html_body = f"""
        <html><body>
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;
                    border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;">
          <div style="background:#f97316;padding:20px;text-align:center;">
            <h2 style="color:white;margin:0;">AI Detection Alert</h2>
          </div>
          <div style="padding:25px;background:#f8fafc;">
            <p style="font-size:15px;color:#334155;">{body}</p>
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
            <p style="font-size:12px;color:#94a3b8;">
              NTTF AI Missing Person Detection System
            </p>
          </div>
        </div>
        </body></html>
        """
        part2 = MIMEText(html_body, 'html', 'utf-8')

        msg.attach(part1)
        msg.attach(part2)

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.ehlo()
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            # FIX 2 — use send_message() instead of sendmail() + as_string()
            server.send_message(msg)

        print(f"Email successfully sent to: {to_email}")

    except Exception as e:
        print(f"Email failed to send: {e}")


FRAME_SKIP = 30
VIDEO_FOLDER = 'static/cctv_videos'
MATCHED_FOLDER = 'static/matched_frames'


def run_ai_for_report(report_id):

    print(f"AI started for Report #{report_id}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT ReportID, UserID, Title, Description, Location, ImagePath
        FROM Reports WHERE ReportID = ?
    """, (report_id,))

    report = cursor.fetchone()

    if not report:
        print("Report not found!")
        conn.close()
        return

    report_id   = report[0]
    user_id     = report[1]
    title       = report[2]
    description = report[3]
    location    = report[4]
    image_path  = report[5]

    print(f"Report: {title} | Image: {image_path}")

    person_keywords = ['person', 'student', 'staff', 'missing',
                       'girl', 'boy', 'man', 'woman', 'friend']
    text = (str(title) + ' ' + str(description)).lower()
    is_person = any(kw in text for kw in person_keywords)

    print(f"Type detected: {'Person' if is_person else 'Object'}")

    found = False
    confidence = 0.0
    matched_frame_filename = None

    os.makedirs(MATCHED_FOLDER, exist_ok=True)

    if is_person and image_path:
        full_image_path = os.path.join('static/uploads', image_path)
        found, confidence, matched_frame_filename = detect_person(
            full_image_path, VIDEO_FOLDER, MATCHED_FOLDER
        )
    else:
        found, confidence, matched_frame_filename = detect_object(
            str(description), VIDEO_FOLDER, MATCHED_FOLDER
        )

    ai_result = 'Found' if found else 'Not Found'
    ai_score  = int(confidence)

    print(f"AI Result: {ai_result} | Score: {ai_score}% | Frame: {matched_frame_filename}")

    cursor.execute("""
        UPDATE Reports
        SET AIResult        = ?,
            Score           = ?,
            AI_Score        = ?,
            AI_MatchedFrame = ?,
            Status          = 'Approved'
        WHERE ReportID = ?
    """, (ai_result, confidence, ai_score, matched_frame_filename, report_id))

    person_db_id = None
    object_db_id = None

    if is_person:
        cursor.execute("""
            INSERT INTO MissingPersons
                (FullName, Department, PhotoPath, ReportedBy, Status)
            VALUES (?, ?, ?, ?, ?)
        """, (
            title, 'Unknown', image_path, user_id,
            'Found' if found else 'Missing'
        ))
        person_db_id = cursor.execute("SELECT @@IDENTITY").fetchval()
        print(f"Inserted into MissingPersons: ID={person_db_id}")

    else:
        cursor.execute("""
            INSERT INTO Objects
                (ObjectName, Description, PhotoPath, ReportedBy, Status)
            VALUES (?, ?, ?, ?, ?)
        """, (
            title, description, image_path, user_id,
            'Found' if found else 'Lost'
        ))
        object_db_id = cursor.execute("SELECT @@IDENTITY").fetchval()
        print(f"Inserted into Objects: ID={object_db_id}")

    cursor.execute("""
        INSERT INTO DetectionLogs
            (PersonID, ObjectID, DetectionType, ConfidenceScore,
             DetectedTime, SnapshotPath)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        person_db_id, object_db_id,
        'Person' if is_person else 'Object',
        confidence, datetime.now(), matched_frame_filename
    ))

    log_id = cursor.execute("SELECT @@IDENTITY").fetchval()
    print(f"Inserted into DetectionLogs: ID={log_id}")

    if found:
        cursor.execute(
            "SELECT Email FROM Users WHERE UserID = ?", (user_id,)
        )
        user_email = cursor.fetchone()
        sent_to = user_email[0] if user_email else 'Unknown'

        alert_message = (
            f"{'Person' if is_person else 'Object'} from your report "
            f"'{title}' was FOUND with {confidence:.1f}% confidence "
            f"at location: {location}"
        )

        cursor.execute("""
            INSERT INTO Alerts (LogID, AlertMessage, SentTo, Status)
            VALUES (?, ?, ?, ?)
        """, (log_id, alert_message, sent_to, 'Sent'))

        print(f"Alert sent to: {sent_to}")

        # FIX 3 — removed em dash from subject (was causing ascii error)
        send_alert_email(
            to_email=sent_to,
            subject=f"Alert: '{title}' - Match Found!",
            body=alert_message
        )

    conn.commit()
    conn.close()
    print(f"AI processing complete for Report #{report_id}")


def detect_person(image_path, video_folder, output_folder):

    print(f"Scanning for person... Image: {image_path}")

    if not os.path.exists(image_path):
        print("Image file not found!")
        return False, 0.0, None

    if not os.path.exists(video_folder):
        print(f"Video folder not found: {video_folder}")
        return False, 0.0, None

    video_files = [f for f in os.listdir(video_folder)
                   if f.endswith(('.mp4', '.avi', '.mkv'))]

    if not video_files:
        print("No video files found in cctv_videos folder!")
        return False, 0.0, None

    for video_file in video_files:

        print(f"Scanning video: {video_file}")
        cap = cv2.VideoCapture(os.path.join(video_folder, video_file))
        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                continue

            temp_frame_path = os.path.join(output_folder, 'temp_frame.jpg')
            cv2.imwrite(temp_frame_path, frame)

            try:
                result = DeepFace.verify(
                    img1_path=image_path,
                    img2_path=temp_frame_path,
                    enforce_detection=False,
                    silent=True
                )

                distance   = result['distance']
                confidence = round((1 - distance) * 100, 2)
                verified   = result['verified']

                print(f"   Frame {frame_count}: confidence={confidence}% verified={verified}")

                if verified and confidence > 50:
                    cv2.putText(frame,
                                f"MATCH {confidence}%",
                                (50, 50),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                1.0, (0, 255, 0), 2)

                    fname = f"match_{video_file}_{frame_count}.jpg"
                    cv2.imwrite(os.path.join(output_folder, fname), frame)
                    cap.release()
                    print(f"Match found! Saved: {fname}")
                    return True, confidence, fname

            except Exception as e:
                print(f"   Frame {frame_count} skipped: {e}")
                continue

        cap.release()
        print(f"   Finished scanning {video_file} - no match found")

    print("No match found in any video")
    return False, 0.0, None


def detect_object(description, video_folder, output_folder):

    print(f"Scanning for object: {description}")
    model = YOLO('yolov8n.pt')
    keywords = description.lower().split()

    if not os.path.exists(video_folder):
        print(f"Video folder not found: {video_folder}")
        return False, 0.0, None

    video_files = [f for f in os.listdir(video_folder)
                   if f.endswith(('.mp4', '.avi', '.mkv'))]

    if not video_files:
        print("No video files found!")
        return False, 0.0, None

    for video_file in video_files:

        print(f"Scanning video: {video_file}")
        cap = cv2.VideoCapture(os.path.join(video_folder, video_file))
        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            if frame_count % FRAME_SKIP != 0:
                continue

            results = model(frame, verbose=False)

            for result in results:
                for box in result.boxes:
                    class_name = model.names[int(box.cls)].lower()
                    confidence = float(box.conf) * 100

                    if any(kw in class_name for kw in keywords) and confidence > 50:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(frame, (x1, y1), (x2, y2),
                                      (0, 0, 255), 2)
                        cv2.putText(frame,
                                    f"{class_name} {confidence:.1f}%",
                                    (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8, (0, 0, 255), 2)

                        fname = f"obj_{video_file}_{frame_count}.jpg"
                        cv2.imwrite(os.path.join(output_folder, fname), frame)
                        cap.release()
                        print(f"Object found! Saved: {fname}")
                        return True, round(confidence, 2), fname

        cap.release()
        print(f"   Finished scanning {video_file} - object not found")

    print("Object not found in any video")
    return False, 0.0, None