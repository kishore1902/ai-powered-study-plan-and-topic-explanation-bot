import os
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import auth, db as database, llm, services
from . import models as M

MAX_UPLOAD = 4_300_000  # Vercel request bodies are limited to 4.5 MB

app = FastAPI(title="GapFinder AI")
api = APIRouter(prefix="/api")


# ---------------------------------------------------------------- dependencies
def current_user(authorization: str = Header(default=""), db: Session = Depends(database.get_db)) -> M.User:
    tok = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    uid = auth.read_token(tok)
    user = db.get(M.User, uid) if uid else None
    if not user:
        raise HTTPException(401, "Please log in again.")
    return user


def llm_ctx(x_groq_key: str = Header(default=""), x_groq_model: str = Header(default="")) -> llm.Ctx:
    return llm.Ctx(x_groq_key.strip(), x_groq_model.strip() or llm.DEFAULT_MODEL)


@app.exception_handler(services.UserError)
async def _user_error(_, e):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(llm.LLMError)
async def _llm_error(_, e):
    return JSONResponse({"detail": str(e)}, status_code=400 if e.missing_key else 502)


# ---------------------------------------------------------------- schemas
class SignupIn(BaseModel):
    name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class TextIn(BaseModel):
    name: str = "Pasted text"
    type: str
    text: str


class QuizIn(BaseModel):
    topic_ids: List[str]
    per: int = 2


class SubmitIn(BaseModel):
    answers: list


class PlanIn(BaseModel):
    days: int
    hours: float


class ExplainIn(BaseModel):
    question: str
    history: Optional[list] = None


# ---------------------------------------------------------------- auth
def _session(user):
    return {"token": auth.make_token(user.id), "user": {"name": user.name, "email": user.email}}


@api.post("/auth/signup")
def signup(body: SignupIn, db: Session = Depends(database.get_db)):
    email, name = body.email.strip().lower(), body.name.strip()
    if not name:
        raise services.UserError("Enter your name.")
    if not re.match(r"^\S+@\S+\.\S+$", email):
        raise services.UserError("Enter a valid email.")
    if len(body.password) < 6:
        raise services.UserError("Password must be at least 6 characters.")
    if db.query(M.User).filter_by(email=email).first():
        raise services.UserError("An account with this email already exists.")
    salt, h = auth.hash_pw(body.password)
    user = M.User(name=name[:120], email=email, salt=salt, pw_hash=h)
    db.add(user)
    db.commit()
    return _session(user)


@api.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(database.get_db)):
    user = db.query(M.User).filter_by(email=body.email.strip().lower()).first()
    if not user or not auth.verify_pw(body.password, user.salt, user.pw_hash):
        raise services.UserError("Wrong email or password.")
    return _session(user)


@api.get("/me")
def me(user: M.User = Depends(current_user)):
    return {"name": user.name, "email": user.email, "temporary_storage": database.IS_TEMPORARY}


@api.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- materials
@api.get("/docs")
def docs(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    return {"docs": services.list_docs(db, user.id)}


@api.post("/docs")
async def upload(type: str = Form(...), files: List[UploadFile] = File(...),
                 user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    for f in files:
        data = await f.read()
        if len(data) > MAX_UPLOAD:
            raise services.UserError(f'"{f.filename}" is larger than 4 MB. Split it or paste the text instead.')
        name = f.filename or "upload"
        if name.lower().endswith(".pdf") or f.content_type == "application/pdf":
            pages = services.pdf_pages(data)
        else:
            from .rag import text_to_pages
            pages = text_to_pages(data.decode("utf-8", errors="ignore"))
        services.add_doc(db, user.id, name, type, pages)
    return {"docs": services.list_docs(db, user.id)}


@api.post("/docs/text")
def upload_text(body: TextIn, user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    from .rag import text_to_pages
    services.add_doc(db, user.id, body.name.strip() or "Pasted text", body.type, text_to_pages(body.text))
    return {"docs": services.list_docs(db, user.id)}


@api.post("/docs/sample")
def sample(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    services.add_sample(db, user.id)
    return {"docs": services.list_docs(db, user.id)}


@api.delete("/docs/{doc_id}")
def delete_doc(doc_id: int, user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    services.delete_doc(db, user.id, doc_id)
    return {"docs": services.list_docs(db, user.id)}


# ---------------------------------------------------------------- topics
@api.get("/topics")
def topics(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    return services.topic_overview(db, user.id)


@api.post("/topics/build")
def build_topics(user: M.User = Depends(current_user), db: Session = Depends(database.get_db), ctx: llm.Ctx = Depends(llm_ctx)):
    services.build_topic_map(db, user.id, ctx)
    return services.topic_overview(db, user.id)


# ---------------------------------------------------------------- quiz
@api.get("/quiz")
def get_quiz(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    ov = services.topic_overview(db, user.id)
    return {"quiz": services.public_quiz(services.get_state(db, user.id).quiz),
            "last_result": services.last_result(db, user.id),
            "topics": [{"id": t["id"], "name": t["name"], "level": t["level"]} for t in ov["topics"]]}


@api.post("/quiz/generate")
def generate(body: QuizIn, user: M.User = Depends(current_user), db: Session = Depends(database.get_db), ctx: llm.Ctx = Depends(llm_ctx)):
    skipped = services.generate_quiz(db, user.id, ctx, body.topic_ids, body.per)
    return {"quiz": services.public_quiz(services.get_state(db, user.id).quiz), "skipped": skipped}


@api.post("/quiz/submit")
def submit(body: SubmitIn, user: M.User = Depends(current_user), db: Session = Depends(database.get_db), ctx: llm.Ctx = Depends(llm_ctx)):
    attempt, warnings = services.submit_quiz(db, user.id, ctx, body.answers)
    return {"attempt": attempt, "warnings": warnings}


@api.delete("/quiz")
def discard(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    services.get_state(db, user.id).quiz = None
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- reports
@api.get("/gaps")
def gaps(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    return services.gap_report(db, user.id)


@api.get("/progress")
def progress(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    return services.progress(db, user.id)


@api.get("/plan")
def get_plan(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    return services.plan_report(db, user.id)


@api.put("/plan")
def put_plan(body: PlanIn, user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    services.set_plan(db, user.id, body.days, body.hours)
    return services.plan_report(db, user.id)


@api.post("/plan/tips")
def tips(user: M.User = Depends(current_user), db: Session = Depends(database.get_db), ctx: llm.Ctx = Depends(llm_ctx)):
    services.plan_tips(db, user.id, ctx)
    return services.plan_report(db, user.id)


@api.post("/explain")
def explain(body: ExplainIn, user: M.User = Depends(current_user), db: Session = Depends(database.get_db), ctx: llm.Ctx = Depends(llm_ctx)):
    return services.explain(db, user.id, ctx, body.question, body.history)


# ---------------------------------------------------------------- settings
@api.post("/groq/test")
def groq_test(user: M.User = Depends(current_user), ctx: llm.Ctx = Depends(llm_ctx)):
    return {"reply": llm.chat(ctx, [{"role": "user", "content": "Reply with the single word OK."}], max_tokens=10).strip()}


@api.delete("/data")
def wipe(user: M.User = Depends(current_user), db: Session = Depends(database.get_db)):
    services.reset_all(db, user.id)
    return {"ok": True}


app.include_router(api)

# Local development: serve the website from the same server. On Vercel, public/ is served by the CDN.
_public = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
if os.path.isdir(_public):
    app.mount("/", StaticFiles(directory=_public, html=True), name="public")
