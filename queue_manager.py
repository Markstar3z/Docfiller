"""Queue and job manager.
Runs one form job at a time and notifies handler callbacks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from engine_adapter import (
    PrepareResult,
    SubmitResult,
    cancel_job,
    prepare_form,
    submit_form,
    update_answer,
)


@dataclass
class QueueJob:
    url: str
    chat_id: int
    requested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ActiveJob:
    url: str
    chat_id: int
    prepare_result: PrepareResult
    application_id: int
    captcha_wait_event: Optional[asyncio.Event] = None


class QueueManager:
    def __init__(self, db, callbacks, screenshot_dir: str) -> None:
        self.db = db
        self.callbacks = callbacks
        self.screenshot_dir = screenshot_dir

        self.queue: asyncio.Queue[QueueJob] = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.current_queue_job: Optional[QueueJob] = None
        self.active_jobs: dict[str, ActiveJob] = {}

    async def start(self) -> None:
        if not self.worker_task or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker(), name="form-job-worker")

    async def enqueue(self, job: QueueJob) -> int:
        await self.queue.put(job)
        return self.queue.qsize()

    def queue_size(self) -> int:
        return self.queue.qsize()

    def current_status_text(self) -> str:
        if self.current_queue_job:
            return f"Running: {self.current_queue_job.url}\nQueue: {self.queue.qsize()} waiting"
        return "No active job right now. Queue is empty."

    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            self.current_queue_job = job
            try:
                await self.callbacks.on_job_started(job)

                result = await asyncio.to_thread(prepare_form, job.url, self.screenshot_dir)
                app_id = self.db.save_application(
                    url=result.url,
                    title=result.form_title,
                    status="prepared",
                    answers=[f.__dict__ for f in result.fields],
                    screenshot_path=result.screenshot_path,
                )

                active = ActiveJob(url=job.url, chat_id=job.chat_id, prepare_result=result, application_id=app_id)
                self.active_jobs[result.job_id] = active

                if result.warning == "scam_warning":
                    self.db.update_application_status(app_id, "blocked_scam")
                    await self.callbacks.on_scam_warning(active)
                    continue

                if result.warning == "login_needed":
                    self.db.update_application_status(app_id, "login_needed")
                    await self.callbacks.on_login_needed(active)
                    continue

                if result.warning == "wallet_connect_needed":
                    self.db.update_application_status(app_id, "manual_wallet_connect")
                    await self.callbacks.on_wallet_needed(active)
                    continue

                if result.warning == "timeout":
                    self.db.update_application_status(app_id, "timeout")
                    await self.callbacks.on_timeout(active)
                    continue

                if result.warning == "captcha_found":
                    event = asyncio.Event()
                    active.captcha_wait_event = event
                    await self.callbacks.on_captcha_needed(active)
                    await event.wait()

                await self.callbacks.on_preview_ready(active)

            except Exception as exc:  # noqa: BLE001
                await self.callbacks.on_job_crash(job, exc)
            finally:
                self.current_queue_job = None
                self.queue.task_done()

    def get_active_job(self, job_id: str) -> Optional[ActiveJob]:
        return self.active_jobs.get(job_id)

    async def resume_captcha(self, job_id: str) -> bool:
        active = self.active_jobs.get(job_id)
        if not active or not active.captcha_wait_event:
            return False
        active.captcha_wait_event.set()
        active.captcha_wait_event = None
        return True

    async def apply_answer_edit(self, job_id: str, field_label: str, new_answer: str) -> ActiveJob:
        active = self.active_jobs[job_id]
        updated = await asyncio.to_thread(update_answer, job_id, field_label, new_answer)
        active.prepare_result = updated

        self.db.save_application(
            url=updated.url,
            title=updated.form_title,
            status="edited",
            answers=[f.__dict__ for f in updated.fields],
            screenshot_path=updated.screenshot_path,
        )
        self.db.cache_answer(field_label, new_answer)
        return active

    async def submit(self, job_id: str) -> tuple[ActiveJob, SubmitResult]:
        active = self.active_jobs[job_id]
        result = await asyncio.to_thread(submit_form, job_id, self.screenshot_dir)

        if result.success:
            self.db.update_application_status(active.application_id, "submitted", result.proof_screenshot_path)
        else:
            self.db.update_application_status(active.application_id, "submit_failed")

        return active, result

    async def retry_submit(self, job_id: str) -> tuple[ActiveJob, SubmitResult]:
        return await self.submit(job_id)

    async def cancel(self, job_id: str) -> bool:
        active = self.active_jobs.get(job_id)
        if not active:
            return False

        ok = await asyncio.to_thread(cancel_job, job_id)
        self.db.update_application_status(active.application_id, "cancelled")
        self.active_jobs.pop(job_id, None)
        return ok

    async def cancel_current(self) -> bool:
        if not self.current_queue_job:
            return False

        for jid, active in list(self.active_jobs.items()):
            if active.url == self.current_queue_job.url and active.chat_id == self.current_queue_job.chat_id:
                await self.cancel(jid)
                return True

        return False
