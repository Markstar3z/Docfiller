"""Engine adapter layer.

The Telegram bot must only call these functions:
- prepare_form(url)
- update_answer(job_id, field_label, new_answer)
- submit_form(job_id)
- cancel_job(job_id)

These are placeholder implementations so you can test full bot flow first.
Replace internals later with your real Playwright engine calls.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import base64
import os
import uuid
from typing import Optional


@dataclass
class FieldResult:
    label: str
    answer: str
    status: str  # filled | flagged | skipped
    optional: bool = False


@dataclass
class PrepareResult:
    job_id: str
    url: str
    form_title: str
    fields: list[FieldResult]
    flagged_field_labels: list[str]
    screenshot_path: Optional[str]
    warning: Optional[str] = None  # captcha_found | login_needed | wallet_connect_needed | scam_warning | timeout
    warning_detail: Optional[str] = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["fields"] = [asdict(f) for f in self.fields]
        return payload


@dataclass
class SubmitResult:
    success: bool
    message: str
    proof_screenshot_path: Optional[str]


_ACTIVE_JOBS: dict[str, PrepareResult] = {}


def _ensure_demo_screenshot(path: str) -> None:
    """Write a tiny valid PNG so Telegram can send a photo in dry runs."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tiny_png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        "/w8AAn8B9pNr8v8AAAAASUVORK5CYII="
    )
    with open(path, "wb") as f:
        f.write(base64.b64decode(tiny_png_base64))


def _demo_fields_for_url(url: str) -> list[FieldResult]:
    """Simple deterministic placeholder answers."""
    fields = [
        FieldResult("Name", "Satoshi Builder", "filled"),
        FieldResult("Email", "builder@example.com", "filled"),
        FieldResult("Telegram", "@yourhandle", "filled"),
        FieldResult("Wallet Address", "0x1234...ABCD", "filled"),
        FieldResult("Why do you want to join?", "I build useful crypto tools.", "filled"),
    ]

    lower_url = url.lower()
    if "long" in lower_url:
        for i in range(1, 20):
            fields.append(FieldResult(f"Extra Question {i}", f"Sample answer {i}", "filled"))

    if "flag" in lower_url:
        fields.append(FieldResult("Twitter profile", "", "flagged"))
        fields.append(FieldResult("Country", "", "flagged", optional=True))

    return fields


def _scan_scam_signals(fields: list[FieldResult]) -> Optional[str]:
    bad_markers = ["seed phrase", "private key", "secret phrase", "recovery phrase", "send payment"]
    for field in fields:
        label = field.label.lower()
        if any(marker in label for marker in bad_markers):
            return field.label
    return None


def prepare_form(url: str, screenshot_dir: str = "./screenshots") -> PrepareResult:
    """Open form, fill, and return preview result.

    Placeholder behavior:
    - Creates demo fields
    - Emits warning based on URL keywords
    """
    job_id = str(uuid.uuid4())
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    screenshot_path = os.path.join(screenshot_dir, f"preview_{ts}_{job_id[:8]}.png")
    _ensure_demo_screenshot(screenshot_path)

    fields = _demo_fields_for_url(url)
    flagged = [f.label for f in fields if f.status == "flagged"]

    warning = None
    warning_detail = None
    lower = url.lower()

    if "captcha" in lower:
        warning = "captcha_found"
    elif "login" in lower:
        warning = "login_needed"
        warning_detail = url.split("/")[2] if "/" in url else "the target site"
    elif "wallet" in lower:
        warning = "wallet_connect_needed"
    elif "timeout" in lower:
        warning = "timeout"

    scam_label = _scan_scam_signals(fields)
    if scam_label:
        warning = "scam_warning"
        warning_detail = scam_label

    result = PrepareResult(
        job_id=job_id,
        url=url,
        form_title="Demo Application Form",
        fields=fields,
        flagged_field_labels=flagged,
        screenshot_path=screenshot_path,
        warning=warning,
        warning_detail=warning_detail,
    )
    _ACTIVE_JOBS[job_id] = result
    return result


def update_answer(job_id: str, field_label: str, new_answer: str) -> PrepareResult:
    """Update one answer and return refreshed preview object."""
    if job_id not in _ACTIVE_JOBS:
        raise ValueError("Job not found")

    result = _ACTIVE_JOBS[job_id]
    found = False
    for field in result.fields:
        if field.label == field_label:
            field.answer = new_answer
            field.status = "filled" if new_answer.strip() else "skipped"
            found = True
            break

    if not found:
        raise ValueError(f"Field not found: {field_label}")

    result.flagged_field_labels = [f.label for f in result.fields if f.status == "flagged"]
    return result


def submit_form(job_id: str, screenshot_dir: str = "./screenshots") -> SubmitResult:
    """Submit form and return success/failure + proof screenshot path."""
    if job_id not in _ACTIVE_JOBS:
        return SubmitResult(False, "Job not found or already closed", None)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    proof_path = os.path.join(screenshot_dir, f"proof_{ts}_{job_id[:8]}.png")
    _ensure_demo_screenshot(proof_path)
    return SubmitResult(True, "Submission completed", proof_path)


def cancel_job(job_id: str) -> bool:
    """Close browser/cleanup for a job."""
    if job_id in _ACTIVE_JOBS:
        del _ACTIVE_JOBS[job_id]
        return True
    return False
