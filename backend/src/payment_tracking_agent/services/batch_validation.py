"""Deterministic batch-level CCD validation summary.

Produces a small dataclass summarizing what the CCD parser and control
records tell us about a batch. This is intentionally lightweight — full
FedACH / NACHA syntax correction is planned as a future enhancement.

The summary is consumed by :class:`~payment_tracking_agent.agents.ai_risk.
AIRiskClassificationService` to classify batch risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from payment_tracking_agent.parsers.ccd import ParsedCcdFile


@dataclass(frozen=True)
class BatchValidationSummary:
    batch_key: str
    source_file: str
    file_parsed: bool
    payment_count: int
    accepted_count: int
    parser_errors: list[str] = field(default_factory=list)
    validation_findings: list[str] = field(default_factory=list)
    syntax_valid: bool = True

    def severity(self) -> str:
        """Return LOW / MEDIUM / HIGH severity for the batch."""
        if not self.file_parsed or not self.syntax_valid or self.parser_errors:
            return "HIGH"
        if self.validation_findings:
            return "MEDIUM"
        return "LOW"


def summarize_ccd(
    batch_key: str,
    source_file: str,
    parsed: ParsedCcdFile,
) -> BatchValidationSummary:
    """Build a validation summary from a parsed CCD file."""
    parser_errors = list(parsed.errors)
    findings: list[str] = []
    if not parsed.syntax_valid:
        findings.append(
            "Bank-side syntax validation failed on one or more entry-detail records."
        )
    if not parsed.entries:
        findings.append("CCD file parsed with zero entry-detail records.")
    payment_count = len(parsed.entries)
    return BatchValidationSummary(
        batch_key=batch_key,
        source_file=source_file,
        file_parsed=True,
        payment_count=payment_count,
        accepted_count=payment_count,
        parser_errors=parser_errors,
        validation_findings=findings,
        syntax_valid=parsed.syntax_valid,
    )
