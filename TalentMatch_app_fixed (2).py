import io
import re
import sqlite3
import hashlib
import secrets
import hmac
from datetime import datetime

import streamlit as st
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

st.set_page_config(page_title="TalentMatch | Career Workspace", page_icon="✨", layout="wide")
DB = "talentmatch.db"

def connect():
    return sqlite3.connect(DB, check_same_thread=False)

def init_db():
    """Create tables and safely migrate older TalentMatch databases."""
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT)""")

        # Older versions may already have a users table without created_at.
        user_columns = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
        if "created_at" not in user_columns:
            c.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        c.execute("UPDATE users SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
                  (datetime.now().isoformat(timespec="seconds"),))

        c.execute("""CREATE TABLE IF NOT EXISTS history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, created_at TEXT NOT NULL,
            resume_name TEXT NOT NULL, job_title TEXT, score REAL NOT NULL,
            matched TEXT, missing TEXT, suggestions TEXT)""")

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 250_000).hex()

def signup(email, password):
    salt = secrets.token_hex(16)
    try:
        with connect() as c:
            c.execute("INSERT INTO users(email,salt,password_hash,created_at) VALUES(?,?,?,?)",
                      (email, salt, password_hash(password, salt), datetime.now().isoformat(timespec="seconds")))
        return True
    except sqlite3.IntegrityError:
        return False

def login(email, password):
    with connect() as c:
        row = c.execute("SELECT salt,password_hash FROM users WHERE email=?", (email,)).fetchone()
    return bool(row and hmac.compare_digest(password_hash(password, row[0]), row[1]))

init_db()
for key, default in {
    "authenticated": False, "email": "", "resume_text": "", "job_text": "",
    "resume_name": "Pasted resume text", "pdf_signature": None, "last_result": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
.stApp {
  background: radial-gradient(ellipse at 5% 0%, #dcd4ff99, transparent 32%),
              radial-gradient(ellipse at 95% 90%, #cbdcff88, transparent 32%),
              linear-gradient(135deg,#f7f5ff,#f8faff 55%,#eef2ff);
  color:#15214b; font-family:'DM Sans',sans-serif;
}
[data-testid="stHeader"] { background:transparent; }
.block-container { max-width:1400px; padding-top:1.5rem; }
h1,h2,h3,h4 { color:#15214b !important; }
p, li, label, [data-testid="stMarkdownContainer"] { color:#26345f; }
.brand { font:800 31px Manrope,sans-serif; letter-spacing:-1px; color:#15214b; }
.brand span { color:#7447ef; }
.brand-icon { display:inline-flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#4130c9,#a05cff); color:white; border-radius:14px; width:46px; height:46px; margin-right:10px; }
.hero { background:linear-gradient(115deg,#111d4c,#4330b2 55%,#8747e9); padding:30px; border-radius:23px; color:white; margin-bottom:24px; box-shadow:0 18px 40px #342a8424; }
.hero h1 { color:white !important; font:800 clamp(28px,3vw,38px) Manrope,sans-serif; margin:0 0 8px; }
.hero p { color:#e4e6ff !important; margin:0; font-size:16px; }
.panel,.auth-panel { background:rgba(255,255,255,.88); border:1px solid #d7def4; border-radius:21px; padding:23px; box-shadow:0 12px 34px #26346e0c; }
.auth-panel { padding:30px; }
.feature { background:#ffffffc9; border:1px solid #e5e6fb; border-radius:15px; padding:14px; margin:10px 0; color:#26345f; }

/* Clearly visible input controls and their labels */
.stTextInput input, .stTextArea textarea, .stDateInput input, .stNumberInput input,
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
  background:#ffffff !important; color:#17264b !important;
  -webkit-text-fill-color:#17264b !important;
  border:1px solid #aebcdd !important; border-radius:11px !important;
  opacity:1 !important; box-shadow:none !important;
}
.stTextInput input::placeholder, .stTextArea textarea::placeholder,
[data-baseweb="input"] input::placeholder, [data-baseweb="textarea"] textarea::placeholder {
  color:#7b87a4 !important; -webkit-text-fill-color:#7b87a4 !important; opacity:1 !important;
}
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label, .stTextInput label, .stTextArea label {
  color:#26345f !important; opacity:1 !important;
}
[data-testid="stRadio"] label, [data-testid="stRadio"] label span,
[data-testid="stRadio"] p, [data-testid="stCheckbox"] label,
[data-testid="stCheckbox"] label span {
  color:#26345f !important; opacity:1 !important;
}
[data-testid="stFileUploader"], [data-testid="stFileUploader"] section {
  background:rgba(255,255,255,.94) !important; color:#26345f !important;
  border:1px solid #cbd5ed !important; border-radius:13px !important;
}
[data-testid="stFileUploader"] *, [data-testid="stFileUploader"] small {
  color:#26345f !important; opacity:1 !important;
}
.stButton>button,.stDownloadButton>button,[data-testid="stFormSubmitButton"]>button {
  border:0 !important; border-radius:12px !important; min-height:44px;
  color:white !important; font-weight:700 !important;
  background:linear-gradient(100deg,#5638df,#8b48ed) !important;
}
.stButton>button p,.stDownloadButton>button p,[data-testid="stFormSubmitButton"]>button p { color:white !important; }
.stTextInput input:focus,.stTextArea textarea:focus {
  border-color:#8066f2 !important; box-shadow:0 0 0 2px #8066f222 !important;
}
[data-testid="stForm"] { background:transparent !important; }
[data-testid="stAlert"] { border-radius:12px !important; }
[data-testid="stAlert"] p,[data-testid="stAlert"] li,[data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
  color:#27345c !important; opacity:1 !important;
}
[data-testid="stSidebar"] { background:#ffffffeb; border-right:1px solid #e4e7f5; }
[data-testid="stSidebar"] * { color:#26345f; }
[data-testid="stSidebar"] .stButton button,[data-testid="stSidebar"] .stButton button p { color:#ffffff !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:#687697 !important; }
[data-testid="stMetric"] {
  background:rgba(255,255,255,.95) !important; border:1px solid #d7def4;
  border-radius:15px; padding:17px;
}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {
  color:#17264b !important; -webkit-text-fill-color:#17264b !important; opacity:1 !important;
}
div[data-testid="stProgressBar"]>div>div>div { background:linear-gradient(90deg,#5837df,#a15bfa); }
.muted { color:#7480a0 !important; }
</style>
""", unsafe_allow_html=True)

