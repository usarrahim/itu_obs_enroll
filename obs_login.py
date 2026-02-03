#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
İTÜ OBS tarayıcı tabanlı otomatik giriş ve JWT token yakalama modülü.
Playwright (headless) ile obs.itu.edu.tr / girisv3.itu.edu.tr girişi ve
GET /ogrenci/auth/jwt ile Bearer token alır.
"""

import json
import re
from typing import Optional

# Playwright kullanımı (opsiyonel bağımlılık)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    sync_playwright = None
    PlaywrightTimeout = None


# Varsayılan URL'ler
OBS_BASE_URL = "https://obs.itu.edu.tr"
OBS_LOGIN_START = "https://obs.itu.edu.tr"
JWT_URL = "https://obs.itu.edu.tr/ogrenci/auth/jwt"

# Giriş sayfası yüklendikten sonra bekleme (saniye)
PAGE_LOAD_TIMEOUT_MS = 60_000
NAVIGATION_TIMEOUT_MS = 45_000
JWT_WAIT_AFTER_LOAD_MS = 3_000

# Token yeniden deneme
MAX_LOGIN_RETRIES = 3


def get_jwt_with_playwright(username: str, password: str, headless: bool = True) -> Optional[str]:
    """
    Playwright ile OBS'e giriş yapar, 302 yönlendirmelerini takip eder,
    ardından GET /ogrenci/auth/jwt ile JWT alır (çerezler dahil).
    Başarısız veya boş yanıt durumunda oturumu kapatıp yeniden dener.

    Args:
        username: İTÜ kullanıcı adı (e-posta vb.)
        password: İTÜ şifre
        headless: Tarayıcıyı görünmez çalıştır

    Returns:
        Bearer token metni (JWT) veya None
    """
    if sync_playwright is None:
        raise ImportError("Playwright gerekli: pip install playwright && playwright install chromium")

    token: Optional[str] = None
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        try:
            token = _do_login_and_fetch_jwt(username, password, headless)
            if token:
                return token
        except Exception:
            # Oturum kapatıldı (context/browser kapanır), baştan dene
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
            # 1) OBS ana adrese git; gerekirse girisv3.itu.edu.tr'ye yönlendirilir
            page.goto(OBS_LOGIN_START, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            # Login formu (obs veya girisv3) görünene kadar bekle
            page.wait_for_selector("input[type='password'], input[name='Password'], input[name='password']", timeout=15_000)

            # 2) Login formunu bul (obs veya girisv3 sayfasında olabilir)
            _fill_and_submit_login(page, username, password)

            # 3) Tüm 302 yönlendirmeleri takip edilir
            page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            # Ana sayfa (obs.itu.edu.tr) yüklensin
            page.wait_for_timeout(JWT_WAIT_AFTER_LOAD_MS)

            # 4) GET /ogrenci/auth/jwt — tarayıcı bağlamındaki çerezlerle (credentials: include)
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
    """Kullanıcı adı/şifre alanlarını doldurur ve giriş butonuna basar."""
    # Yaygın selector'lar: obs / girisv3 / genel formlar
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
        raise RuntimeError("Kullanıcı adı alanı bulunamadı")

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
        raise RuntimeError("Şifre alanı bulunamadı")

    for sel in submit_selectors:
        try:
            btn = page.locator(sel)
            if btn.count() > 0:
                btn.first.click()
                return
        except Exception:
            continue
    # Son çare: form submit
    page.keyboard.press("Enter")


def _extract_jwt_from_response(body: str) -> Optional[str]:
    """JWT metnini yanıttan çıkarır. JSON { "token": "..." } veya düz JWT string olabilir."""
    body = (body or "").strip()
    if not body:
        return None
    # Düz JWT (xxx.yyy.zzz)
    if re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$", body):
        return body
    # JSON
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
    """
    İTÜ OBS JWT token alır. Playwright kullanılabilirse tarayıcı ile giriş yapıp
    /ogrenci/auth/jwt cevabından token döner; yoksa None.

    Ana script bu fonksiyonu kullanarak Authorization: Bearer <token> değerini alabilir.
    """
    return get_jwt_with_playwright(username, password, headless=headless)


if __name__ == "__main__":
    import os
    USERNAME = os.environ.get("ITU_USERNAME", "")
    PASSWORD = os.environ.get("ITU_PASSWORD", "")
    if not USERNAME or not PASSWORD:
        print("ITU_USERNAME ve ITU_PASSWORD ortam değişkenlerini ayarlayın veya kodu düzenleyin.")
    else:
        t = get_jwt(USERNAME, PASSWORD)
        print("Token alındı." if t else "Token alınamadı.")
        if t:
            print("Bearer", t[:50] + "...")
