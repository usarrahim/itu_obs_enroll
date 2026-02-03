#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated ITU OBS course registration script.
Runs in terminal, no GUI.
"""

import os
import json
import re
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Optional: Playwright-based login to capture JWT automatically
try:
    from obs_login import get_jwt as get_jwt_playwright
except ImportError:
    get_jwt_playwright = None


# =============================================================================
# CONFIGURATION (loaded from environment)
# =============================================================================

load_dotenv()

MODE = os.getenv("MODE", "WATCH").upper()  # "TIME" or "WATCH"

USERNAME = os.getenv("ITU_USERNAME", "").strip()
PASSWORD = os.getenv("ITU_PASSWORD", "").strip()

TARGET_TIME = os.getenv("TARGET_TIME", "14:00:00.400").strip()

RETRY_INTERVAL = float(os.getenv("RETRY_INTERVAL_SECONDS", "3.12"))

DIRECT_ENROLL_INTERVAL = float(os.getenv("DIRECT_ENROLL_INTERVAL_SECONDS", "120"))

WATCH_CRNS_RAW = os.getenv("WATCH_CRNS", "").strip()
TIME_CRNS_RAW = os.getenv("TIME_CRNS", "").strip()

LOGIN_BASE_URL = os.getenv("OBS_LOGIN_BASE_URL", "https://obs.itu.edu.tr").strip()

DERS_PROGRAM_BASE = "https://obs.itu.edu.tr/public/DersProgram/DersProgramSearch"

BRANCH_CODES_FILE = os.getenv("BRANCH_CODES_FILE", "derskodları.json").strip()

TOKEN_REFRESH_INTERVAL = 15 * 60

USE_TARGET_TIME = True  # time-based mode uses this; watch mode ignores it

# Populated at runtime from derskodları.json based on used branch codes
DERS_PROGRAM_URLS: Dict[str, str] = {}

# =============================================================================
# SABİTLER (Genelde dokunmayın)
# =============================================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _default_headers() -> dict[str, str]:
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


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"Saat: {ts} - {msg}", flush=True)


def _load_branch_code_map() -> Dict[str, int]:
    try:
        with open(BRANCH_CODES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        result: Dict[str, int] = {}
        for item in data:
            code = str(item.get("dersBransKodu") or "").upper()
            bid = item.get("bransKoduId")
            if code and isinstance(bid, int):
                result[code] = bid
        return result
    except Exception:
        return {}


def _init_ders_program_urls(required_branch_codes: List[str]) -> None:
    global DERS_PROGRAM_URLS
    branch_map = _load_branch_code_map()
    urls: Dict[str, str] = {}
    for code in set(c.upper() for c in required_branch_codes):
        bid = branch_map.get(code)
        if bid is None:
            continue
        urls[code] = f"{DERS_PROGRAM_BASE}?programSeviyeTipiAnahtari=LS&dersBransKoduId={bid}"
    DERS_PROGRAM_URLS = urls


def _parse_prefixed_crn_list(raw: str) -> Tuple[List[str], List[str]]:
    """
    Parses strings like 'EHB:23603,MYZ:23622' into:
    (['23603','23622'], ['EHB','MYZ'])
    """
    crns: List[str] = []
    branches: List[str] = []
    if not raw:
        return crns, branches
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        if ":" not in token:
            _log(f"Geçersiz CRN formatı (prefix yok, beklenen BRANCH:CRN): '{token}'")
            continue
        branch, crn = token.split(":", 1)
        branch = branch.strip().upper()
        crn = crn.strip()
        if branch and crn:
            branches.append(branch)
            crns.append(crn)
    return crns, branches


def _parse_target_time(target: str) -> tuple[int, int, int, int]:
    """TARGET_TIME string'ini (HH:MM:SS.fff) saat, dakika, saniye, mikrosaniye olarak parse eder."""
    parts = target.strip().replace(",", ".").split(".")
    time_part = parts[0]
    # Kesirli kısım milisaniye (3 hane); mikrosaniyeye çeviriyoruz
    frac = (parts[1].ljust(3, "0")[:3] if len(parts) > 1 else "000")
    micro = int(frac) * 1000  # .000 -> 0, .500 -> 500000
    h, m, s = map(int, time_part.split(":"))
    return h, m, s, micro


