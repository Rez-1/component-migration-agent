"""Guide retrieval: a keyword (BM25) retriever over the vendored migration guide.

It sits behind LangChain's ``BaseRetriever`` interface, so the M5 "keyword vs
embeddings" experiment is a configuration value (``retrieval``) rather than a
refactor. Each document is one change (or one change-less section) of the guide, as
``migrations.guide`` splits it. A section marked as handled by a codemod is labelled,
never demoted: codemods often handle only the common form of a change (ticket #14).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, PrivateAttr

from migrator.migrations import MigrationSpec
from migrator.migrations.guide import GuideChange, load_guide

_WORD = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|\d+")
_DOTTED = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+")
_CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")
_STOP_WORDS = (
    "a an and are as at be by for from has have in is it its of on or that the this to "
    "with you your was were will can not no use used "
    # TypeScript and test-runner boilerplate, which says nothing about the change
    "type types must side left right hand operation property exist exists does "
    "assignable overload overloads matches match call error errors value argument "
    "parameter expected received unable find element role name any number bigint "
    "enum string"
)
_STOP = frozenset(_STOP_WORDS.split())
K1, B = 1.5, 0.75
SECTION_BOOST = 4.0  # a query identifier that names the section (``Autocomplete``)
TITLE_BOOST = 2.0  # a query identifier the change heading names (``renderOption``)
DOTTED_BOOST = 1.0  # a dotted name from the query in the text (``theme.spacing``)
DOTTED_LEAD_BOOST = 6.0  # ... in the heading or the first lines
LEAD_CHARS = 160


def tokens(text: str) -> list[str]:
    """Lower-cased words, with camelCase identifiers also split into their parts."""
    out: list[str] = []
    for word in _WORD.findall(text):
        lower = word.lower()
        if lower in _STOP:
            continue
        out.append(lower)
        parts = _CAMEL.findall(word)
        if len(parts) > 1:
            out.extend(p.lower() for p in parts if p.lower() not in _STOP)
    return out


def identifiers(text: str) -> set[str]:
    return set(_WORD.findall(text))


def to_document(change: GuideChange) -> Document:
    return Document(
        page_content=change.body,
        id=change.id,
        metadata={
            "id": change.id,
            "file": change.file,
            "section": change.section,
            "title": change.title,
            "kind": change.kind,
            "codemod_handled": change.codemod_handled,
        },
    )


class GuideRetriever(BaseRetriever):
    """BM25 over the guide's changes, with boosts for names in the query."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    documents: list[Document]
    k: int = 3
    _tf: list[Counter[str]] = PrivateAttr(default_factory=list)
    _df: Counter[str] = PrivateAttr(default_factory=Counter)
    _avg_len: float = PrivateAttr(default=1.0)

    def model_post_init(self, context: object, /) -> None:
        for doc in self.documents:
            meta = doc.metadata
            tf = Counter(tokens(f"{meta['section']} {meta['title']} {doc.page_content}"))
            self._tf.append(tf)
            self._df.update(tf.keys())
        lengths = [sum(tf.values()) for tf in self._tf]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0

    @classmethod
    def from_spec(cls, spec: MigrationSpec, k: int = 3) -> GuideRetriever:
        changes = load_guide(spec.guide_dir(), spec.guide)
        return cls(documents=[to_document(c) for c in changes], k=k)

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        names = identifiers(query)
        dotted = set(_DOTTED.findall(query))
        n = len(self.documents)
        out: list[float] = []
        for doc, tf in zip(self.documents, self._tf, strict=True):
            length = sum(tf.values())
            score = 0.0
            for term in set(q):
                f = tf.get(term, 0)
                if not f:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * length / self._avg_len))
            meta = doc.metadata
            if str(meta["section"]) in names:
                score += SECTION_BOOST
            title_words = identifiers(str(meta["title"]))
            score += TITLE_BOOST * len(names & title_words - _STOP)
            text = f"{meta['title']} {doc.page_content}"
            lead = f"{meta['title']} {doc.page_content[:LEAD_CHARS]}"
            # An API name in the heading or first lines is what the section is about.
            score += sum(
                DOTTED_LEAD_BOOST if d in lead else DOTTED_BOOST for d in dotted if d in text
            )
            out.append(score)
        return out

    def rank(self, query: str, k: int | None = None) -> list[Document]:
        scored = [(s, i) for i, s in enumerate(self.scores(query)) if s > 0]
        scored.sort(key=lambda si: (-si[0], si[1]))
        return [self.documents[i] for _, i in scored[: k or self.k]]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self.rank(query)


def heading(doc: Document) -> str:
    meta = doc.metadata
    marker = " (codemod)" if meta.get("codemod_handled") else ""
    if meta.get("kind") == "section":
        return f"{meta['section']}{marker}"
    return f"{meta['section']} › {meta['title']}{marker}"


MAX_SECTION_CHARS = 3500


def render_section(doc: Document, link_base: str | None) -> str:
    body = doc.page_content.strip()
    if link_base:
        body = re.sub(r"\]\((/[^)]*)\)", lambda m: f"]({link_base}{m.group(1)})", body)
    if len(body) > MAX_SECTION_CHARS:
        body = body[:MAX_SECTION_CHARS].rstrip() + "\n\n(… cut; `search_guide` for more)"
    return f"**{heading(doc)}**\n\n{body}"


def unique(docs: Iterable[Document]) -> list[Document]:
    seen: set[str] = set()
    out: list[Document] = []
    for doc in docs:
        key = str(doc.metadata["id"])
        if key not in seen:
            seen.add(key)
            out.append(doc)
    return out
