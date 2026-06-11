from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import csv
import json
import os
import random
import hashlib
import re
from datetime import datetime

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

app = Flask(__name__)
app.secret_key = "interviewai_secret_2024"

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
QUESTION_BANK_FILE = "questions_bank.csv"
QUESTIONS_PER_ROUND = 10
TOTAL_ROUNDS = 3
PERSONALIZED_QUESTIONS_PER_ROUND = 2
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".txt", ".docx"}
SKILL_KEYWORDS = {
    "python", "java", "javascript", "react", "flask", "django", "sql", "mysql",
    "postgresql", "mongodb", "html", "css", "machine learning", "data analysis",
    "pandas", "numpy", "power bi", "tableau", "excel", "spring boot", "node.js",
    "git", "api", "rest", "docker", "aws", "azure", "c", "c++"
}
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "your", "about",
    "using", "used", "into", "their", "will", "would", "could", "should", "where",
    "when", "then", "than", "been", "were", "they", "them", "also", "while", "into"
}

# ── Helpers ───────────────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def allowed_resume_file(filename):
    return os.path.splitext(filename.lower())[1] in ALLOWED_RESUME_EXTENSIONS

def extract_text_from_resume(filepath):
    ext = os.path.splitext(filepath.lower())[1]
    if ext == ".txt":
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if ext == ".pdf":
        if PdfReader is None:
            raise RuntimeError("PyPDF2 is not installed, so PDF resumes are not supported yet.")
        reader = PdfReader(filepath)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if ext == ".docx":
        if Document is None:
            raise RuntimeError("python-docx is not installed, so DOCX resumes are not supported yet.")
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    raise RuntimeError("Unsupported file type.")

def clean_resume_text(text):
    return re.sub(r"\s+", " ", text).strip()

def extract_section_lines(raw_text, section_name):
    lines = [line.strip(" -•\t") for line in raw_text.splitlines()]
    capture = False
    section_lines = []
    section_pattern = re.compile(rf"^{re.escape(section_name)}\s*$", re.I)
    header_pattern = re.compile(r"^[A-Z][A-Za-z /&]{2,40}$")
    for line in lines:
        if not line:
            if capture and section_lines:
                break
            continue
        if section_pattern.match(line):
            capture = True
            continue
        if capture:
            if header_pattern.match(line) and line.lower() != section_name.lower():
                break
            section_lines.append(line)
    return section_lines

def extract_skills(raw_text):
    text_lower = raw_text.lower()
    found = []
    for skill in sorted(SKILL_KEYWORDS):
        if skill in text_lower:
            found.append(skill.title())
    section_lines = extract_section_lines(raw_text, "skills")
    for line in section_lines:
        for part in re.split(r"[,|/]", line):
            token = part.strip()
            if token and len(token) <= 30:
                found.append(token.title())
    deduped = []
    seen = set()
    for item in found:
        key = item.lower()
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped[:12]

def extract_projects(raw_text):
    section_lines = extract_section_lines(raw_text, "projects")
    projects = []
    for line in section_lines:
        if len(line) >= 12:
            projects.append(line)
    if not projects:
        for line in raw_text.splitlines():
            cleaned = line.strip(" -•\t")
            if "project" in cleaned.lower() and len(cleaned) >= 12:
                projects.append(cleaned)
    return projects[:4]

def extract_education(raw_text):
    lines = [line.strip(" -•\t") for line in extract_section_lines(raw_text, "education")]
    if lines:
        return lines[:3]
    fallback = []
    for line in raw_text.splitlines():
        cleaned = line.strip(" -•\t")
        lower = cleaned.lower()
        if any(word in lower for word in ["b.tech", "btech", "b.e", "be ", "mca", "bca", "degree", "university", "college"]):
            fallback.append(cleaned)
    return fallback[:3]

def extract_resume_profile(raw_text):
    cleaned_text = clean_resume_text(raw_text)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
    phone_match = re.search(r"(\+?\d[\d\s-]{8,}\d)", raw_text)
    words = re.findall(r"[A-Za-z][A-Za-z\+\#\.]{2,}", raw_text)
    keywords = []
    seen = set()
    for word in words:
        lower = word.lower()
        if lower in STOPWORDS or len(lower) < 4:
            continue
        if lower not in seen:
            keywords.append(word.title())
            seen.add(lower)
    return {
        "candidate_name": first_line[:80] if first_line else "",
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0) if phone_match else "",
        "skills": extract_skills(raw_text),
        "projects": extract_projects(raw_text),
        "education": extract_education(raw_text),
        "top_keywords": keywords[:15],
        "resume_excerpt": cleaned_text[:500],
        "uploaded_at": datetime.now().strftime("%d %b %Y %I:%M %p")
    }

def keyword_tokens(*values):
    tokens = []
    seen = set()
    for value in values:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9\+\#\.]{2,}", value):
            lower = token.lower()
            if lower not in seen and lower not in STOPWORDS:
                tokens.append(token.lower())
                seen.add(lower)
    return tokens[:8]

