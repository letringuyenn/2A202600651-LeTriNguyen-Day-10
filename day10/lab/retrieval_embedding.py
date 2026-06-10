"""Deterministic local embedding utilities for Day 10.

The lab pipeline needs a stable, offline embedding path so publish, eval, and
grading can run without downloading a sentence-transformer model at runtime.
This helper keeps the vector size compatible with the original MiniLM setup
while remaining fully local and deterministic.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").casefold().replace("đ", "d"))
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    ascii_text = ascii_text.replace("-", " ")
    return " ".join(_TOKEN_RE.findall(ascii_text))


def _hash_index(token: str, dimensions: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
    index = int.from_bytes(digest[:8], "big") % dimensions
    sign = 1.0 if digest[8] % 2 == 0 else -1.0
    return index, sign


def _vectorize(text: str, dimensions: int) -> list[float]:
    tokens = _normalize_text(text).split()
    vec = [0.0] * dimensions
    if not tokens:
        return vec

    feature_stream: list[tuple[str, float]] = []
    feature_stream.extend((token, 1.0) for token in tokens)
    feature_stream.extend((f"{a}_{b}", 1.5) for a, b in zip(tokens, tokens[1:]))

    for feature, weight in feature_stream:
        idx, sign = _hash_index(feature, dimensions)
        vec[idx] += sign * weight

    norm = math.sqrt(sum(value * value for value in vec))
    if norm:
        vec = [value / norm for value in vec]
    return vec


@dataclass(frozen=True)
class LocalHashEmbeddingFunction:
    """Chroma-compatible embedding function with no external downloads."""

    dimensions: int = 384

    def __call__(self, input: Iterable[str]) -> List[List[float]]:
        return [_vectorize(text, self.dimensions) for text in input]

    def embed_documents(self, input: Iterable[str]) -> List[List[float]]:
        return self(input)

    def embed_query(self, input: Iterable[str] | str) -> List[List[float]] | List[float]:
        if isinstance(input, str):
            return _vectorize(input, self.dimensions)
        return self(input)

    def name(self) -> str:
        return f"local_hash_embedding_{self.dimensions}"


def get_embedding_function(dimensions: int = 384) -> LocalHashEmbeddingFunction:
    return LocalHashEmbeddingFunction(dimensions=dimensions)
