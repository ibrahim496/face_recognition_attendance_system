


from flask import Flask, render_template, request, redirect, url_for, escape, flash,session

from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from flask_login import current_user
from flask_login import AnonymousUserMixin
from mysql.connector.errors import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import boto3
import os
import mysql.connector
import cv2
import uuid

import base64

def lecturer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"current_user.is_authenticated: {current_user.is_authenticated}, current_user.role: {current_user.role}")
        if not current_user.is_authenticated or current_user.role != 'lecturer':
            return redirect(url_for('staff_login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


class AnonymousUser(AnonymousUserMixin):
    role = 'guest'



def load_student_faces():
    student_faces = {}
    for student_id, student_name in get_all_students():
        student_image_path = f'student_photos/{student_id}.jpg'
        if os.path.exists(student_image_path):
            student_image = face_recognition.load_image_file(student_image_path)
            student_faces[student_id] = face_recognition.face_encodings(student_image)[0]

    return student_faces



# Connect to the MySQL database
db = mysql.connector.connect(
    host='localhost',
    user='root',
    password='khalil4820',
    database='sys',
    auth_plugin='mysql_native_password'
)

app = Flask(__name__)
app.secret_key = 'khalil4820'
# Initialize the S3 client
s3 = boto3.client('s3',
                  region_name='eu-west-2',
                  aws_access_key_id='AKIASAQRD2NH325ZFA7O',
                  aws_secret_access_key='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'
                  )
print(f"S3 region: {s3.meta.region_name}")

rekognition = boto3.client('rekognition',
                           region_name='eu-west-2',
                           aws_access_key_id='AKIASAQRD2NH325ZFA7O',
                           aws_secret_access_key='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')

def create_collection():
    collection_name = 'students_collection'

    # Check if the collection already exists
    response = rekognition.list_collections()
    if collection_name in response['CollectionIds']:
        print(f"Collection '{collection_name}' already exists.")
        return collection_name

    # Create the collection if it does not exist
    response = rekognition.create_collection(CollectionId=collection_name)
    print(f"Collection '{collection_name}' created with ARN: {response['CollectionArn']}")
    return collection_name
    student_faces = load_student_faces()
    recognized_student_id = recognize_and_record_attendance(temp_image_path, student_faces, app.config['COLLECTION_ID'])



   

def recognize_and_record_attendance(s3_bucket, image_key, collection_id):
    rekognition_client = boto3.client(
        'rekognition',
        region_name='eu-west-2',
        aws_access_key_id='AKIASAQRD2NH325ZFA7O',
        aws_secret_access_key='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',
    )

    image_path = '/tmp/temp_image.jpg'  # Move this line here, before it is used
    s3.download_file(s3_bucket, image_key, image_path)
    
    with open(image_path, 'rb') as image_file:
        image_binary = image_file.read()

    response = rekognition_client.search_faces_by_image(
        CollectionId=collection_id,
        Image={'Bytes': image_binary},
        MaxFaces=1,
        FaceMatchThreshold=90
    )

    if len(response['FaceMatches']) > 0:
        recognized_student_id = response['FaceMatches'][0]['Face']['ExternalImageId']
        return recognized_student_id
    else:
        return None

    unknown_face_encoding = unknown_face_encodings[0]

    matches = face_recognition.compare_faces(list(student_faces.values()), unknown_face_encoding, tolerance=0.6)
    distances = face_recognition.face_distance(list(student_faces.values()), unknown_face_encoding)

    best_match_index = None
    if True in matches:
        best_match_index = matches.index(True)
        min_distance = min(distances)
        for index, match in enumerate(matches):
            if match and distances[index] < min_distance:
                best_match_index = index
                min_distance = distances[index]

    if best_match_index is not None:
        return list(student_faces.keys())[best_match_index]
    else:
        return None



@app.route('/')

def index():
    return redirect(url_for('staff_login'))




# register starts

@app.route('/register', methods=['GET', 'POST'])
@lecturer_required
def register():
    

    

    message = None
    if request.method == 'POST':
        student_id = request.form['student_id']
        password = request.form['password']
        student_first_name = request.form['student_first_name']
        student_last_name = request.form['student_last_name']
        print(f"student_id: {student_id}, Password: {password}")
        

        if 'image' in request.files:
            image = request.files['image']
            s3.upload_fileobj(image, 'attedance-recog', f'{student_id}.jpg')

        if 'image_data' in request.form:
            image_data = request.form['image_data']
            if image_data:
                image_data = image_data.split(',')[1]  # Remove the data URL prefix
                image_bytes = base64.b64decode(image_data)

                # Save the captured image to a temporary file
                temp_image_file = f"{uuid.uuid4()}.jpg"
                with open(temp_image_file, 'wb') as f:
                    f.write(image_bytes)

                # Upload the temporary file to the S3 bucket
                s3_bucket = 'attedance-recog'
                image_key = f"temp/{temp_image_file}"
                s3.upload_file(temp_image_file, s3_bucket, image_key)

                # Remove the temporary file after uploading
                os.remove(temp_image_file)

                # Add the student to the face collection
                response = rekognition.index_faces(
                    CollectionId=app.config['COLLECTION_ID'],
                    Image={
                        'S3Object': {
                            'Bucket': s3_bucket,
                            'Name': image_key
                        }
                    },
                    ExternalImageId=student_id
                )
                face_id = response['FaceRecords'][0]['Face']['FaceId']
                print(f"Added student '{student_id}' with face ID '{face_id}' to collection '{app.config['COLLECTION_ID']}'")

                cursor = db.cursor()
                query = "INSERT INTO students (student_id, password, student_first_name, student_last_name) VALUES (%s, %s, %s, %s)"
                values = (student_id, password, student_first_name, student_last_name)

                cursor.execute(query, values)
                db.commit()

        message = 'You have been registered'

    return render_template('register.html', message=message)
# register ends 





# student login 
@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        student_id = request.form['student_id']
        password = request.form['password']

        cursor = db.cursor()
        cursor.execute("SELECT student_id, password FROM students WHERE student_id = %s", (student_id,))
        student_data = cursor.fetchone()

        if student_data:
            print(f"Student data: {student_data}")
            print(f"Provided password: {password}, Stored password: {student_data[1]}")

            if password == student_data[1]:
                session['student_id'] = student_data[0]
                return redirect(url_for('attendance'))
            else:
                flash('Invalid Student ID or password', 'error')
        else:
            flash('Invalid Student ID or password', 'error')

    return render_template('student_login.html')



# student login  ends 




# attendance starts 
# attendance starts 
@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))

    if request.method == 'POST':
        image_data = request.form['image_data']
        if image_data:
            image_data = image_data.split(',')[1]  # Remove the data URL prefix
            image_bytes = base64.b64decode(image_data)

            # Save the captured image to a temporary file
            temp_image_file = f"{uuid.uuid4()}.jpg"
            with open(temp_image_file, 'wb') as f:
                f.write(image_bytes)
    
            # Upload the temporary file to the S3 bucket
            s3_bucket = 'attedance-recog'
            image_key = f"temp/{temp_image_file}"
            s3.upload_file(temp_image_file, s3_bucket, image_key)

            # Remove the temporary file after uploading
            os.remove(temp_image_file)

            recognized_student_id = recognize_and_record_attendance(s3_bucket, image_key, app.config['COLLECTION_ID'])
            if recognized_student_id:
                course_id = request.form['course_id']

                cursor = db.cursor()

                # Fetch student's name
                cursor.execute("SELECT student_first_name FROM students WHERE student_id = %s", (recognized_student_id,))
                student_name = cursor.fetchone()[0]

                # Fetch course name
                cursor.execute("SELECT name FROM courses WHERE id = %s", (course_id,))
                course_name = cursor.fetchone()[0]

                query = "INSERT INTO attendance (student_id, course_id) VALUES (%s, %s)"
                values = (recognized_student_id, course_id)
                
                try:
                    cursor.execute(query, values)
                    db.commit()
                    message = f"Attendance recorded for {student_name} (ID: {recognized_student_id}) in {course_name} (ID: {course_id})"
                except IntegrityError:
                    message = f"Attendance has already been taken for {student_name} (ID: {recognized_student_id}) in {course_name} (ID: {course_id})"
                except mysql.connector.DatabaseError:
                    message = f"Error: course_id is missing or invalid"
            else:
                message = "No student recognized"
            
            flash(message)

    cursor = db.cursor()
    cursor.execute("SELECT id, name FROM courses")
    courses = cursor.fetchall()

    return render_template('attendance.html', courses=courses)



    attendance_form = """
    
<html>
    <head>
        <title>Attendance</title>
    </head>
    <body>
        {{ message_element|safe }}

        <form method="post" enctype="multipart/form-data">
            <video id="video" width="640" height="480" autoplay></video>
            <canvas id="canvas" width="640" height="480"></canvas>
            <br>
            <button type="button" id="capture">Capture</button>
            <br>
            <input type="hidden" id="image_data" name="image_data">
            <input type="submit" value="Submit">
        </form>
        <script>
            const video = document.getElementById('video');
            const canvas = document.getElementById('canvas');
            const context = canvas.getContext('2d');
            const captureButton = document.getElementById('capture');
            const imageDataInput = document.getElementById('image_data');

            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                navigator.mediaDevices.getUserMedia({ video: true })
                    .then(function (stream) {
                        video.srcObject = stream;
                    })
                    .catch(function (err) {
                        console.log("An error occurred: " + err);
                    });
            }

            captureButton.addEventListener('click', function () {
                context.drawImage(video, 0, 0, 640, 480);
                imageDataInput.value = canvas.toDataURL('image/jpeg');
            });
        </script>
    </body>
</html>
    """
        
    return render_template('attendance.html', attendance_form=attendance_form, courses=courses)




                # attendance  ends
