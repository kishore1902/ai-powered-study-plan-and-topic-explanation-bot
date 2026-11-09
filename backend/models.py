import datetime as dt

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    salt = Column(String(64), nullable=False)
    pw_hash = Column(String(128), nullable=False)
    created = Column(DateTime, default=dt.datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(300), nullable=False)
    type = Column(String(20), nullable=False)  # syllabus | notes | past
    created = Column(DateTime, default=dt.datetime.utcnow)
    chunks = relationship("Chunk", cascade="all, delete-orphan", back_populates="doc")


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), index=True, nullable=False)
    label = Column(String(400), nullable=False)
    text = Column(Text, nullable=False)
    doc = relationship("Document", back_populates="chunks")


class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    key = Column(String(64), nullable=False)  # stable slug, survives rebuilds
    name = Column(String(200), nullable=False)
    subtopics = Column(JSON, default=list)
    pos = Column(Integer, default=0)


class Attempt(Base):
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    ts = Column(BigInteger, nullable=False)  # epoch ms
    pct = Column(Float, nullable=False)
    results = Column(JSON, nullable=False)


class UserState(Base):
    __tablename__ = "user_state"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    quiz = Column(JSON, nullable=True)
    reasons = Column(JSON, nullable=True)
    plan = Column(JSON, nullable=True)
    last_result = Column(Integer, nullable=True)
