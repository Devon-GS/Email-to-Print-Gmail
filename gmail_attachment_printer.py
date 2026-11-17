from __future__ import annotations

import base64
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
SETTINGS_FILE = BASE_DIR / "settings.json"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx"}
CHECK_OPTIONS: dict[str, int] = {
    "Disabled (never checks)": 0,
    "60 sec": 60,
    "5 min": 300,
    "10 min": 600,
    "20 min": 1200,
    "30 min": 1800,
    "1 hour": 3600,
    "2 hours": 7200,
    "5 hours": 18000,
    "10 hours": 36000,
}
OS_OPTIONS = ("Windows", "macOS", "Linux")
DEFAULT_SETTINGS = {"operating_system": "Windows", "check_interval": "Disabled (never checks)"}
LOG = logging.getLogger("gmail_attachment_printer")


class QueueLogHandler(logging.Handler):
    """Copies log records to the GUI without making worker threads touch Tk."""

    def __init__(self, messages: queue.Queue[str]) -> None:
        super().__init__()
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.put_nowait(self.format(record))
        except Exception:
            self.handleError(record)


def load_settings() -> dict[str, str]:
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        result = DEFAULT_SETTINGS.copy()
        if raw.get("operating_system") in OS_OPTIONS:
            result["operating_system"] = raw["operating_system"]
        if raw.get("check_interval") in CHECK_OPTIONS:
            result["check_interval"] = raw["check_interval"]
        return result
    except (OSError, json.JSONDecodeError, AttributeError):
        LOG.warning("Could not read settings.json; using defaults.")
        return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict[str, str]) -> None:
    temporary = SETTINGS_FILE.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(settings, file, indent=2)
            file.write("\n")
        os.replace(temporary, SETTINGS_FILE)
    except OSError:
        LOG.exception("Could not save settings to %s", SETTINGS_FILE)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def gmail_service() -> Any:
    """Load, refresh, or create the OAuth credentials and Gmail service."""
    if not CREDENTIALS_FILE.is_file():
        raise FileNotFoundError(f"Missing {CREDENTIALS_FILE}. Download it from Google Cloud.")

    credentials: Credentials | None = None
    if TOKEN_FILE.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except (ValueError, OSError):
            LOG.warning("token.json is invalid; starting OAuth authorization again.")

    if credentials and credentials.expired and credentials.refresh_token:
        LOG.info("Refreshing Gmail OAuth token...")
        credentials.refresh(Request())
    elif not credentials or not credentials.valid:
        LOG.info("Opening the browser for Gmail authorization...")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def header(message: dict[str, Any], name: str, default: str = "(unknown)") -> str:
    for item in message.get("payload", {}).get("headers", []):
        if item.get("name", "").lower() == name.lower():
            return item.get("value", default)
    return default