def generate_resume_questions(profile, category, round_num):
    if not profile:
        return []
    personalized = []
    skills = profile.get("skills", [])
    projects = profile.get("projects", [])
    primary_skill = skills[0] if skills else ""
    primary_project = projects[0] if projects else ""

    if category == "hr":
        if primary_project:
            personalized.append({
                "question": f"Tell me about the project '{primary_project[:60]}' from your resume and the impact you created.",
                "keywords": keyword_tokens(primary_project, "impact ownership outcome result challenge"),
                "difficulty": "medium",
                "personalized": True
            })
        if skills:
            personalized.append({
                "question": f"Which skill from your resume best represents you in real work, and how have you applied {primary_skill} in practice?",
                "keywords": keyword_tokens(primary_skill, "applied example practice result learning"),
                "difficulty": "medium",
                "personalized": True
            })

    if category == "tech":
        if primary_skill:
            personalized.append({
                "question": f"Your resume mentions {primary_skill}. Describe one real problem you solved using {primary_skill}.",
                "keywords": keyword_tokens(primary_skill, "problem solution design implementation"),
                "difficulty": "medium" if round_num == 1 else "hard",
                "personalized": True
            })
        if primary_project:
            personalized.append({
                "question": f"In your project '{primary_project[:55]}', what was the architecture or technical flow from input to output?",
                "keywords": keyword_tokens(primary_project, "architecture api database frontend backend"),
                "difficulty": "hard" if round_num >= 2 else "medium",
                "personalized": True
            })

    if category == "data":
        focus = primary_skill or "data analysis"
        personalized.append({
            "question": f"Your resume highlights {focus}. Explain a data-driven decision or insight you produced using that skill.",
            "keywords": keyword_tokens(focus, "data insight analysis result metrics"),
            "difficulty": "medium",
            "personalized": True
        })
        if primary_project:
            personalized.append({
                "question": f"For the project '{primary_project[:55]}', how did you collect, clean, or analyze the data?",
                "keywords": keyword_tokens(primary_project, "collect clean analyze preprocess dashboard"),
                "difficulty": "hard" if round_num >= 2 else "medium",
                "personalized": True
            })

    return personalized[:PERSONALIZED_QUESTIONS_PER_ROUND]

def get_resume_profile_for_user(email):
    users = load_users()
    user = users.get(email, {})
    return user.get("resume_profile")

def save_resume_profile_for_user(email, filename, profile):
    users = load_users()
    if email not in users:
        return
    users[email]["resume_filename"] = filename
    users[email]["resume_profile"] = profile
    save_users(users)

def resolve_data_file(filename):
    primary_path = os.path.join(DATA_DIR, filename)
    if os.path.exists(primary_path):
        return primary_path
    fallback_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(fallback_path):
        return fallback_path
    raise FileNotFoundError(f"Data file not found: {filename}")

