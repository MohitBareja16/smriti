"""Metric definitions. Every number in a results table is computed here, so the definitions live in
one place (see docs/research/README.md, "Metrics")."""

from __future__ import annotations

from dataclasses import dataclass

from smriti.guardrails import IDK
from smriti.types import Answer


def is_idk(answer: Answer) -> bool:
    return answer.text.strip() == IDK or "don't know" in answer.text.lower()


def score_answer(answer: Answer, item: dict) -> dict:
    """Score one QA item.

    correct:   all `expect_contains` strings appear (case-insensitive) in the answer text, citations or
               attachment; for unanswerable items (`expect_idk`), the system abstains.
    cited:     the gold source document appears in the citations (answerable items only).
    """
    if item.get("expect_idk"):
        return {"answerable": False, "correct": is_idk(answer), "cited": None}
    haystack = f"{answer.text} {' '.join(answer.citations)} {answer.attachment or ''}".lower()
    correct = all(s.lower() in haystack for s in item["expect_contains"])
    cited = any(item["expect_source"] in c for c in answer.citations)
    return {"answerable": True, "correct": correct, "cited": cited}


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..1)."""
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float
    accuracy: float


def calibration(confidences: list[float], correct: list[bool], n_bins: int = 10
                ) -> tuple[float, list[CalibrationBin]]:
    """Expected Calibration Error (ECE) with equal-width bins, plus the reliability-diagram bins.

    ECE = Σ_b (|b| / N) · |accuracy(b) − mean_confidence(b)|. Lower is better; 0 = perfectly calibrated.
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must have the same length")
    n = len(confidences)
    bins: list[CalibrationBin] = []
    ece = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        idx = [i for i, c in enumerate(confidences) if (lo <= c < hi) or (b == n_bins - 1 and c == 1.0)]
        if not idx:
            bins.append(CalibrationBin(lo, hi, 0, 0.0, 0.0))
            continue
        conf = sum(confidences[i] for i in idx) / len(idx)
        acc = sum(correct[i] for i in idx) / len(idx)
        ece += len(idx) / n * abs(acc - conf)
        bins.append(CalibrationBin(lo, hi, len(idx), conf, acc))
    return ece, bins