def brand():
    st.markdown('<div class="brand"><span class="brand-icon">✦</span>Talent<span>Match</span></div><p class="muted" style="margin-left:57px;margin-top:-4px">Your career journey, thoughtfully matched.</p>', unsafe_allow_html=True)

def auth_screen():
    left, right = st.columns([1.05,.95], gap="large")
    with left:
        brand()
        st.markdown("""
        <div style="margin-top:55px;font:800 clamp(36px,4.3vw,58px)/1.07 Manrope,sans-serif;letter-spacing:-2px;color:#14204b">
        Make your next<br><span style="color:#7045ed">move count.</span></div>
        <p style="font-size:17px;line-height:1.8;color:#637194;max-width:540px;margin-top:20px">Understand how your resume aligns with a role, discover relevant skills, and turn gaps into a practical action plan.</p>
        <div class="feature">📄 &nbsp; <b>PDF resume upload</b><br><span class="muted">Extract text and edit it before analysis.</span></div>
        <div class="feature">🎯 &nbsp; <b>Skill gap insights</b><br><span class="muted">See skills found in your resume and job description.</span></div>
        <div class="feature">📈 &nbsp; <b>Analysis history & reports</b><br><span class="muted">Keep comparisons and download reports.</span></div>
        """, unsafe_allow_html=True)
    with right:
        st.markdown('<div class="auth-panel"><h2 style="text-align:center">Welcome to <span style="color:#7045ed">TalentMatch</span></h2><p style="text-align:center;color:#7b86a5">Sign in or create your personal workspace</p>', unsafe_allow_html=True)
        mode = st.radio("Account", ["Login","Sign Up"], horizontal=True, label_visibility="collapsed")
        if mode == "Login":
            with st.form("login_form"):
                email=st.text_input("Email address",placeholder="you@example.com")
                pw=st.text_input("Password",type="password")
                submit=st.form_submit_button("Log in to TalentMatch",use_container_width=True)
            if submit:
                email=email.strip().lower()
                if login(email,pw):
                    st.session_state.authenticated=True; st.session_state.email=email; st.rerun()
                else: st.error("Login failed. Check your details or create an account.")
        else:
            with st.form("signup_form"):
                email=st.text_input("Email address",placeholder="you@example.com")
                pw=st.text_input("Create password",type="password",help="Use at least 8 characters.")
                confirm=st.text_input("Confirm password",type="password")
                submit=st.form_submit_button("Create my account",use_container_width=True)
            if submit:
                email=email.strip().lower()
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): st.error("Enter a valid email address.")
                elif len(pw)<8: st.error("Password must contain at least 8 characters.")
                elif pw!=confirm: st.error("Passwords do not match.")
                elif signup(email,pw): st.success("Account created! Choose Login to sign in.")
                else: st.error("An account with this email already exists.")
        st.markdown('</div><p class="muted" style="text-align:center;font-size:12px">Local student-project prototype</p>',unsafe_allow_html=True)

