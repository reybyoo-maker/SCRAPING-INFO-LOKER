"""Daily, bounded, multi-source job listing collector for Indonesia.

The collector reads RSS and public/authorized APIs; it does not crawl every outbound
article or bypass access controls. Missing facts are left empty rather than guessed.
"""
from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import logging
import os
import re
import socket
import time
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl, urlencode as encode_qs

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
JOBS_FILE = DATA_DIR / "jobs.json"
STATUS_FILE = DATA_DIR / "run_status.json"
LOCATIONS_FILE = CONFIG_DIR / "locations.json"
APPROVED_FEEDS_FILE = CONFIG_DIR / "approved_feeds.json"

UTC = timezone.utc
WIB = timezone(timedelta(hours=7))
USER_AGENT = "InfoLokerIndonesiaCollector/1.0 (+https://github.com/reybyoo-maker/SCRAPING-INFO-LOKER)"
TIMEOUT = 12
RETRIES = 1
QUERY_BATCH_SIZE = max(10, int(os.getenv("QUERY_BATCH_SIZE", "90")))
RETENTION_DAYS = max(30, int(os.getenv("DATA_RETENTION_DAYS", "120")))
OCR_ENABLED = os.getenv("ENABLE_FLYER_OCR", "0").lower() in ("1", "true", "yes")
MAX_OCR_PER_RUN = max(0, int(os.getenv("MAX_OCR_PER_RUN", "10")))
OCR_COUNTER = 0

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("info-loker")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json, application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
})


PROVINCES = [
    "Aceh", "Sumatera Utara", "Sumatera Barat", "Riau", "Kepulauan Riau", "Jambi",
    "Sumatera Selatan", "Kepulauan Bangka Belitung", "Bengkulu", "Lampung",
    "DKI Jakarta", "Banten", "Jawa Barat", "Jawa Tengah", "DI Yogyakarta", "Jawa Timur",
    "Bali", "Nusa Tenggara Barat", "Nusa Tenggara Timur", "Kalimantan Barat",
    "Kalimantan Tengah", "Kalimantan Selatan", "Kalimantan Timur", "Kalimantan Utara",
    "Sulawesi Utara", "Gorontalo", "Sulawesi Tengah", "Sulawesi Barat", "Sulawesi Selatan",
    "Sulawesi Tenggara", "Maluku", "Maluku Utara", "Papua", "Papua Barat", "Papua Selatan",
    "Papua Tengah", "Papua Pegunungan", "Papua Barat Daya",
]

FRAUD_SIGNALS = [
    "biaya pendaftaran", "uang administrasi", "diminta transfer", "transfer terlebih dahulu",
    "bayar untuk melamar", "biaya seragam", "deposit pekerjaan", "biaya interview",
    "bayar training", "minta top up", "biaya penempatan",
]
NEGATED_FEE_PHRASES = [
    "tanpa biaya pendaftaran", "tidak dipungut biaya", "gratis tanpa biaya",
    "tidak ada biaya pendaftaran", "proses rekrutmen gratis",
]
VACANCY_KEYWORDS = [
    "lowongan", "loker", "rekrutmen", "recruitment", "walk in", "walk-in",
    "dibutuhkan", "penerimaan", "karir", "career", "job vacancy", "hiring",
    "tenaga kerja", "fresh graduate", "magang", "posisi",
]

EDUCATION_MAP = [
    (r"\b(S3|doktoral|doctoral)\b", "S3"),
    (r"\b(S2|magister|master degree)\b", "S2"),
    (r"\b(S1|sarjana|bachelor(?:'s)? degree)\b", "S1"),
    (r"\b(D4|DIV)\b", "D4"),
    (r"\b(D3|diploma III)\b", "D3"),
    (r"\b(D1|D2|diploma I{1,2})\b", "D1/D2"),
    (r"\b(SMA|SMK|MA|SLTA|sederajat)\b", "SMA/SMK sederajat"),
    (r"\b(SMP|SLTP)\b", "SMP"),
    (r"\b(SD|sekolah dasar)\b", "SD"),
]
SOCIAL_DOMAINS = (
    "instagram.com", "facebook.com", "fb.com", "linkedin.com", "tiktok.com",
    "x.com", "twitter.com", "youtube.com", "youtu.be", "wa.me", "whatsapp.com",
    "t.me", "telegram.me",
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return now_utc().isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_date(value) -> str | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value, tz=UTC)
        else:
            parsed = date_parser.parse(str(value), fuzzy=True)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            parsed = parsed.astimezone(UTC)
        return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        return None


def date_age_days(value: str | None) -> float | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    try:
        dt = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
        return max(0.0, (now_utc() - dt).total_seconds() / 86400)
    except Exception:
        return None


def read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def clean_text(value, limit: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip() + "…"
    return text


def safe_public_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(str(url).strip())
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            return False
        hostname = parsed.hostname.lower()
        if hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            # Reject localhost/private literals, but allow public hostnames.
            if "." not in hostname:
                return False
        return True
    except Exception:
        return False


def http_get(url: str, params=None, timeout: int = TIMEOUT):
    if not safe_public_url(url):
        raise ValueError("URL is not a permitted public HTTP(S) URL")
    last_error = None
    for attempt in range(RETRIES + 1):
        try:
            response = SESSION.get(url, params=params, timeout=timeout, allow_redirects=True)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < RETRIES:
                    time.sleep(1.5 * (attempt + 1))
                    continue
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < RETRIES:
                time.sleep(1.0 * (attempt + 1))
    raise last_error


def clean_url(url: str | None) -> str:
    if not url:
        return ""
    url = html.unescape(str(url)).strip()
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return ""
        ignored = {"fbclid", "gclid", "ref", "source", "trk", "tracking"}
        pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in ignored]
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", encode_qs(pairs, doseq=True), ""))
    except Exception:
        return ""


