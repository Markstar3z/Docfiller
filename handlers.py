"""Telegram command and callback handlers."""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import messages
from queue_manager import ActiveJob, QueueJob, QueueManager

logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


class BotHandlers:
    def __init__(self, allowed_user_id: int, db, screenshot_dir: str) -> None:
        self.allowed_user_id = allowed_user_id
        self.db = db
        self.screenshot_dir = screenshot_dir

        self.queue_manager = QueueManager(db=db, callbacks=self, screenshot_dir=screenshot_dir)

        # token -> url, for duplicate URL confirmation callbacks
        self.pending_duplicate_urls: dict[str, str] = {}

    async def start_background(self) -> None:
        await self.queue_manager.start()

    def register(self, app: Application) -> None:
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("recent", self.cmd_recent))
        app.add_handler(CommandHandler("search", self.cmd_search))
        app.add_handler(CommandHandler("export", self.cmd_export))
        app.add_handler(CommandHandler("autosubmit", self.cmd_autosubmit))
        app.add_handler(CommandHandler("profile", self.cmd_profile))
        app.add_handler(CommandHandler("cancel", self.cmd_cancel))

        app.add_handler(CallbackQueryHandler(self.on_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text_message))

    def _is_allowed(self, update: Update) -> bool:
        user = update.effective_user
        return bool(user and user.id == self.allowed_user_id)

    @staticmethod
    def _mask_wallet(text: str) -> str:
        pattern = re.compile(r"\b0x[a-fA-F0-9]{16,}\b")

        def repl(match: re.Match) -> str:
            value = match.group(0)
            return f"{value[:6]}...{value[-4:]}"

        return pattern.sub(repl, text)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.effective_message.reply_text(messages.WELCOME)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.effective_message.reply_text(messages.HELP)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        status = self.queue_manager.current_status_text()
        await update.effective_message.reply_text(status)

    async def cmd_recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        rows = self.db.list_recent(10)
        if not rows:
            await update.effective_message.reply_text("No applications yet.")
            return

        lines = ["Recent applications"]
        for row in rows:
            lines.append(f"#{row['id']} {row['status']} | {row['date'][:19]} | {row['url']}")
        await update.effective_message.reply_text("\n".join(lines))

    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        if not context.args:
            await update.effective_message.reply_text(messages.SEARCH_USAGE)
            return

        q = " ".join(context.args).strip()
        rows = self.db.search_applications(q)
        if not rows:
            await update.effective_message.reply_text("No matches found.")
            return

        lines = [f"Found {len(rows)} match(es)"]
        for row in rows:
            lines.append(f"#{row['id']} {row['status']} | {row['date'][:19]} | {row['url']}")
        await update.effective_message.reply_text("\n".join(lines))

    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return

        rows = self.db.export_all()
        if not rows:
            await update.effective_message.reply_text(messages.EXPORT_EMPTY)
            return

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "url", "title", "status", "date", "answers_json", "screenshot_path"])
        for row in rows:
            writer.writerow([
                row["id"],
                row["url"],
                row["title"],
                row["status"],
                row["date"],
                row["answers_json"],
                row["screenshot_path"],
            ])

        data = output.getvalue().encode("utf-8")
        bio = io.BytesIO(data)
        bio.name = f"applications_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        await update.effective_message.reply_document(document=InputFile(bio))

    async def cmd_autosubmit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return

        if not context.args:
            await update.effective_message.reply_text(messages.AUTOSUBMIT_USAGE)
            return

        mode = context.args[0].strip().lower()
        if mode not in {"on", "off"}:
            await update.effective_message.reply_text(messages.AUTOSUBMIT_USAGE)
            return

        is_on = mode == "on"
        self.db.set_auto_submit(is_on)
        await update.effective_message.reply_text(messages.AUTO_ON_WARNING if is_on else messages.AUTO_OFF)

    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return

        profile = self.db.get_profile_fields()
        if not profile:
            text = f"{messages.PROFILE_HEADER}\nNo fields saved yet."
        else:
            lines = [messages.PROFILE_HEADER]
            for k, v in profile.items():
                shown = self._mask_wallet(v)
                lines.append(f"{k}: {shown}")
            text = "\n".join(lines)

        context.user_data["awaiting_profile_edit"] = True
        await update.effective_message.reply_text(f"{text}\n\n{messages.PROFILE_EDIT_PROMPT}")

    async def cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return

        ok = await self.queue_manager.cancel_current()
        if ok:
            await update.effective_message.reply_text(messages.CANCELLED)
        else:
            await update.effective_message.reply_text("Nothing active to cancel.")

    async def on_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return

        text = (update.effective_message.text or "").strip()

        # profile edit mode: field=value
        if context.user_data.get("awaiting_profile_edit") and "=" in text:
            key, value = [x.strip() for x in text.split("=", 1)]
            if key and value:
                self.db.set_profile_field(key, value)
                context.user_data["awaiting_profile_edit"] = False
                await update.effective_message.reply_text(messages.PROFILE_UPDATED)
                return

        pending_edit = context.user_data.get("awaiting_answer")
        if pending_edit:
            job_id = pending_edit["job_id"]
            field_label = pending_edit["field_label"]
            if text == "/skip":
                new_answer = ""
            else:
                if any(word in text.lower() for word in ["seed phrase", "private key"]):
                    await update.effective_message.reply_text("🚨 I won't save that. Never share private keys or seed phrases.")
                    return
                new_answer = text

            context.user_data.pop("awaiting_answer", None)
            await update.effective_message.reply_text(messages.UPDATED)
            active = await self.queue_manager.apply_answer_edit(job_id, field_label, new_answer)
            await self.send_preview(update.effective_chat.id, active)

            await self._continue_flagged_prompt_if_needed(update, context, job_id)
            return

        urls = URL_RE.findall(text)
        if not urls:
            return

        await update.effective_message.reply_text(messages.ON_IT)

        for url in urls:
            if self.db.application_exists(url):
                token = f"dup{len(self.pending_duplicate_urls)+1}_{abs(hash((url, datetime.utcnow().isoformat())))}"
                self.pending_duplicate_urls[token] = url
                kb = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("Continue", callback_data=f"dup_yes:{token}"),
                        InlineKeyboardButton("Skip", callback_data=f"dup_no:{token}"),
                    ]]
                )
                await update.effective_message.reply_text(messages.DUPLICATE_WARNING, reply_markup=kb)
                continue

            await self._enqueue_url(update, url)

    async def _enqueue_url(self, update: Update, url: str) -> None:
        qjob = QueueJob(url=url, chat_id=update.effective_chat.id)
        position = await self.queue_manager.enqueue(qjob)
        if self.queue_manager.current_queue_job is None and position == 1:
            await update.effective_message.reply_text(messages.QUEUE_RUNNING)
        else:
            await update.effective_message.reply_text(messages.QUEUE_WAIT.format(position=position))

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return

        q = update.callback_query
        await q.answer()
        data = q.data or ""

        if data.startswith("dup_yes:"):
            token = data.split(":", 1)[1]
            url = self.pending_duplicate_urls.pop(token, None)
            if url:
                fake_update = update
                fake_update.callback_query = None
                await self._enqueue_url(update, url)
            await q.edit_message_text("Okay, continuing with that URL.")
            return

        if data.startswith("dup_no:"):
            token = data.split(":", 1)[1]
            self.pending_duplicate_urls.pop(token, None)
            await q.edit_message_text("Skipped that URL.")
            return

        if data.startswith("submit:"):
            job_id = data.split(":", 1)[1]
            active = self.queue_manager.get_active_job(job_id)
            if not active:
                await q.edit_message_text("This job is no longer active.")
                return

            if active.prepare_result.flagged_field_labels:
                kb = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("Fill flagged", callback_data=f"fillflag:{job_id}"),
                        InlineKeyboardButton("Submit anyway", callback_data=f"submitany:{job_id}"),
                    ]]
                )
                await q.message.reply_text("There are flagged fields. Fix them first or submit anyway?", reply_markup=kb)
                return

            await self._submit_job(q.message.chat_id, job_id)
            return

        if data.startswith("submitany:"):
            job_id = data.split(":", 1)[1]
            await self._submit_job(q.message.chat_id, job_id)
            return

        if data.startswith("edit:"):
            job_id = data.split(":", 1)[1]
            active = self.queue_manager.get_active_job(job_id)
            if not active:
                await q.message.reply_text("This job is no longer active.")
                return

            buttons = []
            for idx, f in enumerate(active.prepare_result.fields):
                buttons.append([InlineKeyboardButton(f.label[:40], callback_data=f"pick:{job_id}:{idx}")])
            kb = InlineKeyboardMarkup(buttons[:80])
            await q.message.reply_text(messages.ASK_EDIT_FIELD, reply_markup=kb)
            return

        if data.startswith("pick:"):
            _, job_id, idx_text = data.split(":", 2)
            active = self.queue_manager.get_active_job(job_id)
            if not active:
                await q.message.reply_text("This job is no longer active.")
                return
            idx = int(idx_text)
            field = active.prepare_result.fields[idx]
            context.user_data["awaiting_answer"] = {"job_id": job_id, "field_label": field.label}
            await q.message.reply_text(messages.ASK_NEW_ANSWER.format(field=field.label))
            return

        if data.startswith("fillflag:"):
            job_id = data.split(":", 1)[1]
            await self._start_flagged_prompt(update, context, job_id)
            return

        if data.startswith("cancel:"):
            job_id = data.split(":", 1)[1]
            ok = await self.queue_manager.cancel(job_id)
            await q.message.reply_text(messages.CANCELLED if ok else "This job already ended.")
            return

        if data.startswith("retry:"):
            job_id = data.split(":", 1)[1]
            await self._submit_job(q.message.chat_id, job_id)
            return

        if data.startswith("captcha_done:"):
            job_id = data.split(":", 1)[1]
            ok = await self.queue_manager.resume_captcha(job_id)
            if ok:
                await q.message.reply_text("Nice, continuing now.")
            else:
                await q.message.reply_text("Captcha session was already closed.")

    async def _submit_job(self, chat_id: int, job_id: str) -> None:
        active = self.queue_manager.get_active_job(job_id)
        if not active:
            return

        await self._send_chat_text(chat_id, messages.SUBMITTING)
        active, result = await self.queue_manager.submit(job_id)

        if result.success:
            if result.proof_screenshot_path:
                await self._send_chat_photo(chat_id, result.proof_screenshot_path, messages.SUBMIT_SUCCESS)
            else:
                await self._send_chat_text(chat_id, messages.SUBMIT_SUCCESS)
        else:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Retry", callback_data=f"retry:{job_id}")]])
            await self._send_chat_text(
                chat_id,
                messages.SUBMIT_FAILED.format(error=result.message),
                reply_markup=kb,
            )

    async def send_preview(self, chat_id: int, active: ActiveJob) -> None:
        result = active.prepare_result

        caption = f"{messages.PREVIEW_HEADER}\n{result.form_title}\n{result.url}"
        if result.screenshot_path:
            await self._send_chat_photo(chat_id, result.screenshot_path, caption)
        else:
            await self._send_chat_text(chat_id, caption)

        chunks = self._format_preview_chunks(result)
        for chunk in chunks:
            await self._send_chat_text(chat_id, chunk)

        buttons = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Submit", callback_data=f"submit:{result.job_id}"),
                InlineKeyboardButton("Edit", callback_data=f"edit:{result.job_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{result.job_id}"),
            ]]
        )
        await self._send_chat_text(chat_id, "What next?", reply_markup=buttons)

    def _format_preview_chunks(self, result) -> list[str]:
        lines = []
        if result.flagged_field_labels:
            lines.append(messages.FLAGGED_HEADER)
            for f in result.flagged_field_labels:
                lines.append(f"• {f}")
            lines.append("")
        else:
            lines.append(messages.NO_FLAGGED)
            lines.append("")

        lines.append("Answers")
        for field in result.fields:
            answer = field.answer if field.answer else "(empty)"
            lines.append(f"• {field.label}: {answer} [{field.status}]")

        max_len = 3300
        chunks: list[str] = []
        current = ""
        for line in lines:
            next_line = f"{line}\n"
            if len(current) + len(next_line) > max_len:
                chunks.append(current.strip())
                current = next_line
            else:
                current += next_line
        if current.strip():
            chunks.append(current.strip())
        return chunks

    async def _start_flagged_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str) -> None:
        active = self.queue_manager.get_active_job(job_id)
        if not active:
            return

        flagged = [f for f in active.prepare_result.fields if f.status == "flagged"]
        if not flagged:
            await update.effective_chat.send_message("No flagged fields left.")
            return

        queue = [f.label for f in flagged]
        context.user_data["flagged_queue"] = {"job_id": job_id, "labels": queue}
        await self._continue_flagged_prompt_if_needed(update, context, job_id)

    async def _continue_flagged_prompt_if_needed(self, update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str) -> None:
        flag_state = context.user_data.get("flagged_queue")
        if not flag_state or flag_state.get("job_id") != job_id:
            return

        labels = flag_state.get("labels", [])
        active = self.queue_manager.get_active_job(job_id)
        if not active:
            context.user_data.pop("flagged_queue", None)
            return

        while labels:
            label = labels[0]
            field = next((f for f in active.prepare_result.fields if f.label == label), None)
            if not field or field.status != "flagged":
                labels.pop(0)
                continue

            context.user_data["awaiting_answer"] = {"job_id": job_id, "field_label": label}
            hint = "You can send /skip" if field.optional else "Please reply with text"
            await update.effective_chat.send_message(f"Flagged field: {label}\n{hint}")
            return

        context.user_data.pop("flagged_queue", None)
        await update.effective_chat.send_message("Great, all flagged fields are handled.")
        active = self.queue_manager.get_active_job(job_id)
        if active:
            await self.send_preview(update.effective_chat.id, active)

    async def _send_chat_text(self, chat_id: int, text: str, **kwargs) -> None:
        app = self.callbacks_app
        await app.bot.send_message(chat_id=chat_id, text=text, **kwargs)

    async def _send_chat_photo(self, chat_id: int, photo_path: str, caption: str, **kwargs) -> None:
        app = self.callbacks_app
        try:
            with open(photo_path, "rb") as photo:
                await app.bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, **kwargs)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("send_photo failed, falling back to document: %s", self._mask_wallet(str(exc)))

        # Fallback so preview flow doesn't crash if Telegram rejects photo format/size.
        try:
            with open(photo_path, "rb") as f:
                filename = os.path.basename(photo_path) or "screenshot.png"
                await app.bot.send_document(
                    chat_id=chat_id,
                    document=InputFile(f, filename=filename),
                    caption=caption,
                    **kwargs,
                )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("send_document fallback failed: %s", self._mask_wallet(str(exc)))

        # Final safety net: never crash the job because media failed to send.
        await app.bot.send_message(chat_id=chat_id, text=f"{caption}\n\nI couldn't send the screenshot, but the job is still active.")

    # The application object is injected from main.py after Application creation.
    callbacks_app: Application

    # Queue callbacks below -------------------------------------------------
    async def on_job_started(self, job: QueueJob) -> None:
        await self._send_chat_text(job.chat_id, f"Starting now: {job.url}")

    async def on_preview_ready(self, active: ActiveJob) -> None:
        await self.send_preview(active.chat_id, active)

        if self.db.get_auto_submit() and not active.prepare_result.flagged_field_labels:
            await self._submit_job(active.chat_id, active.prepare_result.job_id)

    async def on_captcha_needed(self, active: ActiveJob) -> None:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Done", callback_data=f"captcha_done:{active.prepare_result.job_id}")]]
        )
        if active.prepare_result.screenshot_path:
            await self._send_chat_photo(
                active.chat_id,
                active.prepare_result.screenshot_path,
                messages.CAPTCHA_NEEDED,
                reply_markup=kb,
            )
        else:
            await self._send_chat_text(active.chat_id, messages.CAPTCHA_NEEDED, reply_markup=kb)

    async def on_login_needed(self, active: ActiveJob) -> None:
        site = active.prepare_result.warning_detail or "the target site"
        await self._send_chat_text(active.chat_id, messages.LOGIN_NEEDED.format(site=site))

    async def on_wallet_needed(self, active: ActiveJob) -> None:
        await self._send_chat_text(active.chat_id, messages.WALLET_NEEDED)

    async def on_timeout(self, active: ActiveJob) -> None:
        await self._send_chat_text(active.chat_id, messages.TIMEOUT_WARNING)

    async def on_scam_warning(self, active: ActiveJob) -> None:
        detail = active.prepare_result.warning_detail or "unknown"
        await self._send_chat_text(active.chat_id, messages.SCAM_WARNING.format(detail=detail))

    async def on_job_crash(self, job: QueueJob, exc: Exception, stage: str = "unknown") -> None:
        raw = str(exc) or exc.__class__.__name__
        safe_msg = self._mask_wallet(raw)
        logger.exception("Job crashed at stage=%s for URL %s: %s", stage, job.url, safe_msg)

        # Keep this short and human, but useful.
        short = safe_msg.strip().replace("\n", " ")[:220]
        await self._send_chat_text(
            job.chat_id,
            f"{messages.CRASH_WARNING}\nWhere: {stage}\nReason: {short}",
        )
