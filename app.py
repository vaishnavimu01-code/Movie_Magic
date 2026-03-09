from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import boto3
from boto3.dynamodb.conditions import Attr
from decimal import Decimal
import uuid
import os
from botocore.exceptions import ClientError

app = Flask(__name__)

# Security & Config
app.secret_key = 'your_static_secret_key_here'
AWS_REGION = os.environ.get('AWS_REGION', 'ap-south-1')
SNS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:977099000730:MovieTicketNotifications'

# AWS Services
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sns = boto3.client('sns', region_name=AWS_REGION)
users_table = dynamodb.Table('MovieMagic_Users')
bookings_table = dynamodb.Table('MovieMagic_Bookings')
movies_table = dynamodb.Table('MovieMagic_Movies')

# --- HELPER: Convert DynamoDB Decimals to Integers/Floats ---
def replace_decimals(obj):
    if isinstance(obj, list):
        return [replace_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: replace_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj

def send_email(booking):
    if not SNS_TOPIC_ARN: return False
    try:
        msg = f"Hello {booking['user_name']},\n\nYour booking for {booking['movie_name']} is confirmed!\nBooking ID: {booking['booking_id']}\nSeats: {booking['seats']}\nAmount Paid: Rs. {booking['amount_paid']}\n\nEnjoy the show!"
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="MovieMagic Ticket Confirmed",
            Message=msg,
            MessageAttributes={'email': {'DataType': 'String', 'StringValue': booking['booked_by']}}
        )
        return True
    except Exception as e:
        print(f"SNS Error: {e}")
        return False

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        name = request.form['name']
        try:
            if 'Item' in users_table.get_item(Key={'email': email}):
                flash('Email already registered', 'danger')
                return redirect(url_for('signup'))
            # Default theme is 'dark'
            users_table.put_item(Item={
                'id': str(uuid.uuid4()), 
                'name': name, 
                'email': email, 
                'password': password, 
                'theme': 'dark'
            })
            flash('Account created! Please login.', 'success')
            return redirect(url_for('login'))
        except ClientError:
            flash('Error creating account', 'danger')
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Admin Login Check
        if email == "admin@moviemagic.com" and password == "admin123":
            session['user'] = {'name': 'Administrator', 'email': email, 'is_admin': True, 'theme': 'dark'}
            return redirect(url_for('admin_dashboard'))

        try:
            response = users_table.get_item(Key={'email': email})
            if 'Item' in response:
                user = response['Item']
                if check_password_hash(user['password'], password):
                    session['user'] = {
                        'name': user['name'], 
                        'email': user['email'],
                        'theme': user.get('theme', 'dark') # Load User Theme
                    }
                    return redirect(url_for('dashboard'))
            flash('Invalid credentials', 'danger')
        except ClientError:
            flash('Login error', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# --- DASHBOARD & MOVIES ---

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('login'))
    try:
        response = movies_table.scan()
        movies = replace_decimals(response.get('Items', [])) 
    except ClientError as e:
        movies = []
    return render_template('dashboard.html', movies=movies)

@app.route('/movie/<movie_id>')
def movie_details(movie_id):
    if 'user' not in session: return redirect(url_for('login'))
    try:
        response = movies_table.get_item(Key={'movie_id': movie_id})
        movie = replace_decimals(response.get('Item'))
        if not movie: 
            flash('Movie not found', 'danger')
            return redirect(url_for('dashboard'))
        return render_template('movie_details.html', movie=movie)
    except ClientError:
        flash('Error loading movie', 'danger')
        return redirect(url_for('dashboard'))

# --- BOOKING & PAYMENT ---

@app.route('/booking')
def booking():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('booking.html',
                           movie=request.args.get('movie'),
                           theater=request.args.get('theater'),
                           address=request.args.get('address'),
                           price=request.args.get('price'))

@app.route('/payment', methods=['POST'])
def payment():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('payment.html', booking_details=request.form)

@app.route('/confirm_booking', methods=['POST'])
def confirm_booking():
    if 'user' not in session: return redirect(url_for('login'))
    data = request.form
    try:
        booking_id = f"MM-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
        fake_payment_id = f"PAY-{str(uuid.uuid4())[:12].upper()}"

        booking_item = {
            'booking_id': booking_id,
            'movie_name': data.get('movie'),
            'theater': data.get('theater'),
            'date': data.get('date'),
            'time': data.get('time'),
            'seats': data.get('seats'),
            'amount_paid': data.get('amount'),
            'address': data.get('address'),
            'booked_by': session['user']['email'],
            'user_name': session['user']['name'],
            'payment_id': fake_payment_id,
            'booking_time': datetime.now().isoformat()
        }
        
        bookings_table.put_item(Item=booking_item)
        send_email(booking_item)
        return render_template('confirmation.html', booking=booking_item)
    except Exception as e:
        print(e)
        flash('Booking failed.', 'danger')
        return redirect(url_for('dashboard'))

# --- USER PROFILE ---