SKILLS = [
"python","java","javascript","typescript","c++","c#","sql","mysql","postgresql","mongodb",
"excel","power bi","tableau","pandas","numpy","data analysis","data visualization",
"machine learning","deep learning","artificial intelligence","scikit-learn","tensorflow",
"pytorch","nlp","statistics","aws","azure","google cloud","docker","kubernetes","git",
"github","linux","html","css","react","node.js","flask","django","fastapi","streamlit",
"rest api","communication","teamwork","leadership","problem solving","project management",
"critical thinking","agile","testing","debugging","cybersecurity","networking",
"computer networks","operating systems","dbms","oop","data structures","algorithms",
"spring boot","php","r programming","figma","ui/ux","marketing","customer service"
]

def find_skills(text):
    found=[]
    for skill in SKILLS:
        if re.search(r"(?<![a-z0-9])"+re.escape(skill)+r"(?![a-z0-9])",text.lower()):
            found.append(skill)
    return found

def suggestions_for(score, matched, missing, resume):
    tips=[]
    if score<30: tips.append("Text overlap is low. Tailor your summary and project descriptions to the target role.")
    elif score<60: tips.append("There is some overlap. Add clear, relevant examples of your experience and projects.")
    else: tips.append("Text overlap is strong. Verify that your resume clearly demonstrates the relevant experience.")
    if missing: tips.append("Review these job skills not detected in your resume: "+", ".join(missing[:12])+". Include only skills you genuinely have.")
    if matched: tips.append("Show matching skills in a concise Skills section and demonstrate them in project or experience bullets.")
    if len(resume.split())<120: tips.append("Your resume text looks brief. Consider adding project outcomes, coursework, tools, internships, and achievements.")
    if "project" not in resume.lower(): tips.append("If applicable, add a Projects section describing the problem, your work, tools, and outcome.")
    tips.append("Proofread spelling, dates, contact details, and formatting before submitting.")
    return tips[:6]

def make_report(result):
    return "\n".join([
        "TALENTMATCH — RESUME ANALYSIS REPORT","="*40,
        f"Account: {st.session_state.email}",f"Generated: {datetime.now():%Y-%m-%d %H:%M}",
        f"Resume: {result['resume_name']}",f"Job title: {result['job_title'] or 'Untitled role'}",
        f"Text similarity: {result['score']}%",
        "Note: Similarity is text overlap, not probability of getting hired.","",
        "MATCHING SKILLS",", ".join(result["matched"]) or "None detected","",
        "SKILLS TO REVIEW",", ".join(result["missing"]) or "None detected","",
        "SUGGESTIONS",*[f"{i}. {tip}" for i,tip in enumerate(result["tips"],1)],
        "","Only include skills and experience you genuinely have."
    ])

def save_history(result):
    with connect() as c:
        c.execute("""INSERT INTO history(email,created_at,resume_name,job_title,score,matched,missing,suggestions)
        VALUES(?,?,?,?,?,?,?,?)""",(st.session_state.email,result["created_at"],result["resume_name"],
        result["job_title"],result["score"],", ".join(result["matched"]),", ".join(result["missing"]),"\n".join(result["tips"])))