def _target_today_datetime(target_time_str: str) -> datetime:
    """TARGET_TIME string'ini bugünün tarihiyle datetime'a çevirir."""
    h, m, s, micro = _parse_target_time(target_time_str)
    now = datetime.now()
    return now.replace(hour=h, minute=m, second=s, microsecond=micro)


def wait_until_target_time(
    target_time_str: str,
    session: Optional[requests.Session] = None,
    token_holder: Optional[list[Optional[str]]] = None,
) -> None:
    """
    Hedef saate kadar bekler. Hedefe 15 dakikadan fazla varsa her 15 dakikada bir
    token yenilenir; son 15 dakikada yüksek hassasiyetle bekler.
    """
    h, m, s, micro = _parse_target_time(target_time_str)
    target_today = _target_today_datetime(target_time_str)
    do_refresh = session is not None and token_holder is not None

    while True:
        now = datetime.now()
        if now >= target_today:
            break
        delta_sec = (target_today - now).total_seconds()

        if do_refresh and delta_sec > TOKEN_REFRESH_INTERVAL:
            # 15 dakika uyu, sonra token yenile
            sleep_sec = min(TOKEN_REFRESH_INTERVAL, delta_sec)
            time.sleep(sleep_sec)
            token_holder[0] = do_login(session)
        else:
            # Son 15 dakika veya daha az: yüksek hassasiyet
            if delta_sec > 1.0:
                time.sleep(min(0.5, delta_sec / 2))
            elif delta_sec > 0.02:
                time.sleep(delta_sec)

    return