def make_id(url: str, title: str, company: str, city: str) -> str:
    canonical = clean_url(url)
    seed = canonical if canonical else "|".join([
        clean_text(title).lower(), clean_text(company).lower(), clean_text(city).lower()
    ])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def extract_social_links(value: str) -> list[str]:
    links = []
    if not value:
        return links
    soup = BeautifulSoup(str(value), "html.parser")
    candidates = [a.get("href", "") for a in soup.find_all("a", href=True)]
    candidates += re.findall(r"https?://[^\s<>\"]+", str(value))
    for candidate in candidates:
        candidate = html.unescape(candidate).rstrip(".,);]")
        if not safe_public_url(candidate):
            continue
        host = (urlparse(candidate).hostname or "").lower()
        if any(host == domain or host.endswith("." + domain) for domain in SOCIAL_DOMAINS):
            cleaned = clean_url(candidate)
            if cleaned and cleaned not in links:
                links.append(cleaned)
    return links[:12]


def extract_phone(value: str) -> str | None:
    text = clean_text(value)
    patterns = [
        r"(?<!\w)(?:\+62|62|0)(?:[\s().-]*\d){8,13}(?!\w)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            digits = re.sub(r"\D", "", match.group(0))
            if 9 <= len(digits) <= 15 and not digits.startswith("2026"):
                return ("+" + digits) if match.group(0).strip().startswith("+") else digits
    return None


def extract_salary(value: str) -> tuple[str | None, int | None, int | None]:
    text = clean_text(value)
    patterns = [
        r"(?i)(?:Rp\.?|IDR)\s*[\d.,]+\s*(?:juta|jt|ribu|rb)?(?:\s*(?:-|–|—|sampai|hingga|to)\s*(?:Rp\.?|IDR)?\s*[\d.,]+\s*(?:juta|jt|ribu|rb)?)?",
        r"(?i)\b\d+(?:[.,]\d+)?\s*(?:juta|jt)\s*(?:-|–|sampai|hingga|to)\s*\d+(?:[.,]\d+)?\s*(?:juta|jt)\b",
    ]
    found = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            found = re.sub(r"\s+", " ", match.group(0)).strip()
            break
    if not found:
        return None, None, None

    def to_idr(part: str) -> int | None:
        part = part.lower().replace("rp", "").replace("idr", "").strip()
        multiplier = 1
        if "juta" in part or re.search(r"\bjt\b", part):
            multiplier = 1_000_000
        elif "ribu" in part or re.search(r"\brb\b", part):
            multiplier = 1_000
        part = re.sub(r"[^0-9,.]", "", part)
        if not part:
            return None
        # For Indonesian notation, dots commonly represent thousands.
        if multiplier == 1:
            part = part.replace(".", "").replace(",", "")
            try:
                return int(float(part))
            except ValueError:
                return None
        try:
            return int(float(part.replace(",", ".")) * multiplier)
        except ValueError:
            return None

    pieces = re.split(r"(?i)\s*(?:-|–|—|sampai|hingga|to)\s*", found)
    values = [to_idr(piece) for piece in pieces]
    values = [value for value in values if value is not None]
    return found, (min(values) if values else None), (max(values) if len(values) > 1 else (values[0] if values else None))


def extract_education(value: str) -> str | None:
    text = clean_text(value)
    minimum_context = re.search(
        r"(?i)(minimal pendidikan|pendidikan minimal|min\.?\s*pendidikan|lulusan minimal|minimal lulusan|pendidikan min(?:imum)?|syarat pendidikan)[^.;]{0,100}",
        text,
    )
    sample = minimum_context.group(0) if minimum_context else text
    for pattern, label in EDUCATION_MAP:
        if re.search(pattern, sample, flags=re.I):
            return label + (" (terdeteksi; verifikasi sumber)" if not minimum_context else "")
    return None


def extract_deadline(value: str) -> str | None:
    text = clean_text(value)
    match = re.search(
        r"(?i)(?:batas lamaran|batas pendaftaran|deadline|ditutup pada|apply before|apply by|closing date)\s*[:\-]?\s*([A-Za-z0-9,./ -]{3,28})",
        text,
    )
    if not match:
        return None
    raw = match.group(1).strip(" .,-")
    return parse_date(raw)


def extract_walkin_date(value: str) -> str | None:
    text = clean_text(value)
    match = re.search(
        r"(?i)(?:walk[\s-]?in(?: interview)?|interview langsung)[^.;]{0,100}?\b(\d{1,2}\s+[A-Za-z]+(?:\s+20\d{2})?|\d{1,2}[/-]\d{1,2}[/-](?:20)?\d{2})",
        text,
    )
    if not match:
        return None
    return parse_date(match.group(1))


def guess_company(value: str) -> str | None:
    text = clean_text(value)
    patterns = [
        r"\b(PT\.?\s+[A-Z0-9][A-Za-z0-9&.,'() -]{2,55})",
        r"\b(CV\.?\s+[A-Z0-9][A-Za-z0-9&.,'() -]{2,45})",
        r"\b(Yayasan\s+[A-Z0-9][A-Za-z0-9&.,'() -]{2,45})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            company = re.split(r"\s(?:membuka|membutuhkan|menerima|sedang|lowongan|mencari|untuk)\b", match.group(1), flags=re.I)[0]
            return company.strip(" .,-")[:100]
    return None


def clean_position(title: str) -> str:
    title = clean_text(title, 200)
    title = re.sub(r"(?i)^\s*(lowongan kerja|lowongan|loker|job vacancy|career opportunity|walk[\s-]?in interview|rekrutmen)\s*[:\-—]*\s*", "", title)
    title = re.sub(r"(?i)\s*[-|]\s*(lowongan kerja|loker|info loker|terbaru).*$", "", title)
    title = re.sub(r"(?i)\s+(terbaru|hari ini|202[4-9])\s*$", "", title)
    return title.strip(" -:|")[:180] or clean_text(title, 180)


def infer_work_mode(text: str) -> str | None:
    value = clean_text(text).lower()
    if any(term in value for term in ("hybrid", "kombinasi wfo dan wfh")):
        return "Hybrid"
    if any(term in value for term in ("remote", "wfh", "work from home", "kerja dari rumah", "daring", "jarak jauh")):
        return "Remote"
    if any(term in value for term in ("onsite", "on-site", "wfo", "di kantor", "di lokasi", "work from office")):
        return "On-site"
    return None


def infer_employment_type(text: str) -> str | None:
    value = clean_text(text).lower()
    mapping = [
        (("part-time", "part time", "paruh waktu"), "Part-time"),
        (("magang", "internship", "intern"), "Internship"),
        (("freelance", "freelancer", "pekerja lepas"), "Freelance"),
        (("kontrak", "contract"), "Contract"),
        (("full-time", "full time", "penuh waktu"), "Full-time"),
        (("harian", "daily worker"), "Harian"),
    ]
    for terms, label in mapping:
        if any(term in value for term in terms):
            return label
    return None


def match_location(text: str, hint: dict | None = None) -> tuple[str | None, str | None, str]:
    low = clean_text(text).lower()
    locations = read_json(LOCATIONS_FILE, {"regions": [], "cities": []})
    city_items = locations.get("cities", [])
    # Longest city name first avoids matching a short city inside a longer name.
    for item in sorted(city_items, key=lambda x: len(x.get("city") or ""), reverse=True):
        city = item.get("city")
        if city and re.search(r"(?<!\w)" + re.escape(city.lower()) + r"(?!\w)", low):
            return city, item.get("province"), "matched_in_listing"
    for province in sorted(PROVINCES, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(province.lower()) + r"(?!\w)", low):
            return None, province, "matched_in_listing"
    if hint:
        city = hint.get("city")
        province = hint.get("province")
        if city or province:
            return city, province, "search_context"
    return None, None, "unknown"


def find_flyer_url(entry) -> str | None:
    candidates = []
    for media in entry.get("media_content", []) or []:
        candidates.append(media.get("url"))
    for media in entry.get("media_thumbnail", []) or []:
        candidates.append(media.get("url"))
    for enclosure in entry.get("enclosures", []) or []:
        if str(enclosure.get("type", "")).startswith("image/"):
            candidates.append(enclosure.get("href") or enclosure.get("url"))
    summary = entry.get("summary", "") or entry.get("description", "") or ""
    soup = BeautifulSoup(str(summary), "html.parser")
    candidates.extend(img.get("src") for img in soup.find_all("img") if img.get("src"))
    for url in candidates:
        url = clean_url(url)
        if url and safe_public_url(url) and urlparse(url).scheme == "https":
            return url
    return None


def flyer_ocr(image_url: str | None) -> str | None:
    global OCR_COUNTER
    if not OCR_ENABLED or OCR_COUNTER >= MAX_OCR_PER_RUN or not image_url or not safe_public_url(image_url):
        return None
    if Image is None or pytesseract is None:
        return None
    try:
        host = (urlparse(image_url).hostname or "").lower()
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
            if any(ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback for address in addresses):
                return None
        except Exception:
            # If DNS resolution cannot be checked, skip the image.
            return None
        response = http_get(image_url, timeout=8)
        content_type = response.headers.get("content-type", "").lower()
        if not content_type.startswith("image/"):
            return None
        length = len(response.content)
        if length == 0 or length > 5_000_000:
            return None
        OCR_COUNTER += 1
        image = Image.open(BytesIO(response.content))
        image.thumbnail((1800, 1800))
        text = clean_text(pytesseract.image_to_string(image, lang="ind+eng"), 1800)
        return text or None
    except Exception as exc:
        log.debug("Flyer OCR skipped: %s", exc)
        return None


def quality(job: dict) -> tuple[int, str, list[str]]:
    score = 0
    reasons = []
    source_type = job.get("source_type", "")
    if source_type == "public_api":
        score += 18
        reasons.append("Berasal dari API lowongan publik")
    elif source_type == "approved_feed":
        score += 16
        reasons.append("Berasal dari feed yang disetujui")
    else:
        score += 8
        reasons.append("Ditemukan dari RSS pencarian; perlu cek sumber asli")

    if job.get("title"):
        score += 10
    if job.get("company_name"):
        score += 15
        reasons.append("Nama perusahaan terdeteksi")
    if job.get("listing_url"):
        score += 8
    if job.get("application_url"):
        score += 6
    if job.get("city") or job.get("province"):
        score += 10 if job.get("location_confidence") == "matched_in_listing" else 4
        reasons.append("Lokasi tercantum" if job.get("location_confidence") == "matched_in_listing" else "Lokasi berasal dari konteks pencarian")
    if job.get("salary_text"):
        score += 8
        reasons.append("Informasi gaji tersedia")
    if job.get("education_minimum"):
        score += 5
    if job.get("description_excerpt") or job.get("requirements"):
        score += 5
    if job.get("contact_phone"):
        score += 3
    if job.get("social_links"):
        score += 2
    if job.get("walk_in"):
        score += 4
        reasons.append("Kategori walk-in interview terdeteksi")

    age = date_age_days(job.get("source_updated_at") or job.get("published_at"))
    if age is None:
        score += 3
        reasons.append("Tanggal sumber belum tersedia")
    elif age <= 2:
        score += 22
        reasons.append("Informasi sumber sangat baru")
    elif age <= 7:
        score += 16
        reasons.append("Informasi sumber masih baru")
    elif age <= 30:
        score += 8
        reasons.append("Informasi sumber berusia kurang dari 30 hari")
    else:
        score -= 10
        reasons.append("Informasi sumber mungkin sudah lama")

    combined = " ".join(str(job.get(field) or "") for field in ("title", "description_excerpt", "requirements")).lower()
    risk_flags = []
    negative = any(phrase in combined for phrase in NEGATED_FEE_PHRASES)
    if not negative:
        for term in FRAUD_SIGNALS:
            if term in combined:
                risk_flags.append("Perlu verifikasi: ada frasa terkait biaya/transfer")
                score -= 20
                break
    job["risk_flags"] = list(dict.fromkeys((job.get("risk_flags") or []) + risk_flags))
    score = min(100, max(0, score))
    if score >= 75 and not job.get("risk_flags"):
        label = "HOT"
        reasons.append("Kelengkapan dan kebaruan relatif tinggi; tetap verifikasi sumber")
    elif score >= 45:
        label = "MEDIUM"
        reasons.append("Sebagian informasi penting tersedia; cek detail yang masih kosong")
    else:
        label = "LOW"
        reasons.append("Informasi terbatas atau sinyal sumber masih lemah; verifikasi ekstra diperlukan")
    return score, label, list(dict.fromkeys(reasons))


def make_record(
    title: str,
    body: str,
    url: str,
    source_name: str,
    source_type: str,
    published: str | None = None,
    updated: str | None = None,
    company: str | None = None,
    location: str | None = None,
    location_hint: dict | None = None,
    application_url: str | None = None,
    salary_text: str | None = None,
    salary_currency: str | None = None,
    salary_period: str | None = None,
    salary_min_source=None,
    salary_max_source=None,
    education: str | None = None,
    image_url: str | None = None,
    employment_type: str | None = None,
    work_mode: str | None = None,
    is_remote: bool = False,
    query: str | None = None,
) -> dict:
    title = clean_text(title, 250)
    body = clean_text(body, 900)
    full_text = " ".join(x for x in (title, body, location or "") if x)
    company = clean_text(company, 120) or guess_company(full_text)
    if location:
        city, province, location_confidence = match_location(location + " " + full_text)
        if not city and not province:
            city, province, location_confidence = match_location(full_text, location_hint)
        if not city and not province and is_remote:
            city, province, location_confidence = "Remote", "Remote / Global", "source_declared"
    else:
        city, province, location_confidence = match_location(full_text, location_hint)
        if is_remote:
            city, province, location_confidence = "Remote", "Remote / Global", "source_declared"

    detected_salary, salary_min, salary_max = extract_salary(" ".join((salary_text or "", body, title)))
    detected_salary = detected_salary or clean_text(salary_text, 100) or None
    currency = clean_text(salary_currency, 12).upper() if salary_currency else None
    period = clean_text(salary_period, 40) if salary_period else None
    try:
        source_min = int(float(salary_min_source)) if salary_min_source is not None else None
    except (TypeError, ValueError):
        source_min = None
    try:
        source_max = int(float(salary_max_source)) if salary_max_source is not None else None
    except (TypeError, ValueError):
        source_max = None
    if currency in ("IDR", "RP", "RUPIAH"):
        salary_min = salary_min if salary_min is not None else source_min
        salary_max = salary_max if salary_max is not None else source_max
    walk_in = bool(re.search(r"(?i)\bwalk[\s-]?in(?: interview)?\b|\binterview langsung\b", full_text))
    flyer_text = flyer_ocr(image_url)
    description = body[:450] if body else None
    requirements = None
    req_match = re.search(r"(?i)(?:persyaratan|kualifikasi|requirements|qualification)\s*[:\-]?\s*(.{10,240})", body)
    if req_match:
        requirements = clean_text(req_match.group(1), 240)
    phone = extract_phone(full_text)
    social_links = extract_social_links(full_text + " " + (body or ""))
    if flyer_text:
        # OCR text can provide missing salary/education/contact/location clues.
        flyer_salary, flyer_min, flyer_max = extract_salary(flyer_text)
        detected_salary = detected_salary or flyer_salary
        salary_min = salary_min if salary_min is not None else flyer_min
        salary_max = salary_max if salary_max is not None else flyer_max
        education = education or extract_education(flyer_text)
        phone = phone or extract_phone(flyer_text)
        social_links = list(dict.fromkeys(social_links + extract_social_links(flyer_text)))
        if not description:
            description = flyer_text[:450]

    record = {
        "id": make_id(url, title, company or "", city or ""),
        "title": title or "Lowongan kerja (judul perlu diverifikasi)",
        "position": clean_position(title),
        "company_name": company or None,
        "listing_url": clean_url(url) or None,
        "application_url": (str(application_url).strip() if application_url and safe_public_url(str(application_url)) else None),
        "source_name": source_name,
        "source_type": source_type,
        "source_updated_at": parse_date(updated) or parse_date(published),
        "published_at": parse_date(published),
        "first_seen_at": iso_now(),
        "last_seen_at": iso_now(),
        "last_checked_at": iso_now(),
        "city": city,
        "province": province,
        "location_label": (", ".join(x for x in [city, province] if x) or (location if is_remote else None)),
        "location_confidence": location_confidence,
        "search_context": query,
        "work_mode": work_mode or infer_work_mode(full_text) or ("Remote" if is_remote else None),
        "employment_type": employment_type or infer_employment_type(full_text),
        "salary_text": detected_salary,
        "salary_currency": currency,
        "salary_period": period,
        "salary_min_idr": salary_min,
        "salary_max_idr": salary_max,
        "education_minimum": education or extract_education(full_text + " " + (flyer_text or "")),
        "requirements": requirements,
        "description_excerpt": description,
        "contact_phone": phone,
        "social_links": social_links,
        "walk_in": walk_in,
        "walk_in_date": extract_walkin_date(full_text + " " + (flyer_text or "")) if walk_in else None,
        "walk_in_location": (location or (", ".join(x for x in [city, province] if x))) if walk_in else None,
        "flyer_image_url": clean_url(image_url) or None,
        "flyer_ocr_text": flyer_text,
        "application_deadline": extract_deadline(full_text),
        "risk_flags": [],
        "quality_score": 0,
        "quality_label": "LOW",
        "quality_explanation": [],
        "verification_status": "unverified",
        "listing_state": "active_unverified",
    }
    score, label, reasons = quality(record)
    record["quality_score"] = score
    record["quality_label"] = label
    record["quality_explanation"] = reasons
    return record


def is_vacancy_relevant(title: str, summary: str = "") -> bool:
    text = (clean_text(title) + " " + clean_text(summary)).lower()
    return any(term in text for term in VACANCY_KEYWORDS)


def query_pool() -> list[dict]:
    config = read_json(LOCATIONS_FILE, {"regions": [], "cities": []})
    targets = []
    seen = set()
    for item in config.get("regions", []) + config.get("cities", []):
        query_place = clean_text(item.get("query"))
        if not query_place:
            continue
        key = query_place.casefold()
        if key in seen:
            continue
        seen.add(key)
        targets.append(item)
    intents = [
        '"lowongan kerja"',
        '"walk in interview"',
        '"loker SMA SMK"',
        '"lowongan fresh graduate"',
    ]
    queries = []
    for item in targets:
        for intent in intents:
            queries.append({
                "q": f'{intent} "{item["query"]}" when:7d',
                "hint": item,
            })
    national_queries = [
        '"lowongan kerja" Indonesia when:7d',
        '"loker seluruh Indonesia" when:7d',
        '"walk in interview" Indonesia when:7d',
        '"lowongan kerja BUMN" Indonesia when:7d',
        '"lowongan kerja SMA SMK" Indonesia when:7d',
        '"lowongan fresh graduate" Indonesia when:7d',
        '"lowongan kerja pabrik" Indonesia when:7d',
        '"lowongan kerja remote" Indonesia when:7d',
        '"lowongan kerja part time" Indonesia when:7d',
        '"lowongan kerja magang" Indonesia when:7d',
        '"rekrutmen" Indonesia when:7d',
        '"penerimaan tenaga kerja" Indonesia when:7d',
    ]
    for query in national_queries:
        queries.append({"q": query, "hint": None})
    return queries


def fetch_google_news(batch_size: int) -> tuple[list[dict], dict]:
    pool = query_pool()
    if not pool:
        return [], {"attempted": 0, "succeeded": 0, "errors": 0, "records": 0}
    now = now_utc()
    slot = (now.hour // 8) % 3
    # Shift the starting offset each day so all query groups are reached even if the
    # query pool size changes; normal scheduled runs cover the pool with some overlap.
    day_index = now.date().toordinal()
    start = (day_index * batch_size * 3 + slot * batch_size) % len(pool)
    selected = [pool[(start + offset) % len(pool)] for offset in range(min(batch_size, len(pool)))]
    records = []
    errors = 0
    succeeded = 0
    for index, item in enumerate(selected, 1):
        rss_url = "https://news.google.com/rss/search?" + urlencode({
            "q": item["q"], "hl": "id", "gl": "ID", "ceid": "ID:id"
        })
        try:
            response = http_get(rss_url, timeout=TIMEOUT)
            parsed_feed = feedparser.parse(response.content)
            succeeded += 1
            for entry in parsed_feed.entries:
                title = clean_text(entry.get("title", ""), 250)
                summary = clean_text(entry.get("summary", "") or entry.get("description", ""), 900)
                if not is_vacancy_relevant(title, summary):
                    continue
                publisher = clean_text((entry.get("source") or {}).get("title") or "Google News RSS", 100)
                published = entry.get("published") or entry.get("updated")
                image_url = find_flyer_url(entry)
                body_html = entry.get("summary", "") or entry.get("description", "") or ""
                social_links = extract_social_links(body_html)
                record = make_record(
                    title=title,
                    body=summary,
                    url=entry.get("link", ""),
                    source_name=publisher,
                    source_type="rss_search",
                    published=published,
                    updated=entry.get("updated"),
                    location_hint=item.get("hint"),
                    image_url=image_url,
                    query=item.get("q"),
                )
                if social_links:
                    record["social_links"] = list(dict.fromkeys(record["social_links"] + social_links))
                    record["quality_score"], record["quality_label"], record["quality_explanation"] = quality(record)
                records.append(record)
        except Exception as exc:
            errors += 1
            log.warning("RSS search failed (%s): %s", item["q"], exc, exc_info=True)
        if index % 10 == 0:
            log.info("Google News RSS query batch: %s/%s", index, len(selected))
        time.sleep(0.12)
    stats = {
        "attempted": len(selected),
        "succeeded": succeeded,
        "errors": errors,
        "records": len(records),
        "query_pool_size": len(pool),
        "batch_start": start,
    }
    return records, stats


def extract_api_jobs(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "data", "results", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def value_from(item: dict, *keys, default=None):
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return default


def location_is_eligible(location: str, allow_missing: bool = False) -> tuple[bool, bool]:
    text = clean_text(location).lower()
    if not text:
        return allow_missing, allow_missing
    eligible_terms = [
        "indonesia", "worldwide", "anywhere", "any location", "global", "work from anywhere",
        "all countries", "asia", "apac", "remote - global", "remote globally",
    ]
    if any(term in text for term in eligible_terms):
        return True, True
    return False, False


def fetch_public_api_records() -> tuple[list[dict], dict]:
    records = []
    stats = {}
    sources = [
        ("jobicy", "https://jobicy.com/api/v2/remote-jobs", {"count": 200, "geo": "apac"}),
        ("remoteok", "https://remoteok.com/api", None),
        ("himalayas", "https://himalayas.app/jobs/api", {"limit": 20}),
    ]
    source_labels = {
        "jobicy": "Jobicy API",
        "remoteok": "Remote OK API",
        "himalayas": "Himalayas API",
    }

    for source_name, endpoint, params in sources:
        try:
            if source_name == "himalayas":
                # Himalayas caps pages at 20 and requires its nextCursor to be passed
                # through unchanged. Keep this bounded to three pages per run.
                items = []
                cursor = None
                raw_count = 0
                for _page in range(3):
                    page_params = {"limit": 20}
                    if cursor:
                        page_params["cursor"] = cursor
                    response = http_get(endpoint, params=page_params)
                    payload = response.json()
                    page_items = extract_api_jobs(payload)
                    raw_count += len(page_items)
                    items.extend(page_items)
                    cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
                    if not cursor or not page_items:
                        break
            else:
                response = http_get(endpoint, params=params)
                payload = response.json()
                items = extract_api_jobs(payload)
                raw_count = len(items)
                if source_name == "remoteok" and items and isinstance(items[0], dict) and ("legal" in items[0] or "terms" in items[0]):
                    items = items[1:]

            count_before = len(records)
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = value_from(item, "title", "jobTitle", "job_title", "position", "name")
                provider_url = value_from(item, "url", "job_url", "jobUrl", "link")
                if source_name == "himalayas":
                    guid = value_from(item, "guid")
                    if guid and str(guid).startswith(("https://", "http://")):
                        provider_url = guid
                    elif guid and str(guid).startswith("/"):
                        provider_url = "https://himalayas.app" + str(guid)
                if not title or not provider_url or not safe_public_url(str(provider_url)):
                    continue

                body = value_from(item, "description", "job_description", "jobDescription", "jobExcerpt", "excerpt", "summary", default="")
                location = value_from(
                    item, "candidate_required_location", "jobGeo", "location", "job_location", "locations",
                    "geo", "location_name", default=""
                )
                if isinstance(location, list):
                    location = ", ".join(clean_text(x) for x in location)
                if isinstance(location, dict):
                    location = ", ".join(clean_text(x) for x in location.values())
                location = clean_text(location, 250)

                if source_name == "himalayas":
                    restrictions = value_from(item, "locationRestrictions", "location_restrictions", default=[])
                    if isinstance(restrictions, str):
                        restrictions = [restrictions]
                    restriction_values = [clean_text(x).lower() for x in restrictions or []]
                    restriction_text = " ".join(restriction_values)
                    eligible_country = any(
                        value in ("id", "idn", "indonesia") or
                        any(term in value for term in ("indonesia", "worldwide", "anywhere", "global"))
                        for value in restriction_values
                    )
                    if restriction_text and not eligible_country:
                        continue
                    timezone_restrictions = value_from(item, "timezoneRestrictions", "timezone_restrictions", default=[])
                    if isinstance(timezone_restrictions, str):
                        timezone_restrictions = [timezone_restrictions]
                    timezone_text = " ".join(clean_text(x) for x in timezone_restrictions or []).lower()
                    if timezone_text:
                        indonesia_time_match = any(term in timezone_text for term in ("utc+7", "utc +7", "utc+07", "gmt+7", "+07", "7:00", "asia/jakarta"))
                        if not indonesia_time_match:
                            continue
                    eligible = True
                    broad = not restriction_text
                    if not location:
                        location = "Worldwide / Remote" if broad else restriction_text
                else:
                    # Jobicy is queried for APAC. Remote OK is a remote-only feed;
                    # unknown location remains visible as global eligibility unverified.
                    eligible, broad = location_is_eligible(
                        location,
                        allow_missing=(source_name in ("jobicy", "remoteok")),
                    )
                    if not eligible:
                        continue

                company = value_from(item, "company_name", "companyName", "company", "employer", "organization")
                published = value_from(item, "publication_date", "pubDate", "date", "pub_date", "published_at", "created_at")
                updated = value_from(item, "updated_at", "updated", "last_updated", default=published)
                salary_currency = value_from(item, "salaryCurrency", "salary_currency", "currency")
                salary_period = value_from(item, "salaryPeriod", "salary_period", "salary_frequency", "pay_period")
                salary_min = value_from(item, "salaryMin", "salary_min", "min_salary", "minSalary")
                salary_max = value_from(item, "salaryMax", "salary_max", "max_salary", "maxSalary")
                salary_text = value_from(item, "salary", "salary_text", "compensation")
                if not salary_text and (salary_min is not None or salary_max is not None):
                    currency_prefix = (str(salary_currency) + " ") if salary_currency else ""
                    range_text = " - ".join(str(x) for x in (salary_min, salary_max) if x is not None)
                    salary_text = currency_prefix + range_text
                    if salary_period:
                        salary_text += " / " + str(salary_period)
                job_type = value_from(item, "job_type", "jobType", "employment_type", "employmentType", "type")
                if isinstance(job_type, list):
                    job_type = ", ".join(clean_text(x) for x in job_type)
                work_mode = value_from(item, "workplace_type", "workplaceType", "remote", "work_mode") or "Remote"
                if isinstance(work_mode, bool):
                    work_mode = "Remote" if work_mode else None
                apply_url = value_from(item, "applicationLink", "application_link", "apply_url", "application_url")
                # Jobicy's public url is its source listing. Himalayas requires the exact
                # applicationLink for Apply; never rewrite or substitute that URL.
                record = make_record(
                    title=clean_text(title, 250),
                    body=clean_text(body, 900),
                    url=str(provider_url),
                    application_url=str(apply_url) if apply_url else None,
                    source_name=source_labels[source_name],
                    source_type="public_api",
                    published=published,
                    updated=updated,
                    company=clean_text(company, 120) if company else None,
                    location=location,
                    salary_text=clean_text(salary_text, 100) if salary_text else None,
                    salary_currency=str(salary_currency) if salary_currency else None,
                    salary_period=str(salary_period) if salary_period else None,
                    salary_min_source=salary_min,
                    salary_max_source=salary_max,
                    employment_type=clean_text(job_type, 60) if job_type else None,
                    work_mode=clean_text(work_mode, 60) if work_mode else "Remote",
                    is_remote=True,
                )
                if broad and "indonesia" not in location.lower():
                    record["location_confidence"] = "source_declared"
                    record["location_label"] = "Remote / eligibility to be verified"
                    record["quality_score"], record["quality_label"], record["quality_explanation"] = quality(record)
                records.append(record)

            stats[source_name] = {
                "status": "ok", "items_received": raw_count,
                "records_accepted": len(records) - count_before,
            }
        except Exception as exc:
            stats[source_name] = {"status": "error", "error": str(exc)[:240]}
            log.warning("Public API source %s failed: %s", source_name, exc, exc_info=True)

    # Jooble is opt-in: the API key must be supplied by the repository owner.
    jooble_key = os.getenv("JOOBLE_API_KEY", "").strip()
    if jooble_key:
        try:
            endpoint = "https://jooble.org/api/" + jooble_key
            response = SESSION.post(
                endpoint,
                json={"keywords": "lowongan kerja", "location": "Indonesia"},
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            items = extract_api_jobs(response.json())
            count_before = len(records)
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = value_from(item, "title")
                url = value_from(item, "link", "url")
                if not title or not url or not safe_public_url(str(url)):
                    continue
                body = value_from(item, "snippet", "description", default="")
                location = value_from(item, "location", default="Indonesia")
                record = make_record(
                    title=title, body=body, url=str(url), application_url=str(url),
                    source_name="Jooble API", source_type="public_api",
                    published=value_from(item, "updated", "date"),
                    updated=value_from(item, "updated", "date"),
                    company=value_from(item, "company"),
                    location=str(location),
                    salary_text=value_from(item, "salary"),
                )
                records.append(record)
            stats["jooble"] = {"status": "ok", "items_received": len(items), "records_accepted": len(records) - count_before}
        except Exception as exc:
            stats["jooble"] = {"status": "error", "error": str(exc)[:240]}
            log.warning("Jooble API failed: %s", exc)
    else:
        stats["jooble"] = {"status": "skipped", "reason": "JOOBLE_API_KEY not configured"}

    # Adzuna is optional because country support depends on the account/API availability.
    adzuna_id = os.getenv("ADZUNA_APP_ID", "").strip()
    adzuna_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if adzuna_id and adzuna_key:
        try:
            endpoint = "https://api.adzuna.com/v1/api/jobs/id/search/1"
            response = http_get(endpoint, params={
                "app_id": adzuna_id, "app_key": adzuna_key,
                "results_per_page": 50, "what": "lowongan kerja",
                "where": "Indonesia", "content-type": "application/json",
            })
            items = extract_api_jobs(response.json())
            count_before = len(records)
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = value_from(item, "title")
                url = value_from(item, "redirect_url", "url")
                if not title or not url or not safe_public_url(str(url)):
                    continue
                company_obj = item.get("company") or {}
                location_obj = item.get("location") or {}
                loc = value_from(location_obj, "display_name", default="Indonesia") if isinstance(location_obj, dict) else location_obj
                salary = None
                if item.get("salary_min") is not None or item.get("salary_max") is not None:
                    salary = f'{item.get("salary_min", "")} - {item.get("salary_max", "")}'.strip(" -")
                records.append(make_record(
                    title=title, body=value_from(item, "description", default=""),
                    url=str(url), application_url=str(url), source_name="Adzuna API",
                    source_type="public_api", published=value_from(item, "created"),
                    updated=value_from(item, "created"),
                    company=value_from(company_obj, "display_name") if isinstance(company_obj, dict) else company_obj,
                    location=str(loc), salary_text=salary,
                ))
            stats["adzuna"] = {"status": "ok", "items_received": len(items), "records_accepted": len(records) - count_before}
        except Exception as exc:
            stats["adzuna"] = {"status": "error", "error": str(exc)[:240]}
            log.warning("Adzuna API unavailable or country unsupported: %s", exc)
    else:
        stats["adzuna"] = {"status": "skipped", "reason": "Adzuna credentials not configured"}
    return records, stats

def fetch_approved_rss() -> tuple[list[dict], dict]:
    config = read_json(APPROVED_FEEDS_FILE, {"feeds": []})
    records = []
    sources = {}
    feeds = config.get("feeds", []) if isinstance(config, dict) else []
    for feed in feeds:
        name = clean_text(feed.get("name") or "Approved RSS feed", 100)
        url = clean_url(feed.get("url"))
        if not url or not safe_public_url(url):
            sources[name] = {"status": "skipped", "reason": "Invalid/public URL required"}
            continue
        try:
            response = http_get(url)
            parsed_feed = feedparser.parse(response.content)
            before = len(records)
            hint = {"city": feed.get("city"), "province": feed.get("province")}
            for entry in parsed_feed.entries:
                title = clean_text(entry.get("title", ""), 250)
                summary_html = entry.get("summary", "") or entry.get("description", "") or ""
                summary = clean_text(summary_html, 900)
                if not title or not is_vacancy_relevant(title, summary):
                    continue
                image_url = find_flyer_url(entry)
                body = summary + (" " + clean_text(summary_html) if summary_html else "")
                item_url = clean_url(entry.get("link")) or url
                records.append(make_record(
                    title=title, body=body, url=item_url,
                    application_url=entry.get("link"), source_name=name,
                    source_type="approved_feed",
                    published=entry.get("published") or entry.get("updated"),
                    updated=entry.get("updated"),
                    company=feed.get("company"),
                    location=feed.get("location"),
                    location_hint=hint, image_url=image_url,
                    query="approved RSS feed",
                ))
            sources[name] = {"status": "ok", "items_accepted": len(records) - before}
        except Exception as exc:
            sources[name] = {"status": "error", "error": str(exc)[:240]}
            log.warning("Approved feed %s failed: %s", name, exc)
    return records, sources


def merge_records(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {str(job.get("id") or make_id(job.get("listing_url", ""), job.get("title", ""), job.get("company_name", ""), job.get("city", ""))): job for job in existing if isinstance(job, dict)}
    for new in incoming:
        key = str(new.get("id") or make_id(new.get("listing_url", ""), new.get("title", ""), new.get("company_name", ""), new.get("city", "")))
        old = merged.get(key)
        if not old:
            merged[key] = new
            continue
        combined = dict(old)
        for field, value in new.items():
            if value is None or value == "" or value == []:
                continue
            if field in ("social_links", "risk_flags", "quality_explanation"):
                combined[field] = list(dict.fromkeys((old.get(field) or []) + (value or [])))
            elif field == "first_seen_at":
                combined[field] = old.get(field) or value
            else:
                combined[field] = value
        combined["first_seen_at"] = old.get("first_seen_at") or new.get("first_seen_at")
        combined["last_seen_at"] = iso_now()
        combined["last_checked_at"] = iso_now()
        # Re-score after old fields are combined.
        combined["risk_flags"] = list(dict.fromkeys((old.get("risk_flags") or []) + (new.get("risk_flags") or [])))
        score, label, reasons = quality(combined)
        combined["quality_score"] = score
        combined["quality_label"] = label
        combined["quality_explanation"] = reasons
        merged[key] = combined
    return list(merged.values())


def update_listing_states(jobs: list[dict]) -> list[dict]:
    current = now_utc()
    output = []
    for job in jobs:
        published_age = date_age_days(job.get("source_updated_at") or job.get("published_at"))
        last_seen_age = date_age_days(job.get("last_seen_at"))
        if job.get("application_deadline"):
            deadline_age = date_age_days(job.get("application_deadline"))
            # A parsed deadline in the past should not be promoted as open.
            try:
                deadline_dt = datetime.fromisoformat(job["application_deadline"].replace("Z", "+00:00"))
                if deadline_dt < current:
                    job["listing_state"] = "deadline_passed"
                elif job.get("listing_state") != "deadline_passed":
                    job["listing_state"] = "active_unverified"
            except Exception:
                pass
        elif (published_age is not None and published_age > 45) or (published_age is None and last_seen_age is not None and last_seen_age > 21):
            job["listing_state"] = "stale"
        else:
            job["listing_state"] = "active_unverified"
        # Keep stale listings for historical filtering, but purge very old records.
        if (last_seen_age is not None and last_seen_age > RETENTION_DAYS) or (published_age is not None and published_age > RETENTION_DAYS * 2):
            continue
        output.append(job)
    output.sort(key=lambda item: (
        item.get("last_seen_at") or "",
        item.get("source_updated_at") or "",
        item.get("title") or "",
    ), reverse=True)
    return output


def main() -> int:
    started_at = iso_now()
    log.info("Starting Info Loker collector; batch size=%s; OCR=%s", QUERY_BATCH_SIZE, OCR_ENABLED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    previous_payload = read_json(JOBS_FILE, {"schema_version": "1.0", "jobs": []})
    existing = previous_payload.get("jobs", []) if isinstance(previous_payload, dict) else []
    if not isinstance(existing, list):
        existing = []

    rss_records, rss_stats = fetch_google_news(QUERY_BATCH_SIZE)
    api_records, api_stats = fetch_public_api_records()
    approved_records, approved_stats = fetch_approved_rss()
    incoming = rss_records + api_records + approved_records

    merged = merge_records(existing, incoming)
    merged = update_listing_states(merged)
    generated_at = iso_now()
    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "timezone": "Asia/Jakarta",
        "total": len(merged),
        "fresh_seen_in_this_run": len(incoming),
        "jobs": merged,
    }
    write_json(JOBS_FILE, payload)

    label_counts = {"HOT": 0, "MEDIUM": 0, "LOW": 0}
    state_counts = {}
    for job in merged:
        label = job.get("quality_label", "LOW")
        label_counts[label] = label_counts.get(label, 0) + 1
        state = job.get("listing_state", "unknown")
        state_counts[state] = state_counts.get(state, 0) + 1

    status = {
        "status": "ok" if incoming or (rss_stats.get("succeeded", 0) > 0) else "partial",
        "started_at": started_at,
        "finished_at": generated_at,
        "timezone": "Asia/Jakarta",
        "sources": {
            "google_news_rss": rss_stats,
            "public_apis": api_stats,
            "approved_rss": approved_stats,
        },
        "records_received_this_run": len(incoming),
        "records_after_deduplication": len(merged),
        "quality_label_counts": label_counts,
        "listing_state_counts": state_counts,
        "flyer_ocr_attempted": OCR_COUNTER,
        "configuration": {
            "query_batch_size": QUERY_BATCH_SIZE,
            "query_pool_size": len(query_pool()),
            "retention_days": RETENTION_DAYS,
            "flyer_ocr_enabled": OCR_ENABLED,
            "max_flyer_ocr_per_run": MAX_OCR_PER_RUN,
        },
        "notes": [
            "HOT/MEDIUM/LOW is an information-quality and freshness estimate, not a guarantee of employer legitimacy.",
            "Google News RSS results link to original publishers; not every linked page is crawled.",
            "Records without a source date or full details remain visible but should be verified by applicants.",
        ],
    }
    write_json(STATUS_FILE, status)
    log.info("Finished: %s incoming, %s total records", len(incoming), len(merged))
    log.info("Quality label counts: %s", label_counts)
    return 0 if status["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
