import hashlib
import io
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
from docx import Document
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://recruit:recruit@localhost:5432/recruitment"
    jwt_secret: str = "change-this-secret-before-deploying"
    access_token_minutes: int = 720
    upload_dir: str = "uploads"
    cors_origins: str = "http://localhost:5173"

settings = Settings()
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(24), default="recruiter")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    recruiter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    department: Mapped[str] = mapped_column(String(120), default="People")
    location: Mapped[str] = mapped_column(String(160), default="Remote")
    employment_type: Mapped[str] = mapped_column(String(32), default="Full-time")
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[list] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    min_experience: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_name: Mapped[str] = mapped_column(String(160))
    candidate_email: Mapped[str] = mapped_column(String(255), index=True)
    resume_name: Mapped[str] = mapped_column(String(255))
    resume_path: Mapped[str] = mapped_column(String(500))
    resume_hash: Mapped[str] = mapped_column(String(64), index=True)
    resume_text: Mapped[str] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="New Applications", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    job: Mapped[Job] = relationship()

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
app = FastAPI(title="Hirewise API", version="1.0.0", description="Recruitment workflow and explainable resume matching API")
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in settings.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)
class LoginIn(BaseModel):
    email: EmailStr
    password: str
class JobIn(BaseModel):
    title: str
    department: str = "People"
    location: str = "Remote"
    employment_type: str = "Full-time"
    description: str
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    min_experience: int = 0
    status: str = "active"
class StatusIn(BaseModel):
    status: str

def token_for(user):
    return jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)}, settings.jwt_secret, algorithm="HS256")
def current_user(token: str = Depends(oauth), db: Session = Depends(db_session)):
    error = HTTPException(status_code=401, detail="Session expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})
    try: uid = int(jwt.decode(token, settings.jwt_secret, algorithms=["HS256"]).get("sub"))
    except (JWTError, TypeError, ValueError): raise error
    user = db.get(User, uid)
    if not user: raise error
    return user
def user_out(u): return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}
def job_out(j, count=0): return {"id": j.id, "title": j.title, "department": j.department, "location": j.location, "employment_type": j.employment_type, "description": j.description, "required_skills": j.required_skills or [], "preferred_skills": j.preferred_skills or [], "min_experience": j.min_experience, "status": j.status, "created_at": j.created_at, "applicant_count": count}
def app_out(a): return {"id": a.id, "job_id": a.job_id, "job_title": a.job.title, "candidate_name": a.candidate_name, "candidate_email": a.candidate_email, "resume_name": a.resume_name, "skills": a.skills or [], "experience_years": a.experience_years, "score": a.score, "score_breakdown": a.score_breakdown or {}, "status": a.status, "created_at": a.created_at}

SKILL_VOCAB = ["Python", "Java", "JavaScript", "TypeScript", "React", "FastAPI", "Django", "SQL", "PostgreSQL", "MySQL", "MongoDB", "AWS", "Azure", "Docker", "Kubernetes", "Pandas", "NumPy", "Scikit-learn", "Machine Learning", "NLP", "TensorFlow", "PyTorch", "Power BI", "Tableau", "Excel", "Git", "Node.js", "HTML", "CSS", "REST API", "Linux", "Figma"]
ALIASES = {"js": "JavaScript", "postgres": "PostgreSQL", "ml": "Machine Learning", "natural language processing": "NLP", "amazon web services": "AWS", "powerbi": "Power BI"}
def extract_text(name, content):
    ext = Path(name).suffix.lower()
    if ext == ".pdf": return "\n".join(p.get_text() for p in fitz.open(stream=content, filetype="pdf"))
    if ext == ".docx": return "\n".join(p.text for p in Document(io.BytesIO(content)).paragraphs)
    if ext == ".txt": return content.decode("utf-8", errors="replace")
    if ext == ".doc": raise ValueError("Legacy .doc files are not supported. Save as DOCX or PDF and retry.")
    raise ValueError("Unsupported file type. Upload a PDF, DOCX, or TXT resume.")
