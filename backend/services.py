"""Application logic. Each function says whether it uses RETRIEVAL (rag.py), plain CODE (logic.py)
or GENERATION (llm.py), so the three stay separate."""
import io
import json
import random
import re
import time

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import llm, logic, rag, samples
from . import models as M


class UserError(Exception):
    """A problem the user can fix; returned as HTTP 400."""


TYPES = {"syllabus", "notes", "past"}
MAX_CHARS = 600_000


# ------------------------------------------------------------------ data access
def get_state(db: Session, uid: int) -> M.UserState:
    st = db.get(M.UserState, uid)
    if not st:
        st = M.UserState(user_id=uid, quiz=None, reasons={}, plan={"days": 14, "hours": 2, "tips": None}, last_result=None)
        db.add(st)
        db.flush()
    return st


def topics_of(db, uid):
    return db.query(M.Topic).filter_by(user_id=uid).order_by(M.Topic.pos).all()


def chunks_of(db, uid, type_):
    rows = (db.query(M.Chunk).join(M.Document, M.Chunk.doc_id == M.Document.id)
            .filter(M.Document.user_id == uid, M.Document.type == type_).order_by(M.Chunk.id).all())
    return [{"id": f"C{c.id}", "label": c.label, "text": c.text} for c in rows]


def attempts_of(db, uid):
    return db.query(M.Attempt).filter_by(user_id=uid).order_by(M.Attempt.id).all()


def tq(t) -> str:
    return t.name + " " + " ".join(t.subtopics or [])


def attempt_dict(a) -> dict:
    return {"id": a.id, "ts": a.ts, "pct": a.pct, "results": a.results}


# ------------------------------------------------------------------ materials
def pdf_pages(data: bytes) -> list:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise UserError("This PDF is password protected.")
        return [{"label": f"p.{i + 1}", "text": p.extract_text() or ""} for i, p in enumerate(reader.pages)]
    except UserError:
        raise
    except Exception:
        raise UserError("Could not read this PDF.")


def add_doc(db: Session, uid: int, name: str, type_: str, pages: list):
    if type_ not in TYPES:
        raise UserError("Unknown material type.")
    if type_ == "past":
        pages = rag.split_past(pages)
    chunks = rag.chunk_pages(name, pages)
    if not chunks:
        raise UserError(f'No readable text found in "{name}" (scanned PDFs need OCR first).')
    total = sum(len(c.text) for c in db.query(M.Chunk).join(M.Document).filter(M.Document.user_id == uid).all())
    if total + sum(len(c["text"]) for c in chunks) > MAX_CHARS:
        raise UserError("You have reached the storage limit for study material. Remove a document first.")
    doc = M.Document(user_id=uid, name=name[:300], type=type_)
    doc.chunks = [M.Chunk(label=c["label"][:400], text=c["text"]) for c in chunks]
    db.add(doc)
    db.commit()
    return doc


def add_sample(db, uid):
    add_doc(db, uid, "Sample syllabus", "syllabus", samples.SYLLABUS)
    add_doc(db, uid, "Sample notes", "notes", samples.NOTES)
    add_doc(db, uid, "Sample past paper 2025", "past", samples.PAST)


def list_docs(db, uid):
    out = []
    for d in db.query(M.Document).filter_by(user_id=uid).order_by(M.Document.id).all():
        out.append({"id": d.id, "name": d.name, "type": d.type, "chunks": len(d.chunks)})
    return out


def delete_doc(db, uid, doc_id):
    d = db.get(M.Document, doc_id)
    if not d or d.user_id != uid:
        raise UserError("Document not found.")
    db.delete(d)
    db.commit()


def reset_all(db, uid):
    for d in db.query(M.Document).filter_by(user_id=uid).all():
        db.delete(d)
    db.query(M.Topic).filter_by(user_id=uid).delete()
    db.query(M.Attempt).filter_by(user_id=uid).delete()
    st = get_state(db, uid)
    st.quiz, st.reasons, st.last_result = None, {}, None
    st.plan = {"days": 14, "hours": 2, "tips": None}
    db.commit()


