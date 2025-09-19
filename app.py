import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
from functools import wraps
import firebase_admin
from firebase_admin import credentials, auth, firestore
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ----------------- Firebase Init -----------------
def get_firebase_cred():
    firebase_env = os.environ.get("FIREBASE_KEY_JSON")
    if firebase_env:
        return credentials.Certificate(json.loads(firebase_env))
    if os.path.exists("firebase_key.json"):
        return credentials.Certificate("firebase_key.json")
    raise RuntimeError("Firebase credentials not found in environment variable or firebase_key.json file.")

try:
    cred = get_firebase_cred()
    firebase_admin.initialize_app(cred)
except Exception as e:
    print("❌ Firebase initialization failed:", e)
    raise

# Firestore client
db = firestore.client()

# -------- GOOGLE SHEETS SETUP --------
def get_gsheet_creds():
    gsheet_env = os.environ.get("GSHEET_KEY_JSON")
    if gsheet_env:
        return ServiceAccountCredentials.from_json_keyfile_dict(json.loads(gsheet_env), [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ])
    if os.path.exists("gsheet_key.json"):
        return ServiceAccountCredentials.from_json_keyfile_name("gsheet_key.json", [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ])
    raise RuntimeError("Google Sheets credentials not found in environment variable or gsheet_key.json file.")

try:
    creds = get_gsheet_creds()
    client = gspread.authorize(creds)
    sheet = client.open("JoinUs Submissions").sheet1
except Exception as e:
    print("❌ Google Sheets initialization failed:", e)
    sheet = None

# ----------------- Flask Init -----------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey")

# ----------------- Helpers -----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("⚠️ Please login to use this feature.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- Routes -----------------
@app.route('/')
def home():
    return render_template("index.html")

@app.route('/explore')
def explore():
    if "user" in session:
        return redirect(url_for("search"))
    else:
        flash("⚠️ Please login to explore books.", "warning")
        return redirect(url_for("login"))

@app.route('/login', methods=["GET"])
def login():
    return render_template("login.html")

@app.route('/sessionLogin', methods=["POST"])
def session_login():
    id_token = request.json.get("idToken")
    try:
        decoded = auth.verify_id_token(id_token)
        session["user"] = decoded.get("email") or decoded.get("uid")
        session["name"] = decoded.get("name") or session["user"]
        session["uid"]  = decoded.get("uid")
        flash("✅ Logged in successfully.", "success")
        return {"ok": True}
    except Exception as e:
        print("Token verify failed:", e)
        return {"ok": False, "error": "Invalid token"}, 401

@app.route('/logout')
def logout():
    session.clear()
    flash("❌ Logged out successfully.", "danger")
    return redirect(url_for("home"))

# ----------------- SEARCH -----------------
@app.route('/search')
@login_required
def search():
    query = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    per_page = 10

    try:
        df = pd.read_excel("books.xlsx")
    except FileNotFoundError:
        flash("⚠️ Books database not found!", "danger")
        return render_template("search.html", results=[], query=query, page=page, total=0, per_page=per_page)

    results_df = df.copy()
    if query:
        results_df = df[
            df['Name Of Book'].str.contains(query, case=False, na=False) |
            df['Writter Name'].str.contains(query, case=False, na=False) |
            df['Langauge/ Script'].str.contains(query, case=False, na=False)
        ]

    total = len(results_df)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = results_df.iloc[start:end].to_dict(orient="records")

    return render_template("search.html", results=paginated, query=query, page=page, total=total, per_page=per_page)

# ----------------- Static Pages -----------------
@app.route('/about')
def about(): return render_template("about.html")
@app.route('/team')
def team(): return render_template("team.html")
@app.route('/contact')
def contact(): return render_template("contact.html")
@app.route('/supporters')
def supporters(): return render_template("supporters.html")

# ----------------- PROFILE -----------------
@app.route('/profile', methods=["GET", "POST"])
@login_required
def profile():
    user_data = {
        "name": session.get("name") or "",
        "email": session.get("user"),
        "mobile": "",
        "dob": "",
        "qualification": "",
        "profile_pic": ""
    }

    if request.method == "POST":
        name  = request.form.get("name").strip()
        mobile = request.form.get("mobile").strip()
        dob    = request.form.get("dob").strip()
        qualification = request.form.get("qualification").strip()

        db.collection("users").document(name).set({
            "name": name,
            "email": session["user"],
            "mobile": mobile,
            "dob": dob,
            "qualification": qualification
        })

        user_data.update({
            "name": name,
            "mobile": mobile,
            "dob": dob,
            "qualification": qualification
        })
        flash("✅ Profile updated successfully!", "success")
    else:
        existing_name = session.get("name") or session.get("user")
        doc = db.collection("users").document(existing_name).get()
        if doc.exists:
            user_data.update(doc.to_dict())

    return render_template("profile.html", user=user_data)

# ----------------- JOIN -----------------
@app.route('/join', methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        city = request.form["city"]

        new_data = pd.DataFrame([{"Name": name,"Email": email,"Mobile": mobile,"City": city}])
        try:
            existing = pd.read_excel("join_data.xlsx")
            updated = pd.concat([existing, new_data], ignore_index=True)
        except FileNotFoundError:
            updated = new_data
        updated.to_excel("join_data.xlsx", index=False)

        if sheet:
            try:
                sheet.append_row([name, email, mobile, city])
            except Exception as e:
                print("Google Sheets append_row error:", e)
                flash("⚠️ Could not save to Google Sheets, but your data is backed up locally.", "warning")
        else:
            flash("⚠️ Could not save to Google Sheets, but your data is backed up locally.", "warning")

        flash("✅ Thank you for joining! Your information has been saved.", "success")
        return redirect(url_for("home"))

    return render_template("join.html")

# ----------------- ADMIN PANEL -----------------
ADMIN_EMAILS = ["abhyudayapjain@gmail.com", "vaibhavjain22112004@gmail.com", "colleague2@gmail.com"]

@app.route('/admin')
@login_required
def admin_panel():
    if session["user"] not in ADMIN_EMAILS:
        flash("⚠️ Admin access only.", "danger")
        return redirect(url_for("home"))

    profiles_ref = db.collection("users").stream()
    profiles = [{"id": doc.id, **doc.to_dict()} for doc in profiles_ref]

    join_data = []
    if sheet:
        try:
            join_data = sheet.get_all_records()
        except Exception as e:
            print("Error fetching JoinUs data:", e)

    return render_template("admin.html", profiles=profiles, join_data=join_data)

# ----------------- Run Flask -----------------
if __name__ == "__main__":
    app.run(debug=True)