def parse_resume(text):
    lower = text.lower()
    skills = [s for s in SKILL_VOCAB if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", lower)]
    for alias, canonical in ALIASES.items():
        if alias in lower and canonical not in skills: skills.append(canonical)
    years = [int(x) for x in re.findall(r"(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|exp)", lower)]
    return skills, max(years, default=0)
def screen(job, text, skills, years):
    required = [s for s in job.required_skills or [] if s]
    preferred = [s for s in job.preferred_skills or [] if s]
    matched = [s for s in required if any(s.lower() == x.lower() for x in skills)]
    preferred_matched = [s for s in preferred if any(s.lower() == x.lower() for x in skills)]
    skill_score = len(matched) / max(len(required), 1) * 100 if required else 75
    exp_score = min(years / max(job.min_experience, 1), 1) * 100 if job.min_experience else 75
    job_text = " ".join([job.title, job.description, *required, *preferred])
    try: semantic = float(cosine_similarity(TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([job_text, text]))[0, 1]) * 100
    except ValueError: semantic = 0
    preferred_score = len(preferred_matched) / max(len(preferred), 1) * 100 if preferred else 50
    score = round(skill_score * .35 + exp_score * .25 + semantic * .30 + preferred_score * .10)
    missing = [s for s in required if s not in matched]
    return score, {"required_skills": {"score": round(skill_score), "weight": 35, "matched": matched, "missing": missing}, "experience": {"score": round(exp_score), "weight": 25, "candidate_years": years, "required_years": job.min_experience}, "context_relevance": {"score": round(semantic), "weight": 30}, "preferred_skills": {"score": round(preferred_score), "weight": 10, "matched": preferred_matched}, "explanation": f"Matched {len(matched)} of {len(required)} required skills and {years} years of stated experience. Context relevance uses TF-IDF similarity. Review the resume and qualifications before deciding."}

@app.get("/api/health")
def health(db: Session = Depends(db_session)):
    db.execute(func.now())
    return {"status": "ok", "database": "connected"}
@app.post("/api/auth/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(db_session)):
    email = data.email.lower()
    if db.query(User).filter(func.lower(User.email) == email).first(): raise HTTPException(409, "An account with this email already exists.")
    u = User(name=data.name.strip(), email=email, password_hash=pwd.hash(data.password), role="recruiter")
    db.add(u); db.commit(); db.refresh(u)
    return {"access_token": token_for(u), "token_type": "bearer", "user": user_out(u)}
@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(db_session)):
    u = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if not u or not pwd.verify(data.password, u.password_hash): raise HTTPException(401, "Email or password is incorrect.")
    return {"access_token": token_for(u), "token_type": "bearer", "user": user_out(u)}
@app.get("/api/auth/me")
def me(user: User = Depends(current_user)): return user_out(user)

@app.get("/api/jobs")
def jobs(db: Session = Depends(db_session), user: User = Depends(current_user)):
    rows = db.query(Job).filter(Job.recruiter_id == user.id).order_by(Job.created_at.desc()).all()
    return [job_out(j, db.query(Application).filter(Application.job_id == j.id).count()) for j in rows]
@app.post("/api/jobs", status_code=201)
def create_job(data: JobIn, db: Session = Depends(db_session), user: User = Depends(current_user)):
    values = data.model_dump(); values["required_skills"] = [s.strip() for s in data.required_skills if s.strip()]; values["preferred_skills"] = [s.strip() for s in data.preferred_skills if s.strip()]
    j = Job(**values, recruiter_id=user.id); db.add(j); db.commit(); db.refresh(j)
    return job_out(j)
@app.put("/api/jobs/{job_id}")
def update_job(job_id: int, data: JobIn, db: Session = Depends(db_session), user: User = Depends(current_user)):
    j = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == user.id).first()
    if not j: raise HTTPException(404, "Job not found.")
    for k, v in data.model_dump().items(): setattr(j, k, v)
    db.commit(); db.refresh(j); return job_out(j)
@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(db_session), user: User = Depends(current_user)):
    j = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == user.id).first()
    if not j: raise HTTPException(404, "Job not found.")
    db.delete(j); db.commit()

@app.get("/api/applications")
def applications(job_id: int | None = None, status: str | None = None, search: str | None = None, db: Session = Depends(db_session), user: User = Depends(current_user)):
    q = db.query(Application).join(Job).filter(Job.recruiter_id == user.id)
    if job_id: q = q.filter(Application.job_id == job_id)
    if status: q = q.filter(Application.status == status)
    if search: q = q.filter(func.lower(Application.candidate_name + " " + Application.candidate_email).contains(search.lower()))
    return [app_out(a) for a in q.order_by(Application.score.desc(), Application.created_at.desc()).all()]
