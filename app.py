from flask import Flask, render_template, request, redirect, url_for, session
from datetime import date
import uuid
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- SAMPLE DATA FOR LOCAL TESTING ----------------

users = []

movies = [
    {
        "movie_id": "m1",
        "title": "Avengers Endgame",
        "genre": "Action",
        "available_seats": 120,
        "price":190,
        "language":"English",
        "poster": "avengers_endgame.jpg"
    },
    {
        "movie_id": "m2",
        "title": "Interstellar",
        "genre": "Sci-Fi",
        "available_seats": 150,
        "price":190,
        "language":"English",
        "poster": "interstellar.png"
    },
    {
        "movie_id": "m3",
        "title": "Spider Man No Way Home",
        "genre": "Action",
        "available_seats": 100,
        "price":190,
        "language":"English",
        "poster":"spiderman_nowayhome.jpg"
    }
]

# ---------------- ROUTES ----------------

@app.route('/')
def index():
    return render_template('index.html')


# REGISTER
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        user = {
            "user_id": str(uuid.uuid4()),
            "username": request.form['name'],
            "email": request.form['email'],
            "password": request.form['password']
        }

        users.append(user)

        return redirect(url_for('login'))

    return render_template('register.html')


# LOGIN
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        for user in users:
            if user['email'] == email and user['password'] == password:

                session['user'] = user['username']
                session['user_id'] = user['user_id']

                return redirect(url_for('home'))

        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

#USER PROFILE

@app.route("/profile")
def profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = next((u for u in users if u['user_id'] == session['user_id']), None)

    bookings = [
        {"movie": "Avatar", "date": "12-03-2026", "seats": "A1,A2"},
        {"movie": "RRR", "date": "15-03-2026", "seats": "B5,B6"}
    ]

    return render_template("profile.html", user=user, bookings=bookings)

#EDIT PROFILE

@app.route("/edit_profile", methods=["GET","POST"])
def edit_profile():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = next((u for u in users if u['user_id'] == session['user_id']), None)

    if user is None:
        return redirect(url_for("login"))

    if request.method == "POST":
        user["username"] = request.form.get("name")
        user["email"] = request.form.get("email")

        session["user"] = user["username"]

        return redirect(url_for("profile"))

    return render_template("edit_profile.html", user=user)
        
#ADMIN PAGE

@app.route("/admin")
def admin():
    return render_template("admin.html", movies=movies)

#ADMIN ADD-MOVIE

@app.route("/add_movie", methods=["POST"])
def add_movie():

    poster_file = request.files["poster"]
    poster_filename = poster_file.filename

    save_path = os.path.join("static", poster_filename)
    poster_file.save(save_path)

    new_movie = {
        "movie_id": len(movies) + 1,
        "title": request.form["title"],
        "genre": request.form["genre"],
        "language": request.form["language"],
        "price": int(request.form["price"]),
        "poster": poster_filename,
        "show_times": request.form["show_times"].split(",")
    }

    movies.append(new_movie)

    return redirect("/admin")

#ADMIN REMOVE-MOVIE

@app.route("/delete_movie/<int:movie_id>")
def delete_movie(movie_id):
    global movies
    movies = [m for m in movies if m["movie_id"] != movie_id]
    return redirect("/admin")


# HOME PAGE
@app.route('/home')
def home():

    if 'user' not in session:
        return redirect(url_for('login'))

    return render_template('home.html', user=session['user'], movies=movies)


# SEARCH
@app.route('/search', methods=['GET','POST'])
def search():

    if request.method == 'POST':

        query = request.form.get('movie','')

        results = [m for m in movies if query.lower() in m['title'].lower()]

        return render_template('search.html', movies=results)

    return render_template('search.html', movies=[])


# BOOK MOVIE
@app.route('/book/<string:movie_id>', methods=['GET','POST'])
def book(movie_id):

    movie = next((m for m in movies if m['movie_id'] == movie_id), None)

    movie['show_times'] = ["10:00 AM", "2:00 PM", "6:00 PM", "9:00 PM"]

    theaters = [
        {"name": "PVR Cinemas", "location": "City Center"},
        {"name": "INOX", "location": "Mall Road"},
        {"name": "Cinepolis", "location": "Downtown"}
    ]

    today = date.today().isoformat()

    if request.method == 'POST':

        seats = request.form['seats']

        return render_template(
            'ticket.html',
            title=movie['title'],
            date=request.form['date'],
            time=request.form['time'],
            seats=seats,
            address=request.form['address'],
            amount=request.form['amount'],
            user=session['user']
        )

    return render_template('book.html', movie=movie, theaters=theaters, today=today)


# LOGOUT
@app.route('/logout')
def logout():

    session.clear()

    return redirect(url_for('index'))


# RUN SERVER
if __name__ == '__main__':
    app.run(debug=True)