def do_login(session: requests.Session) -> Optional[str]:
    """
    OBS girişi: Önce Playwright ile obs.itu.edu.tr + /ogrenci/auth/jwt ile JWT alır;
    başarısızsa veya Playwright yoksa requests ile denemeye devam eder.
    """
    # 1) Playwright ile tarayıcı tabanlı giriş ve JWT yakalama (auth/jwt, credentials include)
    if get_jwt_playwright and USERNAME and PASSWORD:
        try:
            token = get_jwt_playwright(USERNAME, PASSWORD, headless=True)
            if token:
                return token
        except Exception as e:
            pass

    token: Optional[str] = None
    # Yaygın login endpoint'leri
    login_urls = [
        f"{LOGIN_BASE_URL}/api/auth/login",
        f"{LOGIN_BASE_URL}/api/login",
        f"{LOGIN_BASE_URL}/login",
        f"{LOGIN_BASE_URL.rstrip('/')}/api/Auth/Login",
    ]
    headers = _default_headers()
    headers["Content-Type"] = "application/json"

    for base in login_urls:
        try:
            # Bazı sistemler username/password, bazıları kullanici_adi/sifre kullanır
            for body in (
                {"username": USERNAME, "password": PASSWORD},
                {"kullanici_adi": USERNAME, "sifre": PASSWORD},
                {"UserName": USERNAME, "Password": PASSWORD},
                {"email": USERNAME, "password": PASSWORD},
            ):
                r = session.post(
                    base,
                    json=body,
                    headers=headers,
                    timeout=15,
                    allow_redirects=True,
                )
                if r.status_code == 401:
                    continue
                data = None
                try:
                    data = r.json()
                except Exception:
                    pass
                if data and isinstance(data, dict):
                    for key in ("token", "accessToken", "access_token", "accessToken", "jwt"):
                        if key in data and data[key]:
                            token = data[key] if isinstance(data[key], str) else str(data[key])
                            break
                if token:
                    return token
        except requests.RequestException as e:
            continue

    # Cookie ile devam: login sayfasına GET atıp form POST denemesi (klasik form)
    try:
        get_url = f"{LOGIN_BASE_URL}/" if not LOGIN_BASE_URL.endswith("/") else LOGIN_BASE_URL
        session.get(get_url, headers=_default_headers(), timeout=10)
        form_url = f"{LOGIN_BASE_URL}/login" if not LOGIN_BASE_URL.rstrip("/").endswith("login") else LOGIN_BASE_URL.rstrip("/")
        r = session.post(
            form_url,
            data={"username": USERNAME, "password": PASSWORD},
            headers={**_default_headers(), "Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
            allow_redirects=True,
        )
        if r.status_code == 200 and "token" in r.text.lower():
            match = re.search(r'"token"\s*:\s*"([^"]+)"', r.text, re.I)
            if match:
                token = match.group(1)
                return token
    except Exception as e:
        pass

    return token


def ensure_token(session: requests.Session, current_token: Optional[str]) -> Optional[str]:
    """Mevcut token varsa döndürür, yoksa login dener."""
    if current_token:
        return current_token
    return do_login(session)


def build_headers_with_auth(token: Optional[str]) -> dict[str, str]:
    h = _default_headers()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def send_ders_kayit(
    session: requests.Session,
    crn_list: list[str],
    token: Optional[str],
) -> tuple[requests.Response, Optional[str]]:
    """
    Ders kayıt API'sine POST atar. (Response, güncel_token) döner.
    401 alınırsa token None yapılır ki tekrar login denensin.
    """
    url = "https://obs.itu.edu.tr/api/ders-kayit/v21"
    body = {"ECRN": crn_list, "SCRN": []}
    headers = build_headers_with_auth(token)
    resp = session.post(
        url,
        json=body,
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 401:
        return resp, None
    return resp, token


def _parse_table_for_crns(soup: BeautifulSoup, watch_crns: list[str]) -> dict[str, dict]:
    """HTML tablosundan watch_crns listesindeki CRN'lerin kontenjan bilgilerini çıkarır."""
    kontenjan_bilgileri: dict[str, dict] = {}
    rows = soup.find_all("tr")
    # İlk satır header, gerisi veriler
    for row in rows[1:]:
        cols = row.find_all("td")
        if len(cols) < 11:
            continue
        try:
            crn = cols[0].get_text(strip=True)
            if not crn or crn not in watch_crns:
                continue
            kapasite_txt = cols[9].get_text(strip=True)  # Capacity (Kontenjan)
            kayitli_txt = cols[10].get_text(strip=True)  # Enrolled (Yazılan)
            kontenjan = int(kapasite_txt) if kapasite_txt.isdigit() else 0
            kayitli = int(kayitli_txt) if kayitli_txt.isdigit() else 0
            bos = max(kontenjan - kayitli, 0)
            kontenjan_bilgileri[crn] = {
                "kontenjan": kontenjan,
                "kayitli": kayitli,
                "bos": bos,
            }
        except Exception:
            continue
    return kontenjan_bilgileri


def check_kontenjan(session: requests.Session, watch_crns: list[str]) -> tuple[list[str], dict[str, dict]]:
    """
    EHB ve MYZ endpoint'lerinden kontenjan bilgisini çeker ve watch_crns
    listesindeki kontenjanı boş olan dersleri (CRN) döndürür.
    Her iki endpoint'e de istek atar, hangi endpoint'te CRN bulunursa onu kullanır.
    Döner: (boş_kontenjan_olan_crn_listesi, {crn: {kontenjan, kayitli, bos}})
    """
    kontenjan_bilgileri: dict[str, dict] = {}
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Referer": "https://obs.itu.edu.tr/public/DersProgram",
    }
    
    if not DERS_PROGRAM_URLS:
        return [], {}

    # İlgili tüm endpoint'lere istek at
    for branş_adi, url in DERS_PROGRAM_URLS.items():
        try:
            resp = session.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                parsed = _parse_table_for_crns(soup, watch_crns)
                # Bulunan CRN'leri birleştir (aynı CRN birden fazla endpoint'te olmaz ama güvenlik için)
                for crn, info in parsed.items():
                    if crn not in kontenjan_bilgileri:
                        kontenjan_bilgileri[crn] = info
        except Exception:
            continue
    
    # Boş kontenjanlı CRN'leri bul
    open_crns: list[str] = []
    for crn, info in kontenjan_bilgileri.items():
        if info["bos"] > 0:
            open_crns.append(crn)
    
    return open_crns, kontenjan_bilgileri


def parse_response(response: requests.Response) -> tuple[bool, list[str], list[str], str]:
    """
    API yanıtını analiz eder.
    Döner: (tümü_başarılı, alınan_dersler, alınamayan_crn_listesi, durum_mesajı)
    """
    alinan: list[str] = []
    alinamayan: list[str] = []
    try:
        data = response.json()
    except Exception:
        return False, [], [], f"Hata: Geçersiz JSON - {response.text[:200]}"

    if not isinstance(data, dict):
        return False, [], [], "Hata: Yanıt sözlük değil"

    # Başarı bilgisi farklı key'lerde olabilir
    success = data.get("success", data.get("basarili", data.get("isSuccess", None)))
    if success is True:
        # Hangi derslerin eklendiği
        for key in ("eklenenDersler", "eklenen", "added", "kayitYapilanDersler", "data"):
            val = data.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and "crn" in item:
                        alinan.append(str(item["crn"]))
                    elif isinstance(item, str):
                        alinan.append(item)
                break
            if isinstance(val, dict) and "crn" in val:
                alinan.append(str(val["crn"]))
        return True, alinan, [], "Başarılı"
    if success is False:
        # Hata veya kısmi başarı
        hata_mesaj = data.get("message", data.get("mesaj", data.get("error", "")))
        hatalar = data.get("errors", data.get("hatalar", data.get("failedCRNs", [])))
        if isinstance(hatalar, list):
            for x in hatalar:
                if isinstance(x, dict) and "crn" in x:
                    alinamayan.append(str(x["crn"]))
                elif isinstance(x, str):
                    alinamayan.append(x)
        return False, alinan, alinamayan, hata_mesaj or "Bazı dersler alınamadı"
    # success yoksa yanıtı metin olarak değerlendir
    if response.status_code == 200:
        return True, alinan, [], "Başarılı (yanıt ayrıştırılamadı)"
    return False, alinan, alinamayan, response.text[:150] or "Bilinmeyen yanıt"


def _watch_loop(session: requests.Session, token_ref: list[Optional[str]], normalized_watch_crns: list[str]) -> None:
    """Kontenjan izleme döngüsü (thread)."""
    interval_dk = RETRY_INTERVAL / 60.0
    print(f"Kontenjan kontrolü her {interval_dk:.2f} dakikada bir yapılacak.", flush=True)
    while True:
        try:
            token_ref[0] = ensure_token(session, token_ref[0])
            # Kontenjan kontrolü
            open_crns, kontenjan_bilgileri = check_kontenjan(session, normalized_watch_crns)
            
            # Kontenjan sonuçlarını yazdır
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{ts}] Kontenjan kontrolü:", flush=True)
            for crn in normalized_watch_crns:
                if crn in kontenjan_bilgileri:
                    info = kontenjan_bilgileri[crn]
                    durum = "BOŞ" if info["bos"] > 0 else "DOLU"
                    print(f"  CRN {crn}: {durum} (Kontenjan: {info['kontenjan']}, Kayıtlı: {info['kayitli']}, Boş: {info['bos']})", flush=True)
                else:
                    print(f"  CRN {crn}: API'de bu CRN için veri bulunamadı (CRN yanlış olabilir veya bu dönem açılmamış)", flush=True)
            
            if open_crns:
                print(f"\n[{ts}] Kontenjan boşluğu bulundu! Kayıt isteği atılıyor: {open_crns}", flush=True)
                # Kontenjan boşluğu bulundu, kayıt isteği at
                resp, token_ref[0] = send_ders_kayit(session, open_crns, token_ref[0])
                # Response'u yazdır
                print(f"Status: {resp.status_code}", flush=True)
                print(f"Headers: {dict(resp.headers)}", flush=True)
                print(f"Body: {resp.text}", flush=True)
                # 401 gelirse token yenile
                if resp.status_code == 401:
                    token_ref[0] = None
            else:
                print(f"[{ts}] Kontenjan boşluğu yok.", flush=True)
            
            # RETRY_INTERVAL kadar bekle, tekrar kontrol et
            time.sleep(RETRY_INTERVAL)
        except requests.RequestException:
            token_ref[0] = None
            time.sleep(RETRY_INTERVAL)
        except KeyboardInterrupt:
            return
        except Exception:
            time.sleep(RETRY_INTERVAL)