@app.post("/api/jobs/{job_id}/applications", status_code=201)
async def apply(job_id: int, name: str = Form(...), email: EmailStr = Form(...), resume: UploadFile = File(...), db: Session = Depends(db_session), user: User = Depends(current_user)):
    job = db.query(Job).filter(Job.id == job_id, Job.recruiter_id == user.id, Job.status == "active").first()
    if not job: raise HTTPException(404, "Active job not found.")
    content = await resume.read()
    if not content or len(content) > 12 * 1024 * 1024: raise HTTPException(400, "Resume is empty or exceeds the 12 MB limit.")
    digest = hashlib.sha256(content).hexdigest()
    if db.query(Application).filter(Application.job_id == job_id, Application.resume_hash == digest).first(): raise HTTPException(409, "This resume has already been submitted for the job.")
    try: text = extract_text(resume.filename or "resume", content)
    except Exception as e: raise HTTPException(400, str(e))
    if not text.strip(): raise HTTPException(400, "No text could be extracted from this file. Check that it is not scanned or image-only.")
    skills, years = parse_resume(text); score, breakdown = screen(job, text, skills, years)
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(resume.filename or "resume").name)
    stored = f"{digest[:12]}_{safe_name}"
    Path(settings.upload_dir, stored).write_bytes(content)
    a = Application(job_id=job.id, candidate_name=name.strip(), candidate_email=str(email).lower(), resume_name=safe_name, resume_path=stored, resume_hash=digest, resume_text=text, skills=skills, experience_years=years, score=score, score_breakdown=breakdown)
    db.add(a); db.flush(); db.add(AuditLog(user_id=user.id, action="application_added", entity="application", entity_id=a.id, detail=f"Submitted for {job.title}")); db.commit(); db.refresh(a)
    return app_out(a)
@app.patch("/api/applications/{application_id}/status")
def change_status(application_id: int, data: StatusIn, db: Session = Depends(db_session), user: User = Depends(current_user)):
    allowed = {"New Applications", "Resume Screening", "Shortlisted", "Assessment/Test", "Interview Scheduled", "Interview Completed", "Selected", "Rejected"}
    if data.status not in allowed: raise HTTPException(422, "Unknown recruitment stage.")
    a = db.query(Application).join(Job).filter(Application.id == application_id, Job.recruiter_id == user.id).first()
    if not a: raise HTTPException(404, "Application not found.")
    old = a.status; a.status = data.status
    db.add(AuditLog(user_id=user.id, action="stage_changed", entity="application", entity_id=a.id, detail=f"{old} → {data.status}")); db.commit(); db.refresh(a)
    return app_out(a)
@app.get("/api/applications/{application_id}/resume")
def download_resume(application_id: int, db: Session = Depends(db_session), user: User = Depends(current_user)):
    a = db.query(Application).join(Job).filter(Application.id == application_id, Job.recruiter_id == user.id).first()
    if not a: raise HTTPException(404, "Application not found.")
    path = Path(settings.upload_dir, a.resume_path).resolve()
    if not path.is_relative_to(Path(settings.upload_dir).resolve()) or not path.exists(): raise HTTPException(404, "Resume file is unavailable.")
    return FileResponse(path, filename=a.resume_name)
@app.get("/api/applications/{application_id}/summary")
def summary(application_id: int, db: Session = Depends(db_session), user: User = Depends(current_user)):
    a = db.query(Application).join(Job).filter(Application.id == application_id, Job.recruiter_id == user.id).first()
    if not a: raise HTTPException(404, "Application not found.")
    chunks = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"(?<=[.!?])\s+", a.resume_text) if len(p.strip()) > 45]
    return {"summary": " ".join(chunks[:4])[:900], "skills": a.skills, "experience_years": a.experience_years, "score": a.score, "score_breakdown": a.score_breakdown, "note": "Summary is extracted from resume text; verify details with the candidate."}

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(db_session), user: User = Depends(current_user)):
    jobs = db.query(Job).filter(Job.recruiter_id == user.id).all(); ids = [j.id for j in jobs]
    apps = db.query(Application).filter(Application.job_id.in_(ids)).order_by(Application.created_at).all() if ids else []
    stages = ["New Applications", "Resume Screening", "Shortlisted", "Assessment/Test", "Interview Scheduled", "Interview Completed", "Selected", "Rejected"]
    counts = {stage: sum(a.status == stage for a in apps) for stage in stages}
    skills = {}
    for a in apps:
        for s in a.skills or []: skills[s] = skills.get(s, 0) + 1
    days = {}
    for a in apps:
        key = a.created_at.date().isoformat(); days[key] = days.get(key, 0) + 1
    return {"metrics": {"open_jobs": sum(j.status == "active" for j in jobs), "applications": len(apps), "shortlisted": counts["Shortlisted"], "interviews": counts["Interview Scheduled"], "selected": counts["Selected"], "awaiting_review": counts["New Applications"], "avg_score": round(sum(a.score for a in apps) / len(apps)) if apps else 0, "conversion": round(counts["Selected"] / len(apps) * 100) if apps else 0}, "stages": counts, "skills": sorted([{"name": k, "count": v} for k, v in skills.items()], key=lambda x: -x["count"])[:8], "applications_over_time": [{"date": k, "count": v} for k, v in sorted(days.items())[-14:]], "jobs": [job_out(j, sum(a.job_id == j.id for a in apps)) for j in jobs]}
