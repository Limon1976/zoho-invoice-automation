from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class CategoryResult:
    category: str
    confidence: float
    source: str


class CategoryDetector:
    """Detects document category using embeddings with LLM fallback.

    Strategy:
    1) Embedding similarity between the document text and per-category
       canonical keyword corpora (configurable via JSON).
    2) If confidence is low, fallback to few-shot LLM classification.
    """

    DEFAULT_KEYWORDS: Dict[str, List[str]] = {
        "CARS": [
            "VIN", "vehicle", "car", "auto", "engine", "transmission", "BMW",
            "Mercedes", "Audi", "registration", "license plate"
        ],
        "FLOWERS": [
            "flower", "flowers", "bouquet", "róża", "tulip", "orchid", "kwiaty"
        ],
        "UTILITIES": [
            "electricity", "energy", "gas", "water", "heating", "waste", "utility"
        ],
        "SERVICES": [
            "service", "consulting", "installation", "repair", "maintenance",
            "transport", "delivery", "parking"
        ],
        "FOOD": [
            "restaurant", "cafe", "catering", "meal", "food", "pizza", "burger"
        ],
        "OTHER": ["invoice", "document", "general goods"]
    }

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = Path(config_path) if config_path else Path("config/category_keywords.json")
        self.keywords = self._load_keywords()
        self._client = None
        self._label_embeddings: Dict[str, List[float]] | None = None

    def _load_keywords(self) -> Dict[str, List[str]]:
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                    # Normalize shape
                    normalized = {k.upper(): list(v or []) for k, v in data.items()}
                    # Ensure defaults exist
                    for k, v in self.DEFAULT_KEYWORDS.items():
                        normalized.setdefault(k, v)
                    return normalized
        except Exception:
            pass
        return dict(self.DEFAULT_KEYWORDS)

    # --- Embeddings helpers ---
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore
            except Exception as e:
                raise RuntimeError("OpenAI SDK is required for CategoryDetector") from e
            self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._client

    def _embed(self, text: str) -> List[float]:
        text = (text or "").strip()
        if not text:
            return []
        client = self._get_client()
        resp = client.embeddings.create(model="text-embedding-3-small", input=text[:4000])
        return list(resp.data[0].embedding)

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _build_label_embeddings(self) -> Dict[str, List[float]]:
        if self._label_embeddings is not None:
            return self._label_embeddings
        label_texts: Dict[str, str] = {}
        for label, words in self.keywords.items():
            # Create a compact canonical description for each category
            label_texts[label] = ", ".join(words)
        embeddings = {label: self._embed(text) for label, text in label_texts.items()}
        self._label_embeddings = embeddings
        return embeddings

    # --- LLM fallback ---
    def _llm_classify(self, text: str) -> Tuple[str, float]:
        client = self._get_client()
        system = (
            "You are a strict classifier. Classify the document into one of: "
            "CARS, FLOWERS, UTILITIES, SERVICES, FOOD, OTHER. "
            "Respond as JSON: {\"category\": <label>, \"confidence\": <0..1>}"
        )
        few_shots = [
            ("FV/3437/2025 ... VIN WDB... Mercedes, vehicle service, registration", "CARS"),
            ("Energy bill for office electricity consumption", "UTILITIES"),
            ("Bouquet purchase invoice, roses and tulips", "FLOWERS"),
            ("Catering services for corporate lunch", "FOOD"),
            ("Website maintenance and consulting invoice", "SERVICES"),
        ]
        examples = "\n".join([f"Example: {t} => {c}" for t, c in few_shots])
        prompt = f"Text:\n{text[:5000]}\n\n{examples}"
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        content = completion.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
            category = str(data.get("category") or "OTHER").upper()
            confidence = float(data.get("confidence") or 0.5)
            if category not in self.keywords:
                category = "OTHER"
            return category, max(0.0, min(1.0, confidence))
        except Exception:
            return "OTHER", 0.5

    # --- Public API ---
    def detect(self, text: str, supplier_name: str = "", product_description: str = "") -> CategoryResult:
        # Build a rich text representation
        combined = "\n".join([
            str(text or ""),
            f"supplier: {supplier_name}",
            f"desc: {product_description}",
        ])

        # 1) Embedding similarity
        label_embeddings = self._build_label_embeddings()
        doc_emb = self._embed(combined)
        sims = {label: self._cosine(doc_emb, emb) for label, emb in label_embeddings.items()}
        best_label = max(sims, key=lambda k: sims[k]) if sims else "OTHER"
        best_score = sims.get(best_label, 0.0)

        if best_score >= 0.28:  # threshold tuned for small model
            return CategoryResult(category=best_label, confidence=float(best_score), source="embeddings")

        # 2) LLM fallback
        label, conf = self._llm_classify(combined)
        return CategoryResult(category=label, confidence=conf, source="llm_few_shot")


