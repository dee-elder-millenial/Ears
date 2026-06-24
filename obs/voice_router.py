from __future__ import annotations

import argparse
import json
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EARS_DIR = Path("/cloud-mirror/Ears")
TRANSCRIPTS = EARS_DIR / "transcripts"
COMMANDS = EARS_DIR / "commands"
MESSAGES_JSONL = TRANSCRIPTS / "messages.jsonl"
APPROVED_JSONL = COMMANDS / "approved.jsonl"
HISTORY_JSONL = COMMANDS / "history.jsonl"
STATUS_JSON = COMMANDS / "status.json"

POLL_SECONDS = 0.5
CAPTURE_IDLE_SECONDS = 3.0
CONFIRMATION_TIMEOUT_SECONDS = 30.0
COOLDOWN_SECONDS = 3.0

WAKE_RE = re.compile(r"\brobot\b[:,]?\s*(.*)", re.IGNORECASE)
YES_RE = re.compile(r"\b(yes|yeah|yep|yes do it|confirm|confirmed|go ahead|do it|approved|approve|please do|that's right|that is right)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(no|nope|cancel|stop|do not|don't|deny|denied|wrong|not right)\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def write_status(record: dict[str, Any]) -> None:
    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(json.dumps(record, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def safe_read_json(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def normalize_for_confirmation(text: str) -> str:
    text = clean_text(text)
    return text[:1].lower() + text[1:] if text else text


def approval_kind(text: str) -> str | None:
    normalized = clean_text(text).lower().strip(" .,!?:;")
    if YES_RE.search(normalized):
        return "approved"
    if NO_RE.search(normalized):
        return "denied"
    return None


def extract_wake_command(text: str) -> str | None:
    match = WAKE_RE.search(text)
    if not match:
        return None
    command = clean_text(match.group(1))
    command = re.sub(r"^(robot\b[:,]?\s*)+", "", command, flags=re.IGNORECASE)
    return clean_text(command)


def command_id(counter: int) -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{counter:03d}"


@dataclass
class PendingCommand:
    id: str
    raw_parts: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now)
    last_activity_monotonic: float = field(default_factory=time.monotonic)
    confirmation_text: str = ""

    @property
    def raw_text(self) -> str:
        return clean_text(" ".join(self.raw_parts))

    @property
    def interpreted_text(self) -> str:
        return normalize_for_confirmation(self.raw_text)


class VoiceRouter:
    def __init__(self, from_start: bool) -> None:
        COMMANDS.mkdir(parents=True, exist_ok=True)
        TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
        self.stop = False
        self.state = "idle"
        self.pending: PendingCommand | None = None
        self.counter = 0
        self.cooldown_until = 0.0
        self.offset = 0 if from_start else self.current_message_size()

    def current_message_size(self) -> int:
        return MESSAGES_JSONL.stat().st_size if MESSAGES_JSONL.exists() else 0

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.handle_stop)
        signal.signal(signal.SIGINT, self.handle_stop)
        self.set_status("idle")
        print("voice router ready; say 'Robot' followed by a command", flush=True)

        while not self.stop:
            self.tick_timeouts()
            for record in self.read_new_records():
                self.handle_record(record)
            time.sleep(POLL_SECONDS)

        self.set_status("stopped")
        print("voice router stopped", flush=True)

    def handle_stop(self, *_args: Any) -> None:
        self.stop = True

    def read_new_records(self) -> list[dict[str, Any]]:
        if not MESSAGES_JSONL.exists():
            return []
        size = MESSAGES_JSONL.stat().st_size
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return []

        records: list[dict[str, Any]] = []
        with MESSAGES_JSONL.open("r", encoding="utf-8") as handle:
            handle.seek(self.offset)
            for line in handle:
                record = safe_read_json(line)
                if record:
                    records.append(record)
            self.offset = handle.tell()
        return records

    def handle_record(self, record: dict[str, Any]) -> None:
        text = clean_text(str(record.get("text") or ""))
        source_file = str(record.get("file") or "")
        if time.monotonic() < self.cooldown_until:
            return

        if self.state == "idle":
            command = extract_wake_command(text)
            if command is None:
                return
            self.begin_command(command, source_file)
            return

        if self.state == "capturing_command":
            if not text:
                self.request_confirmation()
                return
            command = extract_wake_command(text)
            self.add_command_text(command if command is not None else text, source_file)
            return

        if self.state == "awaiting_confirmation":
            if not text:
                return
            decision = approval_kind(text)
            if decision == "approved":
                self.approve_command(text, source_file)
                return
            if decision == "denied":
                self.deny_command(text, source_file)
                return
            self.repeat_confirmation(text, source_file)

    def begin_command(self, command: str, source_file: str) -> None:
        self.counter += 1
        self.pending = PendingCommand(id=command_id(self.counter))
        self.state = "capturing_command"
        self.add_command_text(command, source_file)
        print(f"heard wake word; capturing command {self.pending.id}", flush=True)
        self.set_status("capturing_command")

    def add_command_text(self, text: str, source_file: str) -> None:
        if not self.pending:
            return
        cleaned = clean_text(text)
        if cleaned:
            self.pending.raw_parts.append(cleaned)
            self.pending.last_activity_monotonic = time.monotonic()
        if source_file:
            self.pending.source_files.append(source_file)

    def request_confirmation(self) -> None:
        if not self.pending:
            self.state = "idle"
            return
        command = self.pending.interpreted_text
        if not command:
            self.expire_command("empty_command")
            return
        self.pending.confirmation_text = f"I heard: {command}. Say yes to approve or no to cancel."
        self.state = "awaiting_confirmation"
        print(self.pending.confirmation_text, flush=True)
        append_jsonl(HISTORY_JSONL, self.base_record("awaiting_confirmation"))
        self.set_status("awaiting_confirmation")

    def approve_command(self, confirmation_text: str, source_file: str) -> None:
        if not self.pending:
            self.state = "idle"
            return
        record = self.base_record("approved")
        record["approved_at"] = utc_now()
        record["approval_text"] = confirmation_text
        if source_file:
            record["source_files"].append(source_file)
        append_jsonl(APPROVED_JSONL, record)
        append_jsonl(HISTORY_JSONL, record)
        print(f"Approved. Queued command {record['id']}: {record['interpreted_text']}", flush=True)
        self.finish()

    def deny_command(self, denial_text: str, source_file: str) -> None:
        if not self.pending:
            self.state = "idle"
            return
        record = self.base_record("denied")
        record["denied_at"] = utc_now()
        record["denial_text"] = denial_text
        if source_file:
            record["source_files"].append(source_file)
        append_jsonl(HISTORY_JSONL, record)
        print(f"Cancelled command {record['id']}.", flush=True)
        self.finish()

    def repeat_confirmation(self, text: str, source_file: str) -> None:
        if self.pending and source_file:
            self.pending.source_files.append(source_file)
        print("I need a clear yes or no.", flush=True)
        if self.pending and self.pending.confirmation_text:
            print(self.pending.confirmation_text, flush=True)
        append_jsonl(HISTORY_JSONL, {
            "id": self.pending.id if self.pending else None,
            "created_at": utc_now(),
            "status": "ambiguous_confirmation",
            "text": text,
        })

    def expire_command(self, reason: str) -> None:
        if self.pending:
            record = self.base_record("expired")
            record["expired_at"] = utc_now()
            record["reason"] = reason
            append_jsonl(HISTORY_JSONL, record)
            print(f"Expired command {record['id']}: {reason}", flush=True)
        self.finish()

    def tick_timeouts(self) -> None:
        if not self.pending:
            return
        now = time.monotonic()
        if self.state == "capturing_command" and now - self.pending.last_activity_monotonic >= CAPTURE_IDLE_SECONDS:
            self.request_confirmation()
        if self.state == "awaiting_confirmation" and now - self.pending.last_activity_monotonic >= CONFIRMATION_TIMEOUT_SECONDS:
            self.expire_command("confirmation_timeout")

    def base_record(self, status: str) -> dict[str, Any]:
        assert self.pending is not None
        return {
            "id": self.pending.id,
            "created_at": utc_now(),
            "started_at": self.pending.started_at,
            "status": status,
            "raw_text": self.pending.raw_text,
            "interpreted_text": self.pending.interpreted_text,
            "confirmation_text": self.pending.confirmation_text,
            "source_files": list(dict.fromkeys(self.pending.source_files)),
        }

    def finish(self) -> None:
        self.pending = None
        self.state = "idle"
        self.cooldown_until = time.monotonic() + COOLDOWN_SECONDS
        self.set_status("idle")

    def set_status(self, state: str) -> None:
        write_status({
            "updated_at": utc_now(),
            "state": state,
            "pending": self.base_record(state) if self.pending else None,
        })


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route transcribed Ears audio into confirmed voice commands.")
    parser.add_argument("--from-start", action="store_true", help="Read the transcript JSONL from the beginning instead of tailing from EOF.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    VoiceRouter(from_start=args.from_start).run()
