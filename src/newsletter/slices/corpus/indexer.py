"""Index a company-context directory into ContextChunk rows.

Incremental: each file's content hash is compared against the stored hash;
unchanged files are skipped. Changed/new files are re-chunked, embedded in a
single batch call, and persisted via ``replace_file_chunks``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from newsletter.core.embeddings import EmbeddingClient, serialize
from newsletter.core.logging import get_logger
from newsletter.slices.corpus import repository
from newsletter.slices.corpus.chunking import chunk_text, extract_keywords
from newsletter.slices.corpus.repository import ChunkInsert
from newsletter.slices.corpus.schemas import IndexReport

log = get_logger(__name__)

_SUFFIXES = {".md", ".txt"}


def index_corpus(session: Session, *, root: Path, embed_client: EmbeddingClient) -> IndexReport:
    """Scan ``root`` recursively and (re)index changed Markdown/text files."""
    report = IndexReport()
    stored = repository.file_hashes(session)

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _SUFFIXES)
    for path in files:
        report.scanned += 1
        rel = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if stored.get(rel) == file_hash:
            report.skipped += 1
            continue

        texts = chunk_text(content)
        if not texts:
            # No indexable content. Clear any stale chunks for this path so an
            # emptied file doesn't leave orphans. We can't record a hash without
            # a row, so empty files are re-checked each run (cheap: no embed).
            repository.replace_file_chunks(session, source_path=rel, file_hash=file_hash, chunks=[])
            continue
        inserts = _build_inserts(texts, embed_client)
        written = repository.replace_file_chunks(
            session, source_path=rel, file_hash=file_hash, chunks=inserts
        )
        report.indexed += 1
        report.chunks += written
        report.embedded += sum(1 for c in inserts if c.embedding is not None)

    log.info(
        "corpus.indexed",
        scanned=report.scanned,
        indexed=report.indexed,
        skipped=report.skipped,
        chunks=report.chunks,
        embedded=report.embedded,
    )
    return report


def _build_inserts(texts: list[str], embed_client: EmbeddingClient) -> list[ChunkInsert]:
    if not texts:
        return []
    vectors = embed_client.embed(texts)
    if vectors and len(vectors) < len(texts):
        log.warning("corpus.embed.partial", expected=len(texts), got=len(vectors))
    model = getattr(embed_client, "model", None)
    inserts: list[ChunkInsert] = []
    for index, text in enumerate(texts):
        has_vector = bool(vectors) and index < len(vectors)
        embedding = serialize(vectors[index]) if has_vector else None
        inserts.append(
            ChunkInsert(
                text=text,
                keywords=extract_keywords(text),
                embedding=embedding,
                embedding_model=model if embedding is not None else None,
            )
        )
    return inserts


__all__ = ["index_corpus"]
