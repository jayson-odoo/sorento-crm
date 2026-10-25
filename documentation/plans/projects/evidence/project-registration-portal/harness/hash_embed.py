"""Harness substitute: the sandbox's OpenAI credit is exhausted (429 insufficient_quota), so the
embedding POST is replaced by a deterministic hashed bag-of-words vector (1536 dims, L2 normalised).
Process-local, nothing in the repo is changed."""
import hashlib, math, re

def _vec(text, dim=1536):
    v = [0.0] * dim
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]

def install():
    from app.services import embedding_worker as ew
    ew._post_embeddings = lambda chunks, timeout=None: [_vec(c) for c in chunks]