def iter_parts(part: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield part
    for child in part.get("parts", []) or []:
        yield from iter_parts(child)


def decode_attachment(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def safe_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in ALLOWED_EXTENSIONS else ".bin"


def print_file(path: Path, selected_os: str) -> None:
    """Send a file to the selected OS's default printer and raise on failure."""
    if selected_os == "Windows":
        if not hasattr(os, "startfile"):
            raise RuntimeError("Windows printing is unavailable on this platform.")
        os.startfile(str(path), "print")  # type: ignore[attr-defined]
        return

    lp = shutil.which("lp")
    if not lp:
        raise FileNotFoundError("The 'lp' command was not found. Install/configure CUPS.")
    completed = subprocess.run(
        [lp, str(path)], capture_output=True, text=True, timeout=120, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"lp failed ({completed.returncode}): {detail or 'unknown error'}")


class GmailPrinter:
    def __init__(self, log: logging.Logger) -> None:
        self.log = log

    def check_once(self, selected_os: str) -> None:
        service = gmail_service()
        page_token: str | None = None
        found = 0
        printed = 0
        while True:
            response = service.users().messages().list(
                userId="me", q="is:unread has:attachment", pageToken=page_token, maxResults=100
            ).execute()
            for item in response.get("messages", []):
                found += 1
                if self._process_message(service, item["id"], selected_os):
                    printed += 1
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        self.log.info("Check complete: %d unread message(s), %d marked read.", found, printed)

    def _process_message(self, service: Any, message_id: str, selected_os: str) -> bool:
        message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        sender = header(message, "From")
        subject = header(message, "Subject")
        self.log.info("Found email from %s: %s", sender, subject)
        parts = [part for part in iter_parts(message.get("payload", {})) if part.get("filename")]
        eligible = [part for part in parts if Path(part["filename"]).suffix.lower() in ALLOWED_EXTENSIONS]
        if not eligible:
            self.log.info("No allowed attachments in message %s; leaving it unread.", message_id)
            return False

        temporary_files: list[Path] = []
        try:
            for part in eligible:
                filename = part["filename"]
                body = part.get("body", {})
                data = body.get("data")
                if not data and body.get("attachmentId"):
                    attachment = service.users().messages().attachments().get(
                        userId="me", messageId=message_id, id=body["attachmentId"]
                    ).execute()
                    data = attachment.get("data")
                if not data:
                    raise ValueError(f"Attachment data is missing for {filename}")
                decoded = decode_attachment(data)
                handle, raw_path = tempfile.mkstemp(prefix="gmail-print-", suffix=safe_suffix(filename))
                os.close(handle)
                path = Path(raw_path)
                path.write_bytes(decoded)
                temporary_files.append(path)
                self.log.info("Printing attachment: %s", filename)
                print_file(path, selected_os)

            service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            self.log.info("Marked email as read: %s", subject)
            return True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            self.log.error("Could not process '%s': %s. The email remains unread.", subject, error)
            return False
        finally:
            for path in temporary_files:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    self.log.warning("Could not delete temporary file %s", path)


class Application(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Gmail Attachment Printer")
        self.minsize(680, 430)
        self.settings = load_settings()
        self.log_messages: queue.Queue[str] = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gmail-check")
        self.check_lock = threading.Lock()
        self.active_future: Future[None] | None = None
        self.next_auto_check = time.monotonic()
        self.closed = False
        self._build_ui()
        self._configure_logging()
        self.after(100, self._drain_logs)
        self.after(1000, self._timer_tick)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._log_startup()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(frame, text="Operating system:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.os_var = tk.StringVar(value=self.settings["operating_system"])
        os_menu = ttk.Combobox(frame, textvariable=self.os_var, values=OS_OPTIONS, state="readonly", width=18)
        os_menu.grid(row=0, column=1, sticky="w", pady=4)
        os_menu.bind("<<ComboboxSelected>>", self._settings_changed)

        ttk.Label(frame, text="Automatic check interval:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.interval_var = tk.StringVar(value=self.settings["check_interval"])
        interval_menu = ttk.Combobox(
            frame, textvariable=self.interval_var, values=list(CHECK_OPTIONS), state="readonly", width=24
        )
        interval_menu.grid(row=1, column=1, sticky="w", pady=4)
        interval_menu.bind("<<ComboboxSelected>>", self._settings_changed)

        ttk.Label(frame, text="Allowed files: " + ", ".join(sorted(ALLOWED_EXTENSIONS))).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 8)
        )
        self.log_text = tk.Text(frame, state="disabled", wrap="word", height=15)
        self.log_text.grid(row=3, column=0, columnspan=2, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=3, column=2, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.check_button = ttk.Button(frame, text="Check Gmail now", command=self.manual_check)
        self.check_button.grid(row=4, column=0, columnspan=3, pady=(12, 0), ipadx=10, ipady=4)

    def _configure_logging(self) -> None:
        handler = QueueLogHandler(self.log_messages)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
        LOG.setLevel(logging.INFO)
        LOG.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOG.addHandler(console)

    def _log_startup(self) -> None:
        LOG.info("Ready. Select an interval or use 'Check Gmail now'.")
        if not CREDENTIALS_FILE.is_file():
            LOG.warning("credentials.json is missing; add it beside this script before checking Gmail.")

    def _settings_changed(self, _event: object = None) -> None:
        self.settings = {"operating_system": self.os_var.get(), "check_interval": self.interval_var.get()}
        save_settings(self.settings)
        self.next_auto_check = time.monotonic() + CHECK_OPTIONS[self.interval_var.get()]
        LOG.info("Settings saved: %s, %s", self.os_var.get(), self.interval_var.get())

    def _timer_tick(self) -> None:
        if not self.closed:
            interval = CHECK_OPTIONS[self.interval_var.get()]
            if interval and time.monotonic() >= self.next_auto_check:
                self.start_check("automatic")
                self.next_auto_check = time.monotonic() + interval
            self.after(1000, self._timer_tick)

    def start_check(self, source: str) -> None:
        if not self.check_lock.acquire(blocking=False):
            LOG.info("%s check skipped because another check is already running.", source.capitalize())
            return
        selected_os = self.os_var.get()
        LOG.info("Starting %s Gmail check...", source)
        self.check_button.configure(state="disabled")
        self.active_future = self.executor.submit(self._run_check, selected_os)
        self.active_future.add_done_callback(self._check_finished)

    def _run_check(self, selected_os: str) -> None:
        try:
            GmailPrinter(LOG).check_once(selected_os)
        except Exception:
            LOG.exception("Gmail check failed.")

    def _check_finished(self, _future: Future[None]) -> None:
        self.check_lock.release()
        if not self.closed:
            self.after(0, lambda: self.check_button.configure(state="normal"))

    def manual_check(self) -> None:
        self.start_check("manual")

    def _drain_logs(self) -> None:
        try:
            while True:
                line = self.log_messages.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        if not self.closed:
            self.after(100, self._drain_logs)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        LOG.info("Closing; waiting for the current check to finish...")
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.destroy()


def main() -> None:
    # Avoid duplicate handlers when a caller embeds and reloads this module.
    Application().mainloop()


if __name__ == "__main__":
    main()
