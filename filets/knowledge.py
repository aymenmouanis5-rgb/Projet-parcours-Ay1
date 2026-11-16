"""The knowledge base: documents, their embeddings, and filtered cosine search."""

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from filets.llm import EMBED_MODEL, LLMClient

CORPUS_DIR = Path("corpus")
CACHE_FILE = CORPUS_DIR / ".embeddings.json"
# Each retrieval fills one slot per kind of memory, so that no single source can crowd out the others.
SLOT_OF_TYPE = {"own_promise": "promise", "market_ledger": "recent", "talk_summary": "recent"}
SLOTS = ("corpus", "promise", "recent")
# nomic-embed-text expects these task prefixes
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


@dataclass(frozen=True)
class Document:
    id: str
    type: str
    sim_time: float
    visibility: str  # "shared", or "personal" for its owner only
    text: str
    hamlet: str | None = None
    owner: int | None = None


def read_document(path: Path) -> Document:
    """Parse a corpus file: `key: value` lines between two --- lines, then the text."""
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    return Document(id=fields["id"], type=fields["type"], sim_time=float(fields["sim_time"]),
                    visibility=fields["visibility"], hamlet=fields.get("hamlet"), text=body.strip())


def normalized(vectors) -> np.ndarray:
    matrix = np.array(vectors, dtype=float)
    return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class KnowledgeBase:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.documents: list[Document] = []
        self.vectors: np.ndarray | None = None
        self.lock = threading.Lock()
        self._load_corpus()

    def _load_corpus(self) -> None:
        """Embed the static corpus, reusing the cached vectors of unchanged documents."""
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
        documents = [read_document(path) for path in sorted(CORPUS_DIR.glob("*.md"))]
        keys = [hashlib.sha256(f"{EMBED_MODEL}:{d.text}".encode()).hexdigest() for d in documents]
        missing = [(key, d) for key, d in zip(keys, documents) if key not in cache]
        if missing:
            vectors = self.llm.embed([DOCUMENT_PREFIX + d.text for _, d in missing])
            cache.update({key: vector for (key, _), vector in zip(missing, vectors)})
            CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
        self.documents = documents
        self.vectors = normalized([cache[key] for key in keys])

    def add(self, documents: list[Document]) -> None:
        if not documents:
            return
        vectors = self.llm.embed([DOCUMENT_PREFIX + d.text for d in documents])
        with self.lock:
            self.documents.extend(documents)
            self.vectors = np.vstack([self.vectors, normalized(vectors)])

    def search(self, query: str, reader: int, before: float) -> list[tuple[str, Document, float]]:
        """Best document per slot among those the reader may see, all strictly older than `before`.

        A slot stays empty when no document qualifies, such as the promises of a silent run.
        """
        vector = normalized(self.llm.embed([QUERY_PREFIX + query]))[0]
        best: dict[str, tuple[Document, float]] = {}
        with self.lock:
            allowed = [i for i, d in enumerate(self.documents)
                       if d.sim_time < before and (d.visibility == "shared" or d.owner == reader)]
            scores = self.vectors[allowed] @ vector
            for index, score in zip(allowed, scores):
                document = self.documents[index]
                slot = SLOT_OF_TYPE.get(document.type, "corpus")
                if slot not in best or score > best[slot][1]:
                    best[slot] = (document, float(score))
        return [(slot, *best[slot]) for slot in SLOTS if slot in best]

    def save(self, path: Path) -> None:
        """Keep the documents of a run; the vectors can be recomputed from their text."""
        path.write_text(json.dumps([asdict(d) for d in self.documents], ensure_ascii=False, indent=1),
                        encoding="utf-8")
