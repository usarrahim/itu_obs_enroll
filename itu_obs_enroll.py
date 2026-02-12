#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Simple timed enrollment script for ITU OBS."""

import time
from datetime import datetime
from typing import List, Optional, Tuple

import requests
import getpass

try:
    from obs_login import get_jwt
except ImportError:
    get_jwt = None

TARGET_TIME = "14:00:00.500"

# CRNs to ADD (ECRN) / DROP (SCRN)
ADD_CRNS: List[str] = []
DROP_CRNS: List[str] = []

DERS_KAYIT_URL = "https://obs.itu.edu.tr/api/ders-kayit/v21"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}", flush=True)


def default_headers() -> dict:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=1, i",
    }


def parse_target_time(target: str) -> Tuple[int, int, int, int]:
    parts = target.strip().replace(",", ".").split(".")
    time_part = parts[0]
    frac = (parts[1].ljust(3, "0")[:3] if len(parts) > 1 else "000")
    micro = int(frac) * 1000
    h, m, s = map(int, time_part.split(":"))
    return h, m, s, micro


def wait_until(target_time_str: str) -> None:
    h, m, s, micro = parse_target_time(target_time_str)
    now = datetime.now()
    target_today = now.replace(hour=h, minute=m, second=s, microsecond=micro)
    if target_today <= now:
        log(f"Target time is in the past today: {target_time_str}. Exiting.")
        raise SystemExit(1)

    log(f"Waiting until {target_time_str} ...")
    while True:
        now = datetime.now()
        if now >= target_today:
            break
        delta = (target_today - now).total_seconds()
        if delta > 1.0:
            time.sleep(min(0.5, delta / 2))
        elif delta > 0.01:
            time.sleep(delta)
        # last ~10ms: busy-wait (no sleep)
    log("Target time reached.")


def prompt_time(default: str) -> str:
    s = input(f"Target time (HH:MM:SS.mmm) [{default}]: ").strip()
    return s or default


def prompt_crns(label: str) -> List[str]:
    raw = input(f"{label} CRN list (comma-separated, empty: none): ").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def send_request(session: requests.Session, token: Optional[str]) -> Tuple[requests.Response, Optional[str]]:
    headers = default_headers()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"ECRN": ADD_CRNS, "SCRN": DROP_CRNS}
    resp = session.post(DERS_KAYIT_URL, json=body, headers=headers, timeout=30)
    if resp.status_code == 401:
        # token invalid/expired; do not auto-refresh in this minimal script
        return resp, None
    return resp, token


def main() -> None:
    if get_jwt is None:
        raise SystemExit("obs_login.py with Playwright is required to obtain JWT.")

    global TARGET_TIME, ADD_CRNS, DROP_CRNS

    username = input("OBS username (email): ").strip()
    password = getpass.getpass("OBS password: ")
    if not username or not password:
        raise SystemExit("Username and password cannot be empty.")

    TARGET_TIME = prompt_time(TARGET_TIME)
    ADD_CRNS = prompt_crns("ADD (ECRN)")
    DROP_CRNS = prompt_crns("DROP (SCRN)")
    if not ADD_CRNS and not DROP_CRNS:
        raise SystemExit("You must enter at least one CRN (ADD or DROP).")

    log("Logging into OBS with Playwright to obtain JWT...")
    token = get_jwt(username=username, password=password, headless=False)
    if not token:
        raise SystemExit("Failed to obtain JWT.")

    session = requests.Session()
    session.headers.update(default_headers())
    wait_until(TARGET_TIME)

    resp, token = send_request(session, token)
    log("Request #1 sent. Full response:")
    print(f"Status: {resp.status_code}", flush=True)
    print(f"Headers: {dict(resp.headers)}", flush=True)
    print(f"Body: {resp.text}", flush=True)

    while True:
        try:
            choice = input('Type "1" then Enter to send one more request, anything else to exit: ').strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice != "1":
            return
        resp, token = send_request(session, token)
        log("Extra request sent. Full response:")
        print(f"Status: {resp.status_code}", flush=True)
        print(f"Headers: {dict(resp.headers)}", flush=True)
        print(f"Body: {resp.text}", flush=True)


if __name__ == "__main__":
    main()