def get_all_courses():
    cursor = db.cursor()
    query = "SELECT id, name FROM courses"
    cursor.execute(query)
    courses = cursor.fetchall()
    return courses


      # create course  starts
@app.route('/create_course', methods=['GET', 'POST'])
@login_required
@lecturer_required
def create_course():
    message = None
    if request.method == 'POST':
        course_name = request.form['course_name']
        start_time = request.form['start_time']
        end_time = request.form['end_time']

        cursor = db.cursor()
        query = "INSERT INTO courses (name, start_time, end_time) VALUES (%s, %s, %s)"
        values = (course_name, start_time, end_time)
        cursor.execute(query, values)
        db.commit()

        message = 'Course created successfully'

    return render_template('create_course.html', message=message)




      # create course  ends

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'staff_login'
login_manager.anonymous_user = AnonymousUser

class Staff(UserMixin):
    def __init__(self, staff_id, username, password, role):
        self.id = staff_id
        self.username = username
        self.password = password
        self.role = role
     

@login_manager.user_loader
def load_staff(staff_id):
    cursor = db.cursor()
    cursor.execute("SELECT id, username, password, role FROM staff WHERE id = %s", (staff_id,))
    staff_data = cursor.fetchone()
    if staff_data:
        return Staff(*staff_data)
    else:
        return None

