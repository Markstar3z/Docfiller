"""Centralized bot message text.
Edit wording here without touching logic files.
"""

WELCOME = (
    "Hey, I’m your form helper 🤝\n"
    "Send one or more form links and I’ll prep answers, show preview, and wait for your tap before submit.\n"
    "Use /help to see quick commands."
)

HELP = (
    "Commands:\n"
    "/start - Welcome\n"
    "/status - Current job and queue\n"
    "/recent - Last 10 applications\n"
    "/search <word> - Search past applications\n"
    "/export - Download CSV of all applications\n"
    "/autosubmit on|off - Toggle auto submit\n"
    "/profile - View and edit profile fields\n"
    "/cancel - Cancel current job\n"
    "/help - Show this list"
)

ON_IT = "Got it, working on this one ⚡"
QUEUE_WAIT = "Added to queue. You’re number {position}."
QUEUE_RUNNING = "You’re up now. Preparing the form preview."
DUPLICATE_WARNING = "You already applied to this URL before. Continue anyway?"

PREVIEW_HEADER = "Preview ready ✅"
FLAGGED_HEADER = "⚠️ Flagged fields"
NO_FLAGGED = "No flagged fields"

ASK_EDIT_FIELD = "Pick a field to edit"
ASK_NEW_ANSWER = "Send the new answer for: {field}"
UPDATED = "Updated. Refreshing preview now."
CANCELLED = "Done, I cancelled this job."

SUBMITTING = "Submitting now 🚀"
SUBMIT_SUCCESS = "Submitted successfully ✅"
SUBMIT_FAILED = "Submit failed: {error}"

CAPTCHA_NEEDED = "Captcha needs your help. Solve it, then tap Done."
LOGIN_NEEDED = "Login is needed for {site}. Refresh your saved session, then retry."
WALLET_NEEDED = "This one needs wallet connect, so I marked it manual."
SCAM_WARNING = "🚨 Stopped for safety. Suspicious field detected: {detail}"
TIMEOUT_WARNING = "Something timed out. I paused this job so nothing is lost."
CRASH_WARNING = "The job crashed unexpectedly. I saved details and paused safely."

AUTO_ON_WARNING = "Auto submit is now ON ⚠️ I’ll submit right after preview unless blocked by flags."
AUTO_OFF = "Auto submit is now OFF. I’ll always wait for your tap."

PROFILE_HEADER = "Saved profile fields"
PROFILE_EDIT_PROMPT = "Reply with: field=value\nExample: twitter=@myhandle"
PROFILE_UPDATED = "Profile saved."

ONLY_YOU = ""

EXPORT_EMPTY = "No applications yet, so there’s nothing to export."
STATUS_IDLE = "No active job right now. Queue is empty."
SEARCH_USAGE = "Use: /search your_word"
AUTOSUBMIT_USAGE = "Use: /autosubmit on or /autosubmit off"
