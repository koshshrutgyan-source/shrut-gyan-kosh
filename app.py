from flask import Flask, render_template, request, redirect, url_for, flash, session  # type: ignore
import pandas as pd  # type: ignore
from functools import wraps
import firebase_admin  # type: ignore
from firebase_admin import credentials, auth  # type: ignore
import gspread  # type: ignore # NEW ✅
from oauth2client.service_account import ServiceAccountCredentials  # type: ignore # NEW ✅


# ----------------- Firebase Init -----------------
cred = credentials.Certificate("firebase_key.json")  # 🔑 your Firebase key JSON
firebase_admin.initialize_app(cred)

# -------- GOOGLE SHEETS SETUP --------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("gsheet_key.json", scope)
client = gspread.authorize(creds)

# Open your Google Sheet (make sure you created one!)
sheet = client.open("JoinUs Submissions").sheet1  # name of your sheet


# ----------------- Flask Init -----------------
app = Flask(__name__)
app.secret_key = "supersecretkey"  # change to a long random string


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

@app.route('/search')
def search():
    if "user" not in session:
        flash("⚠️ Please login to use search functionality!", "warning")
        return redirect(url_for("login"))

    query = request.args.get("q", "")
    page = int(request.args.get("page", 1))
    per_page = 10

    try:
        df = pd.read_excel("books.xlsx")  # change filename if needed
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

    return render_template("search.html",
                           results=paginated,
                           query=query,
                           page=page,
                           total=total,
                           per_page=per_page)

@app.route('/about')
def about():
    return render_template("about.html")

@app.route('/team')
def team():
    return render_template("team.html")

@app.route('/contact')
def contact():
    return render_template("contact.html")

@app.route('/supporters')
def supporters():
    return render_template("supporters.html")

@app.route('/join', methods=["GET", "POST"])
def join():
    if "user" not in session:
        flash("⚠️ Please login to access Join Us form.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        city = request.form["city"]

        # -------- Save to Excel (local backup) --------
        new_data = pd.DataFrame([{
            "Name": name,
            "Email": email,
            "Mobile": mobile,
            "City": city
        }])

        try:
            existing = pd.read_excel("join_data.xlsx")
            updated = pd.concat([existing, new_data], ignore_index=True)
        except FileNotFoundError:
            updated = new_data

        updated.to_excel("join_data.xlsx", index=False)

        # -------- Save to Google Sheets (online) --------
        sheet.append_row([name, email, mobile, city])

        flash("✅ Thank you for joining! Your information has been saved.", "success")
        return redirect(url_for("home"))
    
    return render_template("join.html")


if __name__ == "__main__":
    app.run(debug=True)
