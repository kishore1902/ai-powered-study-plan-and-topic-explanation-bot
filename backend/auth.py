"""Password hashing (PBKDF2) and signed session tokens, standard library only."""
import hashlib
import hmac
import os
import secrets
import time

from .models import User

# Set SECRET_KEY in Vercel (Settings > Environment Variables) so tokens can't be forged.
SECRET = (os.environ.get("SECRET_KEY") or "dev-secret-change-me").encode()
DEMO_EMAIL = "demo@gapfinder.app"
DEMO_PASSWORD = "demo1234"


def hash_pw(pw: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 120_000).hex()
    return salt, h


def verify_pw(pw: str, salt: str, h: str) -> bool:
    return hmac.compare_digest(hash_pw(pw, salt)[1], h)


def make_token(uid: int) -> str:
    exp = int(time.time()) + 14 * 86400
    msg = f"{uid}.{exp}"
    sig = hmac.new(SECRET, msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def read_token(tok: str):
    try:
        uid, exp, sig = tok.split(".")
        good = hmac.new(SECRET, f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, good) and int(exp) > time.time():
            return int(uid)
    except Exception:
        pass
    return None


def seed_demo(session_factory):
    try:
        with session_factory() as db:
            if not db.query(User).filter_by(email=DEMO_EMAIL).first():
                salt, h = hash_pw(DEMO_PASSWORD)
                db.add(User(name="Demo Student", email=DEMO_EMAIL, salt=salt, pw_hash=h))
                db.commit()
    except Exception:
        pass  # another instance seeded it first
