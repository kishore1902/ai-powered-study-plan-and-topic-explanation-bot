"""Retrieval: chunking and BM25 keyword search over the student's own material.

Pure Python, no dependencies, so it runs fine inside a serverless function.
"""
import math
import re

STOP = set(
    "a an the of and or to in on for with is are was were be by as at from that this it its into than then "
    "which what how why when where who whom do does did can could should would may might will shall not no yes "
    "you your we our their they them he she his her i me my about between explain describe write".split()
)


def _stem(w: str) -> str:
    return re.sub(r"(ing|ed|es|s)$", "", w) if len(w) > 4 else w


def tok(s: str) -> list:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 1 and w not in STOP]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", s.lower())).strip()


# ---------- chunking ----------
def chunk_pages(doc_name: str, pages: list, size: int = 900) -> list:
    """pages: [{"label": "p.1", "text": "..."}] -> [{"label": "...", "text": "..."}]"""
    out = []
    for pg in pages:
        t = re.sub(r"\s+", " ", pg["text"]).strip()
        if not t:
            continue
        if len(t) <= size:
            out.append({"label": f"{doc_name} · {pg['label']}", "text": t})
            continue
        s, part = 0, 1
        while s < len(t):
            e = min(len(t), s + size)
            if e < len(t):
                dot = t.rfind(". ", 0, e)
                if dot > s + 400:
                    e = dot + 1
            out.append({"label": f"{doc_name} · {pg['label']} (part {part})", "text": t[s:e].strip()})
            if e >= len(t):
                break
            s = max(e - 150, s + 1)
            part += 1
    return out


def text_to_pages(text: str) -> list:
    pages, cur, n = [], "", 1
    for p in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(p) > 900:
            pages.append({"label": f"§{n}", "text": cur})
            n += 1
            cur = ""
        cur += ("\n" if cur else "") + p
    if cur.strip():
        pages.append({"label": f"§{n}", "text": cur})
    return pages


def split_past(pages: list) -> list:
    """A past paper becomes one chunk per question when it has Q1, Q2... markers."""
    full = "\n".join(p["text"] for p in pages)
    parts = [s.strip() for s in re.split(r"(?=\bQ\s?\d+\s*[.):])", full)]
    parts = [s for s in parts if len(s) > 25 and re.match(r"Q\s?\d+", s)]   # drop the title/header before Q1
    if len(parts) >= 3:
        return [{"label": f"item {i + 1}", "text": p} for i, p in enumerate(parts)]
    return pages


# ---------- BM25 ----------
class Index:
    """chunks: [{"id": "C1", "label": "...", "text": "..."}]"""

    def __init__(self, chunks: list):
        self.docs = []
        self.df = {}
        for c in chunks:
            toks = tok(c["text"] + " " + c["label"])
            tf = {}
            for w in toks:
                tf[w] = tf.get(w, 0) + 1
            self.docs.append((c, tf, len(toks)))
            for w in tf:
                self.df[w] = self.df.get(w, 0) + 1
        self.n = len(self.docs)
        self.avg = (sum(d[2] for d in self.docs) / self.n) if self.n else 1.0

    def search(self, query: str, k: int = 4) -> list:
        """Returns [(chunk, score)] best first."""
        q = set(tok(query))
        k1, b = 1.5, 0.75
        res = []
        for c, tf, ln in self.docs:
            s = 0.0
            for w in q:
                f = tf.get(w)
                if not f:
                    continue
                n = self.df[w]
                idf = math.log(1 + (self.n - n + 0.5) / (n + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * ln / self.avg))
            if s > 0:
                res.append((c, s))
        res.sort(key=lambda x: -x[1])
        return res[:k]