def dashboard():
    with st.sidebar:
        st.markdown('<div class="brand" style="font-size:23px"><span class="brand-icon" style="width:38px;height:38px">✦</span>Talent<span>Match</span></div>',unsafe_allow_html=True)
        st.caption("YOUR CAREER WORKSPACE"); st.divider()
        st.caption("SIGNED IN AS"); st.write(st.session_state.email)
        page=st.radio("Navigation",["Resume Analyzer","Analysis History","How It Works","About"],label_visibility="collapsed")
        st.divider()
        if st.button("Log out",use_container_width=True):
            st.session_state.authenticated=False; st.session_state.email=""; st.session_state.last_result=None; st.rerun()
    st.markdown('<div class="hero"><h1>Your next opportunity starts here.</h1><p>Compare your resume with a job role, uncover skill gaps, and build a practical improvement plan.</p></div>',unsafe_allow_html=True)

    if page=="Resume Analyzer":
        st.subheader("Resume Analyzer")
        st.markdown('<p class="muted">Upload a PDF or paste text, then add the target job description.</p>',unsafe_allow_html=True)
        a,b=st.columns(2,gap="large")
        with a:
            st.markdown('<div class="panel">',unsafe_allow_html=True); st.markdown("### 📄 Your resume")
            pdf=st.file_uploader("Upload resume PDF (optional)",type=["pdf"],key="pdf_upload")
            if pdf:
                sig=f"{pdf.name}:{pdf.size}"
                if st.session_state.pdf_signature!=sig:
                    try:
                        reader=PdfReader(io.BytesIO(pdf.getvalue()))
                        extracted="\n\n".join(p.extract_text() or "" for p in reader.pages).strip()
                        if extracted:
                            st.session_state.resume_text=extracted; st.session_state.resume_name=pdf.name
                            st.session_state.pdf_signature=sig
                            st.success("PDF text extracted. Review it below.")
                        else:
                            st.session_state.pdf_signature=sig
                            st.warning("No selectable text found. This may be a scanned PDF; paste the text manually or use OCR.")
                    except Exception as e: st.error(f"Could not read this PDF: {e}")
            resume=st.text_area("Resume text (editable)",height=280,key="resume_text",placeholder="Upload a PDF or paste your resume here...")
            st.markdown('</div>',unsafe_allow_html=True)
        with b:
            st.markdown('<div class="panel">',unsafe_allow_html=True); st.markdown("### 💼 Target role")
            title=st.text_input("Job title (optional)",placeholder="e.g. Junior Data Analyst",key="job_title")
            job=st.text_area("Job description",height=280,key="job_text",placeholder="Paste job responsibilities and required skills...")
            st.markdown('</div>',unsafe_allow_html=True)
        if st.button("✨ Analyze my match",use_container_width=True):
            if not resume.strip() or not job.strip(): st.warning("Please add both resume text and a job description.")
            elif len(resume.split())<5 or len(job.split())<5: st.warning("Please enter more meaningful text in both fields.")
            else:
                try:
                    vec=TfidfVectorizer(stop_words="english",ngram_range=(1,2))
                    matrix=vec.fit_transform([resume,job])
                    score=round(float(cosine_similarity(matrix[0:1],matrix[1:2])[0][0])*100,1)
                    rs,js=find_skills(resume),find_skills(job)
                    matched=[x for x in js if x in rs]; missing=[x for x in js if x not in rs]
                    result={"created_at":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "resume_name":st.session_state.resume_name,"job_title":title.strip(),"score":score,
                    "matched":matched,"missing":missing,"tips":suggestions_for(score,matched,missing,resume)}
                    st.session_state.last_result=result; save_history(result)
                except ValueError: st.error("Text could not be analyzed. Please add more meaningful text.")
        result=st.session_state.last_result
        if result:
            st.divider(); st.subheader("Your results")
            x,y,z=st.columns(3); x.metric("Text similarity",f"{result['score']}%"); y.metric("Matching skills",len(result["matched"])); z.metric("Skills to review",len(result["missing"]))
            st.progress(int(max(0,min(100,result["score"]))))
            st.caption("Similarity measures text overlap. It is not a probability of getting hired.")
            l,r=st.columns(2)
            with l:
                st.markdown("### ✅ Matching skills")
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if result["matched"]:
                    for skill in result["matched"]:
                        st.markdown(
                            f'<div style="background:#e8f8ef;color:#17633b;border:1px solid #bfe9d0;'
                            f'padding:12px 15px;border-radius:11px;margin:8px 0;font-weight:600">'
                            f'✓ &nbsp; {skill.title()}</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("No built-in checklist skills matched.")
                st.markdown('</div>', unsafe_allow_html=True)
            with r:
                st.markdown("### 🎯 Skills to review")
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if result["missing"]:
                    for skill in result["missing"]:
                        st.markdown(
                            f'<div style="background:#fff5d9;color:#704b08;border:1px solid #f1d58b;'
                            f'padding:12px 15px;border-radius:11px;margin:8px 0;font-weight:600">'
                            f'• &nbsp; {skill.title()}</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.success("No checklist skill gaps detected.")
                st.markdown('</div>', unsafe_allow_html=True)
            st.markdown("### 💡 Your improvement plan")
            for i,tip in enumerate(result["tips"],1): st.markdown(f"**{i}.** {tip}")
            st.download_button("⬇️ Download analysis report",make_report(result),file_name="talentmatch_report.txt",mime="text/plain",use_container_width=True)
            st.info("The skill list is a basic checklist and may miss specialized terms. Only add skills you genuinely have.")

    elif page=="Analysis History":
        st.subheader("📚 Your analysis history")
        with connect() as c:
            rows=c.execute("SELECT id,created_at,resume_name,job_title,score,matched,missing,suggestions FROM history WHERE email=? ORDER BY id DESC",(st.session_state.email,)).fetchall()
        if not rows: st.info("No analyses saved yet. Run your first analysis to see it here.")
        else:
            st.caption(f"{len(rows)} saved analysis record(s)")
            for row in rows:
                rid,created,resume_name,title,score,matched,missing,tips=row
                with st.expander(f"{title or 'Untitled role'} · {score:.1f}% · {created}"):
                    st.write("**Resume:**",resume_name); st.write("**Matching skills:**",matched or "None detected"); st.write("**Skills to review:**",missing or "None detected")
                    st.markdown("**Suggestions**")
                    for tip in (tips or "").splitlines():
                        if tip: st.markdown("- "+tip)
                    data=f"TALENTMATCH REPORT\nDate: {created}\nResume: {resume_name}\nJob: {title}\nSimilarity: {score}%\nMatched skills: {matched}\nMissing skills: {missing}\n\nSuggestions:\n{tips}"
                    st.download_button("Download this report",data,file_name=f"talentmatch_report_{rid}.txt",mime="text/plain",key=f"dl_{rid}")

    elif page=="How It Works":
        st.subheader("How TalentMatch works")
        for num,title,desc in [
            ("01","Upload or paste","Upload a text-based PDF or paste resume content; review extracted text."),
            ("02","Add a target role","Paste the job description and optionally enter the job title."),
            ("03","Compare text","TF-IDF and cosine similarity estimate text overlap."),
            ("04","Review skills","The built-in skill checklist compares terms in the resume and job description."),
            ("05","Improve and save","Use the rule-based tips, download a report, and revisit saved history.")]:
            st.markdown(f'<div class="feature"><span style="color:#7950ef;font-weight:800">{num}</span> &nbsp; <b>{title}</b><br><span class="muted">{desc}</span></div>',unsafe_allow_html=True)
        st.write("**Built with:** Python, Streamlit, SQLite, scikit-learn and pypdf.")
        st.warning("Suggestions are rule-based, not generative AI. A real AI API can be integrated later with a provider key.")

    else:
        st.subheader("About TalentMatch")
        st.markdown("""
        TalentMatch is a student portfolio project that helps compare a resume with a job description.

        **Features**
        - Login and signup with salted password hashing
        - PDF upload and text extraction
        - Resume/job text similarity
        - Skills matching and skill-gap checklist
        - Rule-based improvement suggestions
        - Per-account analysis history stored in SQLite
        - Downloadable analysis reports

        **Technology:** Python, Streamlit, SQLite, scikit-learn, pypdf.
        """)
        st.info("This is a local educational prototype, not a hiring decision system. Similarity scores do not predict hiring outcomes.")

if st.session_state.authenticated:
    dashboard()
else:
    auth_screen()