# ------------------------------------------------------------------ topic map
def build_topic_map(db, uid, ctx):
    """GENERATION reads the syllabus text and lists topics."""
    syl = chunks_of(db, uid, "syllabus")
    if not syl:
        raise UserError("Upload a syllabus first.")
    text = "\n".join(c["text"] for c in syl)[:9000]
    out = llm.chat_json(ctx, [
        {"role": "system", "content": 'You extract the topic structure from a syllabus. Use ONLY the text provided; do not add topics that are not in it. Return JSON: {"topics":[{"name":"short topic name","subtopics":["..."]}]} with 4 to 15 topics.'},
        {"role": "user", "content": text}], max_tokens=1800)
    used, topics = set(), []
    for t in out.get("topics") or []:
        name = str(t.get("name", "")).strip()
        if not name:
            continue
        key = "t_" + (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30] or str(len(topics)))
        while key in used:
            key += "_"
        used.add(key)
        topics.append(M.Topic(user_id=uid, key=key, name=name[:200], subtopics=[str(s) for s in (t.get("subtopics") or [])][:8], pos=len(topics)))
    if not topics:
        raise UserError("Could not find topics in the syllabus.")
    db.query(M.Topic).filter_by(user_id=uid).delete()
    db.add_all(topics)
    db.commit()


def past_hits(db, uid, topics) -> dict:
    """RETRIEVAL maps each past-paper question to its closest topic."""
    hits = {t.key: 0 for t in topics}
    past = chunks_of(db, uid, "past")
    if not past or not topics:
        return hits
    idx, best = rag.Index(past), {}
    for t in topics:
        for c, s in idx.search(tq(t), len(past)):
            if c["id"] not in best or s > best[c["id"]][0]:
                best[c["id"]] = (s, t.key)
    for _, key in best.values():
        hits[key] += 1
    return hits


def topic_overview(db, uid):
    topics = topics_of(db, uid)
    notes = chunks_of(db, uid, "notes")
    idx = rag.Index(notes) if notes else None
    hits = past_hits(db, uid, topics)
    m = logic.mastery_map([a.results for a in attempts_of(db, uid)])
    return {
        "topics": [{"id": t.key, "name": t.name, "sub": t.subtopics or [], "level": logic.level(m.get(t.key)),
                    "past_hits": hits[t.key], "covered": bool(idx and idx.search(tq(t), 1))} for t in topics],
        "has_syllabus": bool(chunks_of(db, uid, "syllabus")),
        "has_notes": bool(notes),
    }


