"""7B re-ranker helper — lightweight wrapper for loading an OSS 7B model in int8
for re-ranking candidate passages and scoring them.

Design decisions:
- Default model: environment variable `RE_RANKER_MODEL` or fallback to a small stub
- Uses bitsandbytes `BitsAndBytesConfig` when available and environment indicates 8-bit
- Testable in CI by setting `RE_RANKER_TEST_MODE=1` which uses a deterministic stub model
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
except Exception:
    AutoTokenizer = None
    AutoModelForCausalLM = None
    BitsAndBytesConfig = None
    torch = None

from agents.tools.mistral_re_ranker_adapter import ReRankerMistralAdapter
from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class ReRankCandidate:
    id: str
    text: str


class _StubReRanker:
    """Simple deterministic scorer used in test mode or when model unavailable.

    Scoring strategy: length-based deterministic score for reproducible tests.
    """

    def __init__(self):
        pass

    def score(self, query: str, candidates: Sequence[ReRankCandidate]) -> list[float]:
        # deterministic scoring: longer overlap / length heuristics
        qwords = set(query.lower().split())
        scores = []
        for c in candidates:
            common = len(qwords.intersection(set(c.text.lower().split())))
            # base score is number of common words + normalized length
            scores.append(float(common) + len(c.text) / 1000.0)
        return scores


class ReRanker:
    """Wraps a quantized 7B model for re-ranking tasks.

    On an RTX 3090 we expect int8 loading to be available; for tests the
    `RE_RANKER_TEST_MODE=1` environment variable will use the deterministic stub
    so tests run quickly and offline.
    """

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or os.environ.get("RE_RANKER_MODEL")
        self.test_mode = os.environ.get("RE_RANKER_TEST_MODE") in ("1", "true")
        self.model = None
        self.tokenizer = None
        self._stub = _StubReRanker()
        self.adapter: ReRankerMistralAdapter | None = None

        if self.test_mode or AutoModelForCausalLM is None:
            return

        try:
            self.adapter = ReRankerMistralAdapter()
        except Exception as exc:  # pragma: no cover - adapter optional
            logger.warning(
                "ReRanker adapter init failed, falling back to direct model: %s", exc
            )
            self.adapter = None

        if self.adapter is None:
            self._load_model()

    def _load_model(self) -> None:
        # If user set 8-bit preference, configure bitsandbytes
        load_in_8bit = os.environ.get("RE_RANKER_LOAD_8BIT", "1") in ("1", "true")
        if load_in_8bit and BitsAndBytesConfig is not None and torch is not None:
            bnb = BitsAndBytesConfig(
                load_in_8bit=True,
                bnb_8bit_compute_dtype=getattr(torch, "float16", None),
                bnb_8bit_use_double_quant=True,
            )
            model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                device_map="auto",
                quantization_config=bnb,
                trust_remote_code=True,
            )
        else:
            # fallback non-quantized loading
            model = AutoModelForCausalLM.from_pretrained(
                self.model_id, device_map="auto", trust_remote_code=True
            )

        tokenizer = AutoTokenizer.from_pretrained(self.model_id)

        self.model = model
        self.tokenizer = tokenizer

    def score(self, query: str, candidates: Sequence[ReRankCandidate]) -> list[float]:
        """Return a list of scores aligned with candidates.

        Prefers the shared Mistral adapter; falls back to the original
        AutoModel-based heuristic or the deterministic stub when unavailable.
        """
        if self.adapter is not None:
            try:
                adapter_scores = self.adapter.score_candidates(query, candidates)
            except Exception as exc:  # pragma: no cover - adapter optional
                logger.warning(
                    "ReRanker adapter scoring failed, will fall back: %s", exc
                )
                adapter_scores = None
            if adapter_scores is not None:
                return adapter_scores

        if self.test_mode or AutoModelForCausalLM is None:
            return self._stub.score(query, candidates)

        if self.model is None or self.tokenizer is None:
            try:
                self._load_model()
            except Exception as exc:  # pragma: no cover - fallback path
                logger.warning("Failed loading fallback re-ranker model: %s", exc)
                return self._stub.score(query, candidates)

        if self.model is None or self.tokenizer is None:
            return self._stub.score(query, candidates)

        return self._score_with_model(query, candidates)

    def _score_with_model(
        self, query: str, candidates: Sequence[ReRankCandidate]
    ) -> list[float]:
        scores: list[float] = []
        for c in candidates:
            input_text = f"Query: {query}\nCandidate: {c.text}\nScore:"
            inputs = self.tokenizer(input_text, return_tensors="pt")
            if torch is not None and torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}

            with torch.no_grad():
                out = self.model(**inputs, return_dict=True)

            logits = out.logits
            last_logits = logits[:, -1, :]
            probs = last_logits.softmax(dim=-1).max().values.item()
            scores.append(float(probs))

        return scores


def simple_demo():
    model = ReRanker()
    queries = "Is the company profitable?"
    cands = [
        ReRankCandidate(id="a1", text="The company saw revenue growth in Q4."),
        ReRankCandidate(id="a2", text="We reported losses last year."),
    ]
    print(model.score(queries, cands))


if __name__ == "__main__":
    simple_demo()