def load_questions(category):
    filepath = resolve_data_file(QUESTION_BANK_FILE)
    questions = {1: [], 2: [], 3: []}
    with open(filepath, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("category", "").strip().lower() != category:
                continue
            r = int(row['round'])
            questions[r].append({
                "question": row['question'],
                "keywords": row['expected_keywords'].split(),
                "difficulty": row['difficulty']
            })
    return questions

def score_answer(answer, keywords):
    """Score answer based on keyword matching - Python logic"""
    if not answer or len(answer.strip()) < 5:
        return 0
    answer_lower = answer.lower()
    matched = sum(1 for kw in keywords if kw.lower() in answer_lower)
    keyword_score = min(100, int((matched / max(len(keywords), 1)) * 100))
    # Length bonus - longer answers score better
    words = len(answer.split())
    length_score = min(30, words * 2)
    total = min(100, keyword_score + length_score)
    return total

def get_pass_threshold():
    return 60  # Must score 60%+ average to pass a round

# ── Auth Routes ───────────────────────────────────────────────
@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        users = load_users()
        if email not in users:
            return jsonify({"success": False, "error": "No account found. Please sign up."})
        if users[email]["password"] != hash_password(password):
            return jsonify({"success": False, "error": "Incorrect password."})
        session["user"] = email
        session["name"] = users[email]["name"]
        return jsonify({"success": True})
    return render_template("login.html")

@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not name or not email or not password:
        return jsonify({"success": False, "error": "All fields are required."})
    if "@" not in email:
        return jsonify({"success": False, "error": "Enter a valid email."})
    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters."})
    users = load_users()
    if email in users:
        return jsonify({"success": False, "error": "Account already exists. Please login."})
    users[email] = {
        "name": name,
        "email": email,
        "password": hash_password(password),
        "created": datetime.now().strftime("%d %b %Y"),
        "sessions": []
    }
    save_users(users)
    session["user"] = email
    session["name"] = name
    return jsonify({"success": True})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Dashboard ─────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    users = load_users()
    user = users.get(session["user"], {})
    sessions = user.get("sessions", [])
    resume_profile = user.get("resume_profile")
    return render_template("dashboard_v2.html", 
                           name=session["name"], 
                           sessions=sessions,
                           sessions_json=json.dumps(sessions),
                           resume_profile_json=json.dumps(resume_profile))

@app.route("/resume")
def resume_page():
    if "user" not in session:
        return redirect(url_for("login"))
    resume_profile = get_resume_profile_for_user(session["user"])
    return render_template("resume.html",
                           name=session["name"],
                           resume_profile_json=json.dumps(resume_profile))

@app.route("/api/resume/upload", methods=["POST"])
def upload_resume():
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    if "resume" not in request.files:
        return jsonify({"success": False, "error": "Please choose a resume file."}), 400
    file = request.files["resume"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Please choose a resume file."}), 400
    if not allowed_resume_file(file.filename):
        return jsonify({"success": False, "error": "Upload a PDF, TXT, or DOCX resume."}), 400

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1].lower()
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", session["user"].split("@")[0]).strip("_") or "resume"
    stored_name = f"{safe_name}_resume{ext}"
    filepath = os.path.join(UPLOADS_DIR, stored_name)
    file.save(filepath)

    try:
        raw_text = extract_text_from_resume(filepath)
        if len(clean_resume_text(raw_text)) < 50:
            raise RuntimeError("Resume text could not be extracted clearly. Try a text-based PDF or TXT file.")
        profile = extract_resume_profile(raw_text)
        save_resume_profile_for_user(session["user"], file.filename, profile)
        return jsonify({"success": True, "profile": profile, "filename": file.filename})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# ── Interview Routes ──────────────────────────────────────────
@app.route("/choose")
def choose():
    if "user" not in session:
        return redirect(url_for("login"))
    resume_profile = get_resume_profile_for_user(session["user"])
    return render_template("choose.html", name=session["name"], resume_profile=resume_profile)

@app.route("/interview")
def interview():
    if "user" not in session:
        return redirect(url_for("login"))
    category = request.args.get("category", "hr")
    resume_profile = get_resume_profile_for_user(session["user"])
    return render_template("interview.html", 
                           category=category,
                           name=session["name"],
                           resume_profile_json=json.dumps(resume_profile))

@app.route("/api/get_questions", methods=["POST"])
def get_questions():
    """Load questions for current round"""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    category = data.get("category", "hr")
    round_num = int(data.get("round", 1))
    questions = load_questions(category)
    round_questions = questions.get(round_num, [])
    random.shuffle(round_questions)
    resume_profile = get_resume_profile_for_user(session["user"])
    personalized_questions = generate_resume_questions(resume_profile, category, round_num)
    base_count = max(0, QUESTIONS_PER_ROUND - len(personalized_questions))
    selected = round_questions[:base_count] + personalized_questions
    random.shuffle(selected)
    return jsonify({
        "questions": selected,
        "round": round_num,
        "total_rounds": TOTAL_ROUNDS,
        "questions_per_round": QUESTIONS_PER_ROUND,
        "pass_threshold": get_pass_threshold(),
        "resume_personalized": bool(personalized_questions)
    })

@app.route("/api/score_answer", methods=["POST"])
def api_score_answer():
    """Score a single answer using Python keyword matching"""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    answer = data.get("answer", "")
    keywords = data.get("keywords", [])
    question = data.get("question", "")
    score = score_answer(answer, keywords)
    # Generate feedback based on score
    if score >= 80:
        feedback = "Excellent answer! You covered the key concepts clearly."
    elif score >= 60:
        feedback = "Good answer. Try to include more specific details or examples."
    elif score >= 40:
        feedback = "Partial answer. Make sure to address all aspects of the question."
    else:
        feedback = "Answer needs improvement. Try to use more relevant terminology."
    passed = score >= get_pass_threshold()
    return jsonify({
        "score": score,
        "feedback": feedback,
        "passed": passed,
        "keywords_matched": [kw for kw in keywords if kw.lower() in answer.lower()]
    })

@app.route("/api/save_session", methods=["POST"])
def save_session_data():
    """Save completed interview session"""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    users = load_users()
    email = session["user"]
    session_record = {
        "date": datetime.now().strftime("%d %b %Y"),
        "time": datetime.now().strftime("%I:%M %p"),
        "category": data.get("category", "hr"),
        "rounds_completed": data.get("rounds_completed", 0),
        "total_rounds": TOTAL_ROUNDS,
        "overall_score": data.get("overall_score", 0),
        "round_scores": data.get("round_scores", []),
        "question_results": data.get("question_results", []),
        "verdict": data.get("verdict", "practice"),
        "eliminated_at": data.get("eliminated_at", None)
    }
    users[email]["sessions"].insert(0, session_record)
    users[email]["sessions"] = users[email]["sessions"][:20]  # keep last 20
    save_users(users)
    return jsonify({"success": True})

@app.route("/result")
def result():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("result.html", name=session["name"])

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    app.run(debug=True, port=5000)
