"""Knowledge base: short, trusted notes the companion can draw on, with sources shown to the person.

The library is Markdown files in `library/` (written in our own words, each linking to its source).
Files are split into sections, embedded once (embeddings are cached in SQLite by content hash),
and searched by cosine similarity for each message. Faith notes are only used for the faith the
person chose.
"""

import asyncio
import hashlib
import logging
import re
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel

log = logging.getLogger(__name__)

LIBRARY = Path(__file__).parent / "library"
Embed = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass(frozen=True)
class Chunk:
    doc: str
    title: str
    section: str
    source: str
    url: str
    topic: str
    faith: str | None
    text: str

    @property
    def key(self) -> str:
        return hashlib.sha256(self.embed_text.encode()).hexdigest()

    @property
    def embed_text(self) -> str:
        return f"{self.title}. {self.section}\n{self.text}"


class Passage(BaseModel):
    """A note given to the companion for one reply. `n` is the citation marker, e.g. [1]."""

    n: int
    title: str
    section: str
    source: str
    url: str
    text: str
    score: float


class Source(BaseModel):
    """What the person sees under a reply that drew on the knowledge base."""

    n: int
    title: str
    source: str
    url: str


# ---------- loading ----------


def parse_doc(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not match:
        raise ValueError(f"{path.name}: missing front matter")
    meta = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    for required in ("title", "source", "url", "topic"):
        if not meta.get(required):
            raise ValueError(f"{path.name}: missing '{required}'")
    chunks = []
    for part in re.split(r"^## ", match.group(2), flags=re.M):
        heading, _, body = part.partition("\n")
        if body.strip():
            chunks.append(
                Chunk(
                    doc=path.stem,
                    title=meta["title"],
                    section=heading.strip(),
                    source=meta["source"],
                    url=meta["url"],
                    topic=meta["topic"],
                    faith=meta.get("faith") or None,
                    text=" ".join(body.split()),
                )
            )
    return chunks


def load_library(folder: Path = LIBRARY) -> list[Chunk]:
    return [c for path in sorted(folder.glob("*.md")) for c in parse_doc(path)]


# ---------- citations ----------

_MARKER = re.compile(r"\s?\[(\d+(?:\s*,\s*\d+)*)\]")


def strip_citations(text: str, passages: list[Passage]) -> tuple[str, list[Source]]:
    """Remove [n] markers from a reply and return the sources it actually cited."""
    cited: list[int] = []
    for group in _MARKER.findall(text):
        cited += [int(n) for n in group.split(",")]
    by_n = {p.n: p for p in passages}
    sources: dict[str, Source] = {}  # one entry per source document
    for n in cited:
        p = by_n.get(n)
        if p and p.url not in sources:
            sources[p.url] = Source(n=p.n, title=p.title, source=p.source, url=p.url)
    return _MARKER.sub("", text), list(sources.values())


def clean_markers(text: str) -> str:
    return _MARKER.sub("", text)


# ---------- search ----------


class KnowledgeBase:
    def __init__(
        self,
        embed: Embed,
        db_path: str = ":memory:",
        chunks: list[Chunk] | None = None,
        model: str = "default",
        min_score: float = 0.3,
        k: int = 3,
    ) -> None:
        self.embed, self.model, self.min_score, self.k = embed, model, min_score, k
        self.chunks = load_library() if chunks is None else chunks
        self._matrix: np.ndarray | None = None
        self._ready = asyncio.Lock()
        self._db_lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS kb_embeddings "
            "(key TEXT, model TEXT, vec BLOB, PRIMARY KEY (key, model))"
        )

    async def ensure_index(self) -> None:
        """Embed any sections not already cached. Cheap after the first run."""
        if self._matrix is not None or not self.chunks:
            return
        async with self._ready:
            if self._matrix is not None:
                return
            cached = self._cached()
            missing = [c for c in self.chunks if c.key not in cached]
            if missing:
                vectors = await self.embed([c.embed_text for c in missing])
                for c, v in zip(missing, vectors, strict=True):
                    cached[c.key] = np.asarray(v, dtype=np.float32)
                self._store({c.key: cached[c.key] for c in missing})
                log.info("knowledge base: embedded %d new sections", len(missing))
            self._matrix = _normalise(np.stack([cached[c.key] for c in self.chunks]))

    async def search(self, query: str, faith: str | None = None) -> list[Passage]:
        await self.ensure_index()
        if self._matrix is None:
            return []
        q = _normalise(np.asarray((await self.embed([query]))[0], dtype=np.float32)[None, :])[0]
        scores = self._matrix @ q
        out: list[Passage] = []
        used_docs: set[str] = set()
        top = float(scores.max())
        for i in np.argsort(-scores):
            c, score = self.chunks[i], float(scores[i])
            # Keep only clear matches: above the floor, and close to the best one.
            if score < self.min_score or score < top - 0.1 or len(out) >= self.k:
                break
            if (c.faith and c.faith != faith) or c.doc in used_docs:
                continue  # faith notes only for the chosen faith; one section per document
            used_docs.add(c.doc)
            out.append(
                Passage(
                    n=len(out) + 1,
                    title=c.title,
                    section=c.section,
                    source=c.source,
                    url=c.url,
                    text=c.text,
                    score=round(score, 3),
                )
            )
        return out

    def _cached(self) -> dict[str, np.ndarray]:
        with self._db_lock:
            rows = self._db.execute(
                "SELECT key, vec FROM kb_embeddings WHERE model = ?", (self.model,)
            ).fetchall()
        return {k: np.frombuffer(v, dtype=np.float32) for k, v in rows}

    def _store(self, vectors: dict[str, np.ndarray]) -> None:
        with self._db_lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO kb_embeddings VALUES (?, ?, ?)",
                [(k, self.model, v.astype(np.float32).tobytes()) for k, v in vectors.items()],
            )


def _normalise(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)


def openai_embedder(api_key: str | None, model: str) -> Embed:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)

    async def embed(texts: list[str]) -> list[list[float]]:
        res = await client.embeddings.create(model=model, input=texts)
        return [d.embedding for d in res.data]

    return embed