# ------------------------------------------------------------------ quiz
def generate_quiz(db, uid, ctx, ids, per):
    """RETRIEVAL picks passages per topic; GENERATION writes questions from only those passages."""
    notes = chunks_of(db, uid, "notes")
    if not notes:
        raise UserError("Add notes or textbook chapters first. Questions are generated only from your material.")
    per = max(1, min(3, int(per or 2)))
    topics = {t.key: t for t in topics_of(db, uid)}
    idx, allowed, parts, skipped = rag.Index(notes), {}, [], []
    for key in ids[:8]:
        t = topics.get(key)
        if not t:
            continue
        hits = idx.search(tq(t), 3)
        if not hits:
            skipped.append(t.name)
            continue
        for c, _ in hits:
            allowed[c["id"]] = c
        parts.append(f"### TOPIC {t.key} — {t.name}\n" + "\n\n".join(f"[{c['id']}] ({c['label']}) {c['text']}" for c, _ in hits))
    if not parts:
        raise UserError("None of the selected topics matched your notes.")
    prev = [r["question"] for a in attempts_of(db, uid)[-2:] for r in a.results][-10:]
    system = (
        "You write exam questions for a student. Use ONLY the SOURCE passages given; never use outside knowledge. "
        "Every question must be answerable from one passage and cite it by its [Cx] id. "
        'Return JSON: {"questions":[{"topicId":"...","type":"mcq" or "short","question":"...","options":["...","...","...","..."],'
        '"answerIndex":0,"modelAnswer":"...","chunkId":"Cx","quote":"exact words copied from the passage, under 200 characters",'
        '"explanation":"one sentence on why the answer is correct"}]}. '
        f'Write {per} question(s) per topic; roughly one in four should be type "short" (no options, give modelAnswer). '
        "MCQ distractors must be plausible. Do not repeat earlier questions.")
    user = "\n\n".join(parts) + (("\n\nEARLIER QUESTIONS (do not repeat):\n- " + "\n- ".join(prev)) if prev else "")
    out = llm.chat_json(ctx, [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.5, max_tokens=4000)

    by_name = {t.name: t for t in topics.values()}
    qs = []
    for q in out.get("questions") or []:
        c = allowed.get(str(q.get("chunkId")))          # citation must be a passage we actually retrieved
        t = topics.get(str(q.get("topicId"))) or by_name.get(str(q.get("topicId")))
        if not c or not t or not q.get("question"):
            continue
        quote = str(q.get("quote") or "")
        o = {
            "id": f"q{len(qs)}", "topic_id": t.key, "topic_name": t.name,
            "type": "short" if q.get("type") == "short" else "mcq",
            "question": str(q["question"]), "chunk_id": c["id"], "label": c["label"],
            "explanation": str(q.get("explanation") or ""), "snippet": c["text"][:240],
            # a quote is only kept if it really appears in the passage
            "quote": quote if len(quote) > 8 and rag.norm(quote) in rag.norm(c["text"]) else "",
        }
        if o["type"] == "mcq":
            opts = [str(x) for x in (q.get("options") or [])]
            try:
                ai = int(q.get("answerIndex"))
            except (TypeError, ValueError):
                continue
            if len(opts) < 3 or not 0 <= ai < len(opts):
                continue
            correct = opts[ai]
            random.shuffle(opts)
            o["options"], o["answer_index"] = opts, opts.index(correct)
        else:
            if not q.get("modelAnswer"):
                continue
            o["model_answer"] = str(q["modelAnswer"])
        qs.append(o)
    if not qs:
        raise UserError("The model did not return usable questions. Try again.")
    st = get_state(db, uid)
    st.quiz = {"id": f"z{int(time.time() * 1000)}", "questions": qs}
    flag_modified(st, "quiz")
    db.commit()
    return skipped


def public_quiz(quiz):
    """Strip answers before sending the quiz to the browser."""
    if not quiz:
        return None
    keep = ("id", "topic_id", "topic_name", "type", "question", "options", "label")
    return {"id": quiz["id"], "questions": [{k: q[k] for k in keep if k in q} for q in quiz["questions"]]}


def submit_quiz(db, uid, ctx, answers):
    """CODE scores MCQs; GENERATION explains mistakes and grades short answers against the cited passage."""
    st = get_state(db, uid)
    quiz = st.quiz
    if not quiz:
        raise UserError("No quiz in progress.")
    Q = quiz["questions"]
    answers = (list(answers or []) + [None] * len(Q))[:len(Q)]
    chunk_text = {c["id"]: c["text"] for c in chunks_of(db, uid, "notes")}
    results, need, warnings = [], [], []
    for q, a in zip(Q, answers):
        r = {"qid": q["id"], "topic_id": q["topic_id"], "topic_name": q["topic_name"], "type": q["type"], "question": q["question"],
             "label": q["label"], "quote": q["quote"], "snippet": q["snippet"], "explanation": q["explanation"], "score": 0.0}
        src = chunk_text.get(q["chunk_id"], q["snippet"])
        if q["type"] == "mcq":
            ok_idx = isinstance(a, int) and 0 <= a < len(q["options"])
            r["chosen"] = q["options"][a] if ok_idx else ""
            r["correct_text"] = q["options"][q["answer_index"]]
            r["score"] = 1.0 if ok_idx and a == q["answer_index"] else 0.0
            if r["score"] == 0:
                need.append({"id": q["id"], "type": "mcq", "question": q["question"], "source": src,
                             "studentAnswer": r["chosen"] or "(left blank)", "correctAnswer": r["correct_text"]})
        else:
            r["chosen"] = (a if isinstance(a, str) else "").strip()
            r["correct_text"] = q["model_answer"]
            if r["chosen"]:
                need.append({"id": q["id"], "type": "short", "question": q["question"], "source": src,
                             "studentAnswer": r["chosen"], "correctAnswer": q["model_answer"]})
            else:
                r["explanation"] = "Left blank. Model answer: " + q["model_answer"]
        results.append(r)
    if need:
        try:
            out = llm.chat_json(ctx, [
                {"role": "system", "content": (
                    'You grade student answers using ONLY the SOURCE passage supplied with each item. Return JSON {"results":[{"id":"...","score":0,"explanation":"..."}]}. '
                    'For type "short": score is 0, 0.5 or 1 (1 = fully correct according to the source, 0.5 = partly, 0 = wrong or blank). '
                    'For type "mcq": the student was wrong, so score is 0 and the explanation must say why the chosen option is wrong and why the correct one is right, in at most 2 sentences. '
                    "For short answers, the explanation says what was right or missing. Be concise and refer to the source.")},
                {"role": "user", "content": json.dumps(need)}], max_tokens=2500)
            by_id = {r["qid"]: r for r in results}
            for g in out.get("results") or []:
                r = by_id.get(str(g.get("id")))
                if not r:
                    continue
                if r["type"] == "short":
                    try:
                        s = float(g.get("score"))
                    except (TypeError, ValueError):
                        s = 0.0
                    r["score"] = 1.0 if s >= 0.75 else 0.5 if s >= 0.25 else 0.0
                if g.get("explanation"):
                    r["explanation"] = str(g["explanation"])
        except llm.LLMError as e:
            warnings.append(f"Could not reach Groq for explanations ({e}). Used basic grading.")
            for r, q in zip(results, Q):
                if r["type"] == "short" and r["chosen"]:
                    r["score"] = logic.overlap_score(r["chosen"], q["model_answer"])
    att = M.Attempt(user_id=uid, ts=int(time.time() * 1000), pct=round(100 * sum(r["score"] for r in results) / len(results)), results=results)
    db.add(att)
    db.flush()
    st.quiz, st.last_result = None, att.id
    db.commit()
    try:
        update_reasons(db, uid, ctx, att)
    except llm.LLMError as e:
        warnings.append(f"Gap reasons could not be generated: {e}")
    return attempt_dict(att), warnings


def update_reasons(db, uid, ctx, att):
    """GENERATION explains each weak topic from the student's actual mistakes."""
    by = {}
    for r in att.results:
        by.setdefault(r["topic_id"], []).append(r)
    st = get_state(db, uid)
    reasons = dict(st.reasons or {})
    items = []
    for key, rs in by.items():
        if sum(r["score"] for r in rs) / len(rs) >= 0.8:
            reasons.pop(key, None)
            continue
        items.append({"topicId": key, "topic": rs[0]["topic_name"],
                      "mistakes": [{"question": r["question"], "studentAnswer": r["chosen"] or "(blank)", "correctAnswer": r["correct_text"], "source": r["label"]}
                                   for r in rs if r["score"] < 1]})
    st.reasons = dict(reasons)
    flag_modified(st, "reasons")
    db.commit()
    if not items:
        return
    out = llm.chat_json(ctx, [
        {"role": "system", "content": "You analyse a student's quiz mistakes. Use ONLY the data given. For each topic write 1-2 sentences on what the student specifically misunderstands, naming the concept and the source label to revisit. "
                                      'Return JSON {"reasons":[{"topicId":"...","reason":"..."}]}.'},
        {"role": "user", "content": json.dumps(items)}], max_tokens=1200)
    keys = {i["topicId"] for i in items}
    for r in out.get("reasons") or []:
        if r.get("topicId") in keys:
            reasons[r["topicId"]] = {"text": str(r.get("reason", "")), "attempt": att.id}
    st.reasons = dict(reasons)
    flag_modified(st, "reasons")
    db.commit()


def last_result(db, uid):
    st = get_state(db, uid)
    a = db.get(M.Attempt, st.last_result) if st.last_result else None
    return attempt_dict(a) if a and a.user_id == uid else None


# ------------------------------------------------------------------ gap report / progress
def gap_report(db, uid):
    topics = topics_of(db, uid)
    attempts = attempts_of(db, uid)
    if not topics or not attempts:
        return {"ready": False}
    m = logic.mastery_map([a.results for a in attempts])
    hits = past_hits(db, uid, topics)
    reasons = get_state(db, uid).reasons or {}
    stats = {}
    for a in attempts:
        for r in a.results:
            s = stats.setdefault(r["topic_id"], [0, 0.0])
            s[0] += 1
            s[1] += r["score"]
    order = {"weak": 0, "medium": 1, "strong": 2, "untested": 3}
    rows = []
    for t in topics:
        lv = logic.level(m.get(t.key))
        why = ("Not tested yet." if lv == "untested" else "Answered correctly in recent attempts." if lv == "strong"
               else (reasons.get(t.key) or {}).get("text") or "Missed questions on this topic.")
        rows.append({"id": t.key, "name": t.name, "level": lv, "mastery": m.get(t.key), "why": why,
                     "answered": stats.get(t.key, [0])[0], "past_hits": hits[t.key]})
    rows.sort(key=lambda r: (order[r["level"]], r["mastery"] or 0))
    counts = {lv: sum(1 for r in rows if r["level"] == lv) for lv in order}
    return {"ready": True, "rows": rows, "counts": counts}


def progress(db, uid):
    topics = topics_of(db, uid)
    attempts = attempts_of(db, uid)
    res = [a.results for a in attempts]
    now = logic.mastery_map(res)
    before = logic.mastery_map(res, len(res) - 1) if len(res) > 1 else {}
    return {
        "attempts": [{"id": a.id, "ts": a.ts, "pct": a.pct, "n": len(a.results)} for a in attempts],
        "topics": [{"id": t.key, "name": t.name, "mastery": now.get(t.key),
                    "delta": round((now[t.key] - before[t.key]) * 100) if t.key in now and t.key in before else None} for t in topics],
    }


# ------------------------------------------------------------------ revision plan
def plan_report(db, uid):
    topics = topics_of(db, uid)
    if not topics:
        return {"ready": False}
    st = get_state(db, uid)
    plan = st.plan or {}
    days, hours = int(plan.get("days", 14)), float(plan.get("hours", 2))
    attempts = attempts_of(db, uid)
    m = logic.mastery_map([a.results for a in attempts])
    hits = past_hits(db, uid, topics)
    mx = max([1] + list(hits.values()))
    total = days * max(15, hours * 60)
    rows = []
    for t in topics:                                   # CODE: priority = weakness x past-paper frequency
        need = 0.65 if m.get(t.key) is None else max(0.08, 1 - m[t.key])
        rows.append({"id": t.key, "name": t.name, "mastery": m.get(t.key), "level": logic.level(m.get(t.key)), "pr": need * (1 + hits[t.key] / mx)})
    rows.sort(key=lambda r: -r["pr"])
    s = sum(r["pr"] for r in rows) or 1
    for r in rows:
        r["min"] = max(10, logic.round5(total * r["pr"] / s))
    sch = logic.build_schedule([{"id": r["id"], "min": r["min"]} for r in rows], days, hours)
    notes = chunks_of(db, uid, "notes")
    idx = rag.Index(notes) if notes else None
    tips = plan.get("tips")
    names = {t.key: t.name for t in topics}
    tmap = {t.key: t for t in topics}
    for r in rows:
        r["overflow"] = sch["overflow"].get(r["id"], 0)
        r["reread"] = [c["label"] for c, _ in idx.search(tq(tmap[r["id"]]), 2)] if idx else []   # RETRIEVAL
        r["tips"] = (tips or {}).get("by", {}).get(r["id"], [])
        del r["pr"]
    return {
        "ready": True, "days": days, "hours": hours, "rows": rows,
        "schedule": [{"n": d["n"], "slots": [{"id": x["id"], "name": names[x["id"]], "min": x["min"]} for x in d["slots"]]} for d in sch["days"]],
        "has_tips": bool(tips), "tips_stale": bool(tips) and tips.get("attempts") != len(attempts),
    }


def set_plan(db, uid, days, hours):
    st = get_state(db, uid)
    plan = dict(st.plan or {})
    plan["days"] = max(1, min(60, int(days)))
    plan["hours"] = max(0.5, min(12.0, float(hours)))
    st.plan = plan
    flag_modified(st, "plan")
    db.commit()


def plan_tips(db, uid, ctx):
    """GENERATION writes short revision actions from the mistakes and retrieved passages."""
    rep = plan_report(db, uid)
    if not rep.get("ready"):
        raise UserError("Build the topic map first.")
    notes = chunks_of(db, uid, "notes")
    idx = rag.Index(notes) if notes else None
    topics = {t.key: t for t in topics_of(db, uid)}
    reasons = get_state(db, uid).reasons or {}
    attempts = attempts_of(db, uid)
    top = []
    for r in rep["rows"][:6]:
        mistakes = []
        for a in reversed(attempts):
            for x in a.results:
                if x["topic_id"] == r["id"] and x["score"] < 1 and len(mistakes) < 3:
                    mistakes.append(x["question"])
        passages = [{"source": c["label"], "text": c["text"][:300]} for c, _ in (idx.search(tq(topics[r["id"]]), 2) if idx else [])]
        top.append({"topicId": r["id"], "topic": r["name"], "masteryPercent": None if r["mastery"] is None else round(r["mastery"] * 100),
                    "reason": (reasons.get(r["id"]) or {}).get("text"), "recentMistakes": mistakes, "passages": passages})
    out = llm.chat_json(ctx, [
        {"role": "system", "content": "You write revision actions. Use ONLY the data given (mistakes, reasons, passages). For each topic give 2-3 short, concrete actions "
                                      '(e.g. re-read a named source, redo a specific type of problem, explain a concept aloud). Return JSON {"tips":[{"topicId":"...","actions":["..."]}]}.'},
        {"role": "user", "content": json.dumps(top)}], max_tokens=1800)
    by = {t["topicId"]: [str(a) for a in t.get("actions", [])] for t in out.get("tips") or [] if t.get("topicId")}
    st = get_state(db, uid)
    plan = dict(st.plan or {})
    plan["tips"] = {"by": by, "attempts": len(attempts)}
    st.plan = plan
    flag_modified(st, "plan")
    db.commit()


# ------------------------------------------------------------------ explain-this-topic
def explain(db, uid, ctx, question, history):
    """RETRIEVAL first; with no matching passage there is no model call. Then GENERATION may only use those passages."""
    question = (question or "").strip()
    if not question:
        raise UserError("Ask a question first.")
    notes = chunks_of(db, uid, "notes")
    hits = [c for c, _ in rag.Index(notes).search(question, 5)] if notes else []
    if not hits:
        return {"text": "I could not find anything about that in your uploaded notes, so I will not guess. Try different wording or upload the relevant chapter.", "sources": []}
    ctx_text = "\n\n".join(f"[{c['id']}] ({c['label']}) {c['text']}" for c in hits)
    msgs = [{"role": "system", "content": (
        'You are a study assistant. Answer ONLY using the SOURCES below. If they do not contain the answer, reply exactly: "Not found in your material." '
        "Cite every claim with its id like [C12]. Be clear and concise, in short paragraphs.\n\nSOURCES:\n" + ctx_text)}]
    for h in (history or [])[-4:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            msgs.append({"role": h["role"], "content": h["content"][:2000]})
    msgs.append({"role": "user", "content": question[:1500]})
    text = llm.chat(ctx, msgs, temperature=0.2, max_tokens=900)
    valid = {c["id"]: c for c in hits}
    used = []

    def fix(m):
        ids = [i for i in re.split(r"[\s,]+", m.group(1)) if i]
        keep = [i for i in ids if i in valid]
        for i in keep:
            if i not in used:
                used.append(i)
        return "[" + ", ".join(keep) + "]" if keep else ""
    text = re.sub(r"\[((?:C\d+\s*,?\s*)+)\]", fix, text)
    return {"text": text, "sources": [valid[i] for i in used]}
