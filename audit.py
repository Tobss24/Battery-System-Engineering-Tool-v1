"""Audit trail, engineering status handling and the missing-data exception.

Engineering status vocabulary (see engineering_basis.md, section 14):

    PASS     the check satisfies its defined criterion
    WARNING  the calculation can proceed, but an assumption or incomplete input exists
    MISSING  information required to evaluate a check is unavailable
    FAIL     a defined requirement is not satisfied

The overall status of a result is the most severe status of its checks.
"""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional

PASS = "PASS"
WARNING = "WARNING"
MISSING = "MISSING"
FAIL = "FAIL"

_SEVERITY = {PASS: 0, WARNING: 1, MISSING: 2, FAIL: 3}


class MissingDataError(ValueError):
    """Raised when a value that must never be assumed silently is not supplied."""

    def __init__(self, items: Iterable[str]):
        self.items: List[str] = list(items)
        super().__init__("Missing required input: " + "; ".join(self.items))


def worst_status(statuses: Iterable[str]) -> str:
    """Return the most severe status (PASS < WARNING < MISSING < FAIL)."""
    worst = PASS
    for status in statuses:
        if status not in _SEVERITY:
            raise ValueError(f"Unknown status: {status!r}")
        if _SEVERITY[status] > _SEVERITY[worst]:
            worst = status
    return worst


@dataclass
class Check:
    """A single engineering check with a status and a human-readable message."""

    name: str
    status: str
    message: str
    value: Any = None
    limit: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculation_record(
    name: str,
    equation: str,
    inputs: Dict[str, Any],
    result: Any,
    source: Optional[str] = None,
    status: str = "CALCULATED",
    notes: str = "",
) -> Dict[str, Any]:
    """One traceable step: input -> equation -> result -> source/assumption."""
    return {
        "calculation": name,
        "equation": equation,
        "inputs": inputs,
        "result": result,
        "source": source,
        "status": status,
        "notes": notes,
    }


class AuditLog:
    """Collects calculation records in the order they were produced."""

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []

    def add(
        self,
        name: str,
        equation: str,
        inputs: Dict[str, Any],
        result: Any,
        source: Optional[str] = None,
        status: str = "CALCULATED",
        notes: str = "",
    ) -> Dict[str, Any]:
        record = calculation_record(name, equation, inputs, result, source, status, notes)
        self.records.append(record)
        return record


def audit_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"number_of_records": len(records), "records": records}