def _direct_enroll_loop(session: requests.Session, token_ref: list[Optional[str]], normalized_watch_crns: list[str]) -> None:
    """Her 2 dakikada bir direkt kayıt isteği döngüsü (thread)."""
    interval_dk = DIRECT_ENROLL_INTERVAL / 60.0
    print(f"Direkt kayıt isteği her {interval_dk:.0f} dakikada bir atılacak.", flush=True)
    while True:
        try:
            time.sleep(DIRECT_ENROLL_INTERVAL)
            token_ref[0] = ensure_token(session, token_ref[0])
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{ts}] Direkt kayıt isteği atılıyor: {normalized_watch_crns}", flush=True)
            resp, token_ref[0] = send_ders_kayit(session, normalized_watch_crns, token_ref[0])
            # Response'u yazdır
            print(f"Status: {resp.status_code}", flush=True)
            print(f"Headers: {dict(resp.headers)}", flush=True)
            print(f"Body: {resp.text}", flush=True)
            # 401 gelirse token yenile
            if resp.status_code == 401:
                token_ref[0] = None
        except requests.RequestException:
            token_ref[0] = None
        except KeyboardInterrupt:
            return
        except Exception:
            pass


def run() -> None:
    if not USERNAME or not PASSWORD:
        print("Missing ITU_USERNAME/ITU_PASSWORD in environment.", flush=True)
        sys.exit(1)

    session = requests.Session()
    session.headers.update(_default_headers())
    # Login
    token: Optional[str] = ensure_token(session, None)

    if MODE == "TIME":
        crns, _branches = _parse_prefixed_crn_list(TIME_CRNS_RAW)
        crns = [c for c in crns if c]
        if not crns:
            print("TIME mode selected but TIME_CRNS is empty or invalid.", flush=True)
            sys.exit(1)

        if USE_TARGET_TIME:
            token_holder: list[Optional[str]] = [token]
            wait_until_target_time(TARGET_TIME, session=session, token_holder=token_holder)
            token = token_holder[0]

        resp, token = send_ders_kayit(session, crns, token)
        print(f"Status: {resp.status_code}", flush=True)
        print(f"Headers: {dict(resp.headers)}", flush=True)
        print(f"Body: {resp.text}", flush=True)
        return

    # Default: WATCH mode
    watch_crns, branch_codes = _parse_prefixed_crn_list(WATCH_CRNS_RAW)
    watch_crns = [c for c in watch_crns if c]
    if not watch_crns:
        print("WATCH mode selected but WATCH_CRNS is empty or invalid.", flush=True)
        sys.exit(1)

    _init_ders_program_urls(branch_codes)
    if not DERS_PROGRAM_URLS:
        print("No valid branch codes found for WATCH_CRNS. Check derskodları.json and prefixes.", flush=True)
        sys.exit(1)

    token_ref: list[Optional[str]] = [token]

    watch_thread = threading.Thread(
        target=_watch_loop, args=(session, token_ref, watch_crns), daemon=True
    )
    direct_thread = threading.Thread(
        target=_direct_enroll_loop, args=(session, token_ref, watch_crns), daemon=True
    )

    watch_thread.start()
    direct_thread.start()

    try:
        watch_thread.join()
        direct_thread.join()
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    run()