@app.route('/profile')
def profile():
    if 'user' not in session: return redirect(url_for('login'))
    user_email = session['user']['email']
    user_bookings = []
    user_info = {}
    try:
        user_response = users_table.get_item(Key={'email': user_email})
        if 'Item' in user_response:
            user_info = user_response['Item']
            # Ensure theme key exists for template
            if 'theme' not in user_info:
                user_info['theme'] = 'dark'
        else:
            user_info = session['user']

        response = bookings_table.scan(FilterExpression=Attr('booked_by').eq(user_email))
        user_bookings = replace_decimals(response.get('Items', []))
    except ClientError:
        pass
    return render_template('profile.html', user=user_info, bookings=user_bookings)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session: return redirect(url_for('login'))
    email = session['user']['email']
    
    fields = {
        'first_name': request.form.get('first_name', ''),
        'last_name': request.form.get('last_name', ''),
        'mobile': request.form.get('mobile', ''),
        'birthday': request.form.get('birthday', ''),
        'gender': request.form.get('gender', ''),
        'married': request.form.get('married', ''),
        'theme': request.form.get('theme', 'dark') # Get Theme Choice
    }
    fields['name'] = f"{fields['first_name']} {fields['last_name']}".strip() or session['user']['name']

    try:
        # Update DynamoDB including 'theme'
        users_table.update_item(
            Key={'email': email},
            UpdateExpression="set #n=:n, first_name=:fn, last_name=:ln, mobile=:m, birthday=:b, gender=:g, married=:ma, theme=:t",
            ExpressionAttributeNames={'#n': 'name'},
            ExpressionAttributeValues={
                ':n': fields['name'], ':fn': fields['first_name'], ':ln': fields['last_name'],
                ':m': fields['mobile'], ':b': fields['birthday'], ':g': fields['gender'], 
                ':ma': fields['married'], ':t': fields['theme']
            }
        )
        # Update Session Data immediately
        session['user']['name'] = fields['name']
        session['user']['theme'] = fields['theme']
        session.modified = True
        
        flash('Profile updated successfully!', 'success')
    except ClientError:
        flash('Error updating profile', 'danger')
    return redirect(url_for('profile'))

# --- ADMIN PORTAL ---

@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or not session.get('user', {}).get('is_admin'):
        return redirect(url_for('login'))
    try:
        response = movies_table.scan()
        movies = replace_decimals(response.get('Items', []))
    except ClientError:
        movies = []
    return render_template('admin.html', movies=movies)

@app.route('/add_movie', methods=['POST'])
def add_movie():
    if 'user' not in session or not session.get('user', {}).get('is_admin'): return redirect(url_for('login'))
    try:
        price = request.form['price']
        if not price: price = 0
        rating = request.form['rating']
        if not rating: rating = 0

        movie_item = {
            'movie_id': str(uuid.uuid4()),
            'title': request.form['title'],
            'genre': request.form['genre'],
            'language': request.form['language'],
            'duration': request.form['duration'],
            'image': request.form['image'],
            'trailer': request.form['trailer'],
            'price': Decimal(str(price)),
            'rating': Decimal(str(rating)),
            'theater': request.form['theater'],
            'address': request.form['address'],
            'description': request.form['description']
        }
        movies_table.put_item(Item=movie_item)
        flash('Movie added successfully!', 'success')
    except Exception as e:
        print(e)
        flash('Error adding movie', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/edit_movie/<movie_id>', methods=['POST'])
def edit_movie(movie_id):
    if 'user' not in session or not session.get('user', {}).get('is_admin'): return redirect(url_for('login'))
    try:
        price = request.form['price']
        if not price: price = 0
        rating = request.form['rating']
        if not rating: rating = 0

        movies_table.update_item(
            Key={'movie_id': movie_id},
            UpdateExpression="set title=:t, genre=:g, #l=:l, #d=:d, image=:i, trailer=:tr, price=:p, rating=:r, theater=:th, address=:a, description=:desc",
            ExpressionAttributeNames={
                '#l': 'language',
                '#d': 'duration'
            },
            ExpressionAttributeValues={
                ':t': request.form['title'],
                ':g': request.form['genre'],
                ':l': request.form['language'],
                ':d': request.form['duration'],
                ':i': request.form['image'],
                ':tr': request.form['trailer'],
                ':p': Decimal(str(price)),
                ':r': Decimal(str(rating)),
                ':th': request.form['theater'],
                ':a': request.form['address'],
                ':desc': request.form['description']
            }
        )
        flash('Movie updated successfully!', 'success')
    except ClientError as e:
        print(e)
        flash('Error updating movie', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_movie/<movie_id>')
def delete_movie(movie_id):
    if 'user' not in session or not session.get('user', {}).get('is_admin'): return redirect(url_for('login'))
    try:
        movies_table.delete_item(Key={'movie_id': movie_id})
        flash('Movie deleted', 'success')
    except ClientError:
        flash('Error deleting movie', 'danger')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
