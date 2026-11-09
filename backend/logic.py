"""Deterministic maths: mastery, levels, scheduling, basic grading fallback. No LLM here."""
from . import rag


def mastery_map(attempts: list, up_to=None) -> dict:
    """attempts: list of result-lists (oldest first). Newest attempt counts 60%."""
    m = {}
    for results in (attempts if up_to is None else attempts[:up_to]):
        by = {}
        for r in results:
            by.setdefault(r["topic_id"], []).append(r["score"])
        for t, sc in by.items():
            acc = sum(sc) / len(sc)
            m[t] = acc if t not in m else 0.4 * m[t] + 0.6 * acc
    return m


def level(m) -> str:
    if m is None:
        return "untested"
    return "weak" if m < 0.5 else "medium" if m < 0.8 else "strong"


def round5(x: float) -> int:
    return int(x / 5 + 0.5) * 5


def build_schedule(items: list, days: int, hours: float) -> dict:
    """items: [{"id", "min"}] in priority order -> day-by-day slots."""
    cap = max(15, int(round(hours * 60)))
    out, over = [], {}
    d, left = 0, cap
    for it in items:
        r = it["min"]
        while r > 0:
            if d >= days:
                over[it["id"]] = over.get(it["id"], 0) + r
                break
            take = min(r, left)
            while len(out) <= d:
                out.append({"n": len(out) + 1, "slots": []})
            out[d]["slots"].append({"id": it["id"], "min": take})
            r -= take
            left -= take
            if left <= 0:
                d += 1
                left = cap
    return {"days": [x for x in out if x["slots"]], "overflow": over}


def overlap_score(answer: str, model: str) -> float:
    a, m = set(rag.tok(answer)), set(rag.tok(model))
    if not m:
        return 0.0
    hit = len(m & a) / len(m)
    return 1.0 if hit >= 0.6 else 0.5 if hit >= 0.3 else 0.0
