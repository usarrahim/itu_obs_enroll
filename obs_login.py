#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless Playwright helper for logging into ITU OBS and retrieving a JWT."""

import json
import re
from typing import Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    sync_playwright = None
    PlaywrightTimeout = None


OBS_BASE_URL = "https://obs.itu.edu.tr"
OBS_LOGIN_START = "https://obs.itu.edu.tr"
JWT_URL = "https://obs.itu.edu.tr/ogrenci/auth/jwt"

PAGE_LOAD_TIMEOUT_MS = 60_000
NAVIGATION_TIMEOUT_MS = 45_000
JWT_WAIT_AFTER_LOAD_MS = 3_000

MAX_LOGIN_RETRIES = 3


def get_jwt_with_playwright(username: str, password: str, headless: bool = True) -> Optional[str]:
    """Login to OBS with Playwright, follow redirects and fetch JWT."""
    if sync_playwright is None:
        raise ImportError("Playwright is required: pip install playwright && playwright install chromium")

    token: Optional[str] = None
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        try:
            token = _do_login_and_fetch_jwt(username, password, headless)
            if token:
                return token
        except Exception:
            continue
    return None


def _do_login_and_fetch_jwt(username: str, password: str, headless: bool) -> Optional[str]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
        context.set_default_timeout(PAGE_LOAD_TIMEOUT_MS)
        page = context.new_page()

        try:
            page.goto(OBS_LOGIN_START, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_selector("input[type='password'], input[name='Password'], input[name='password']", timeout=15_000)

            _fill_and_submit_login(page, username, password)

            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(JWT_WAIT_AFTER_LOAD_MS)

            resp = page.request.get(
                JWT_URL,
                headers={"Accept": "application/json"},
            )
            if resp.status != 200:
                return None
            body = resp.text()
            if not body:
                return None
            token = _extract_jwt_from_response(body)
            return token
        finally:
            context.close()
            browser.close()
    return None


def _fill_and_submit_login(page, username: str, password: str) -> None:
    """Fill username/password fields and submit the login form."""
    username_selectors = [
        'input[name="username"]',
        'input[name="UserName"]',
        'input[name="KullaniciAdi"]',
        'input[type="email"]',
        'input[id*="username"]',
        'input[id*="UserName"]',
        'input[id*="KullaniciAdi"]',
        'input[placeholder*="mail"]',
        'input[placeholder*="kullanıcı"]',
    ]
    password_selectors = [
        'input[name="password"]',
        'input[name="Password"]',
        'input[name="Sifre"]',
        'input[type="password"]',
        'input[id*="password"]',
        'input[id*="Password"]',
        'input[id*="Sifre"]',
    ]
    submit_selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Giriş")',
        'button:has-text("Login")',
        'input[value*="Giriş"]',
        'input[value*="Login"]',
        'a:has-text("Giriş")',
        '[type="submit"]',
    ]

    user_filled = False
    for sel in username_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.fill(username)
                user_filled = True
                break
        except Exception:
            continue
    if not user_filled:
        raise RuntimeError("Username input field not found")

    pass_filled = False
    for sel in password_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.fill(password)
                pass_filled = True
                break
        except Exception:
            continue
    if not pass_filled:
        raise RuntimeError("Password input field not found")

    for sel in submit_selectors:
        try:
            btn = page.locator(sel)
            if btn.count() > 0:
                btn.first.click()
                return
        except Exception:
            continue
    page.keyboard.press("Enter")


def _extract_jwt_from_response(body: str) -> Optional[str]:
    """Extract JWT string from response body."""
    body = (body or "").strip()
    if not body:
        return None
    if re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$", body):
        return body
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in ("token", "accessToken", "access_token", "jwt", "data"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    return val
                if isinstance(val, dict) and "token" in val:
                    return val.get("token")
        if isinstance(data, str):
            return data
    except Exception:
        pass
    return None


def get_jwt(username: str, password: str, headless: bool = True) -> Optional[str]:
    return get_jwt_with_playwright(username, password, headless=headless)


if __name__ == "__main__":
    import os
    USERNAME = os.environ.get("ITU_USERNAME", "")
    PASSWORD = os.environ.get("ITU_PASSWORD", "")
    if not USERNAME or not PASSWORD:
        print("Set ITU_USERNAME and ITU_PASSWORD environment variables or edit the code.")
    else:
        t = get_jwt(USERNAME, PASSWORD)
        print("Token retrieved." if t else "Token could not be retrieved.")
        if t:
            print("Bearer", t[:50] + "...")