login_manager.init_app(app)
login_manager.login_view = 'staff_login'

 # view student attedance records
@app.route('/view_attendance', methods=['GET'])
@login_required
@lecturer_required
def view_attendance():
    course_filter = request.args.get('course_filter', '')
    attended_at = request.args.get('attended_at', '')

    cursor = db.cursor()

    # Fetch courses for the filter dropdown
    cursor.execute("SELECT id, name FROM courses")
    courses = cursor.fetchall()

    # Construct the base query
    query = """
    SELECT a.student_id, c.name, a.attended_at, 
    IF(a.attended_at > DATE_ADD(DATE_ADD(DATE_FORMAT(a.attended_at, '%Y-%m-%d'), INTERVAL TIME_TO_SEC(c.start_time) SECOND), INTERVAL 10 MINUTE), 'Late', 'Present') AS status
    FROM attendance AS a
    INNER JOIN students AS s ON a.student_id = s.student_id
    INNER JOIN courses AS c ON a.course_id = c.id
    """

    # Apply filters
    filters = []
    if course_filter:
        filters.append(f"c.id = {course_filter}")
    if attended_at:
        filters.append(f"DATE(a.attended_at) = '{attended_at}'")



    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY a.attended_at DESC"

    cursor.execute(query)
    attendance_data = cursor.fetchall()
    return render_template('view_attendance.html', attendance_data=attendance_data, courses=courses, course_filter=course_filter, attended_at=attended_at)



@app.route('/staff_login', methods=['GET', 'POST'])
def staff_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cursor = db.cursor()
        cursor.execute("SELECT id, username, password, role FROM staff WHERE username = %s", (username,))
        staff_data = cursor.fetchone()

        if staff_data and password == staff_data[2]:
            staff = Staff(*staff_data)
            login_user(staff)
            return redirect(url_for('staff_dashboard'))
        else:
          flash('Invalid username or password', 'error')
    return render_template('staff_login.html')

@app.route('/staff_logout')
@login_required
def staff_logout():
    logout_user()
    return redirect(url_for('staff_login'))

@app.route('/staff_dashboard')
@login_required
def staff_dashboard():
    cursor = db.cursor()
    query = "SELECT id, name FROM courses"
    cursor.execute(query)
    courses = cursor.fetchall()
    return render_template('staff_dashbord.html', current_user=current_user, courses=courses)


if __name__ == "__main__":
    collection_id = create_collection()
    app.config['COLLECTION_ID'] = collection_id
    app.run(debug=True,  host="0.0.0.0", port=5000)