#!/usr/bin/env python3
"""Collect leads for the brief. Candidate headlines require independent verification."""

import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


KST = timezone(timedelta(hours=9))
DEFAULT_OUT = Path("/tmp/kg-tj-brief-candidates/korea_candidates.json")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
MAX_FETCH_SECONDS = 85
MAX_RESPONSE_BYTES = 2_000_000
SOURCE_NAMES = {
    "google_news_ko": "Google News",
    "google_news_en": "Google News",
    "korea_kr": "정책브리핑",
    "mofa": "외교부",
    "motie": "산업통상부",
    "yna": "연합뉴스",
}
GOOGLE_QUERIES = {
    "google_news_ko": ("ko", "KR", "KR:ko", (
        "키르기스스탄 when:2d", "타지키스탄 when:2d",
        "키르기스 한국 when:2d", "타지키스탄 한국 대사 when:2d",
    )),
    "google_news_en": ("en-US", "US", "US:en", (
        '"Kyrgyzstan" Korea when:2d', '"Tajikistan" Korea when:2d', "Kyrgyz Korean when:2d",
    )),
}
KOREAN_KEYWORDS = ("키르기스", "타지키스탄", "타지크", "비슈케크", "두샨베")
KOREAN_CONTEXT = re.compile(
    r"한국|한\s*[-‐–—·ㆍ]|한\s*[.․]\s*중앙아시아|韓|정부|부처|외교부|산업(?:통상(?:자원)?)?부|"
    r"기획재정부|재정경제부|국토교통부|중기부|무역협회|수출입은행|"
    r"삼성|현대|기아|롯데|포스코|한화|두산|효성|코오롱|네이버|카카오|쿠팡|"
    r"\b(?:KOTRA|KOICA|SK|LG|POSCO|CJ|GS|KT|LS)(?=[^a-zA-Z0-9]|$)",
    re.IGNORECASE,
)
ENGLISH_KEYWORDS = re.compile(
    r"\b(?:(Kyrgyz)(?:stan(?:i)?s?|s)?|(Tajik)(?:istan(?:i)?s?|s)?|(Bishkek|Dushanbe))\b",
    re.IGNORECASE,
)
ENGLISH_CONTEXT = re.compile(r"\b(?:Korea|Koreans?|Seoul)\b", re.IGNORECASE)
LIST_DATE = re.compile(r"\d{4}[-.]\d{2}[-.]\d{2}")
BOARD_PATHS = {
    "korea_kr": re.compile(r"/briefing/pressReleaseView\.do"),
    "mofa": re.compile(r"/(?:www/)?brd/(?:m_)?4080/view\.do"),
    "motie": re.compile(r"/kor/article/ATCL3f49a5a8c/\d+/view"),
}
BOARD_ID_KEYS = {"korea_kr": "newsId", "mofa": "seq"}


@dataclass
class Article:
    title: str
    url: str
    source: str
    published: str = ""


class FeedFormatError(ValueError):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid arguments")


def source_requests():
    for origin, (language, country, edition, queries) in GOOGLE_QUERIES.items():
        for index, query in enumerate(queries, 1):
            params = urlencode(dict(q=query, hl=language, gl=country, ceid=edition))
            yield origin, f"query{index}", f"https://news.google.com/rss/search?{params}"

    # Korea.kr discontinued RSS on 2026-07-01. Use its official release lists.
    policy = "https://www.korea.kr/briefing/pressReleaseList.do"
    yield "korea_kr", "list", policy
    yield "korea_kr", "page2", f"{policy}?pageIndex=2"
    yield "korea_kr", "departments", f"{policy}?repCode=A00014%2CA00015"
    mofa = "https://www.mofa.go.kr/www/brd/m_4080/list.do"
    yield "mofa", "list", mofa
    yield "mofa", "list50", f"{mofa}?pitem=50"
    # motie.go.kr redirects to the ministry's current motir.go.kr site.
    yield "motie", "list", "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c"
    for section in ("news", "politics", "economy"):
        yield "yna", section, f"https://www.yna.co.kr/rss/{section}.xml"


def clean_text(value):
    return " ".join(value.split())


def public_url(base_url, value):
    if not value.strip():
        return ""
    try:
        url = urljoin(base_url, value.strip())
        parts = urlsplit(url)
        if parts.scheme in {"http", "https"} and parts.hostname and parts.username is None:
            return url
    except ValueError:
        pass
    return ""


def rss_articles(data, base_url, origin):
    root = ET.fromstring(data)
    channel = root.find("./{*}channel")
    if root.tag.rsplit("}", 1)[-1] != "rss" or channel is None:
        raise FeedFormatError("missing RSS channel")

    articles = []
    for item in channel.findall("./{*}item"):
        title = clean_text(unescape(item.findtext("{*}title", "")))
        url = public_url(base_url, item.findtext("{*}link", ""))
        if not title or not url:
            continue
        source = item.find("{*}source")
        publisher = ""
        if source is not None:
            publisher = clean_text(unescape("".join(source.itertext())))
            if publisher and title.endswith(f" - {publisher}"):
                title = title.removesuffix(f" - {publisher}")
            if not publisher:
                publisher_url = public_url(base_url, source.get("url", ""))
                publisher = urlsplit(publisher_url).hostname or ""
        published = item.findtext("{*}pubDate") or item.findtext("{*}date", "")
        articles.append(Article(title, url, publisher or SOURCE_NAMES[origin], published))
    return articles


class PressListParser(HTMLParser):
    """Read rows from ministry tables and headline cards from Korea.kr."""

    def __init__(self, base_url, origin):
        super().__init__()
        self.base_url = base_url
        self.origin = origin
        self.policy = origin == "korea_kr"
        self.articles = []
        self.article = None
        self.field = ""

    def article_url(self, href):
        url = public_url(self.base_url, href)
        parts = urlsplit(url)
        if not BOARD_PATHS[self.origin].fullmatch(parts.path):
            return ""
        key = BOARD_ID_KEYS.get(self.origin)
        if key:
            article_id = parse_qs(parts.query).get(key, [""])[0]
            if article_id.isdigit():
                return parts._replace(query=urlencode({key: article_id}), fragment="").geturl()
            return ""
        return parts._replace(query="", fragment="").geturl()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and not self.policy:
            self.article = Article("", "", SOURCE_NAMES[self.origin])
            self.field = ""
        if tag == "a" and (self.policy or self.article is not None):
            url = self.article_url(attrs.get("href") or "")
            if url:
                if self.policy:
                    self.article = Article("", url, SOURCE_NAMES[self.origin])
                else:
                    self.article.url = url
                    self.field = "title"

        if self.article is None:
            return
        if self.policy:
            if tag == "strong":
                self.field = "title"
            elif tag == "span" and "source" in (attrs.get("class") or "").split():
                self.field = "metadata"
        elif tag == "time" and attrs.get("datetime") and self.field != "title":
            self.article.published = attrs["datetime"]

    def handle_endtag(self, tag):
        if (self.policy and tag == "strong") or (not self.policy and tag == "a"):
            self.field = ""
        if tag != ("a" if self.policy else "tr") or self.article is None:
            return
        self.article.title = clean_text(self.article.title)
        if self.article.url and self.article.title:
            self.articles.append(self.article)
        self.article = None
        self.field = ""

    def handle_data(self, data):
        if self.article is None:
            return
        if self.field == "title":
            self.article.title += data
            return
        value = clean_text(data)
        if not value or (self.policy and self.field != "metadata"):
            return
        if LIST_DATE.fullmatch(value) and not self.article.published:
            self.article.published = value
        elif self.policy and self.article.published:
            self.article.source = value


def fetch_articles(url, origin, timeout):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_RESPONSE_BYTES + 1)
        base_url = response.geturl()
        charset = response.headers.get_content_charset() or "utf-8"
    if len(data) > MAX_RESPONSE_BYTES:
        raise FeedFormatError("response too large")
    if origin not in BOARD_PATHS:
        return rss_articles(data, base_url, origin)
    parser = PressListParser(base_url, origin)
    parser.feed(data.decode(charset, errors="replace"))
    parser.close()
    if not parser.articles:
        raise FeedFormatError("release list has no recognized rows")
    return parser.articles


def matched_keywords(title, origin):
    if origin == "google_news_en":
        if not ENGLISH_CONTEXT.search(title):
            return []
        matches = ENGLISH_KEYWORDS.findall(title)
        return list(dict.fromkeys((kyrgyz or tajik or city).capitalize() for kyrgyz, tajik, city in matches))
    matches = [word for word in KOREAN_KEYWORDS if word in title]
    if "중앙아시아" in title and KOREAN_CONTEXT.search(title):
        matches.append("중앙아시아")
    return matches


def local_time(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def iso_time(value):
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return local_time(datetime.fromisoformat(value))


def publication_date(value):
    value = value.strip()
    if not value:
        return None
    try:
        if LIST_DATE.fullmatch(value):
            return date.fromisoformat(value.replace(".", "-"))
        try:
            return iso_time(value)
        except ValueError:
            return local_time(parsedate_to_datetime(value))
    except (TypeError, ValueError, OverflowError):
        return None


def candidates_for(articles, origin, cutoff, now):
    for article in articles:
        matches = matched_keywords(article.title, origin)
        if not matches:
            continue
        published = publication_date(article.published)
        published_at = ""
        sort_time = datetime.min.replace(tzinfo=KST)
        if isinstance(published, datetime):
            if not cutoff <= published <= now:
                continue
            sort_time = published
            published_at = published.isoformat()
        elif published is not None:
            if not cutoff.date() <= published <= now.date():
                continue
            # Keep releases that might be in the window without inventing a time.
            sort_time = datetime.combine(published, time.min, KST)
        yield sort_time, {
            "title": article.title,
            "url": article.url,
            "source": article.source,
            "publishedAt": published_at,
            "matched": matches,
            "origin": origin,
        }


def error_label(error):
    # Raw exceptions can contain request details or filesystem paths.
    if isinstance(error, HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, URLError):
        error = error.reason
    return type(error).__name__


def collect(result, cutoff, now, limit, timeout):
    requests = list(source_requests())
    budget = min(timeout, MAX_FETCH_SECONDS)
    deadline = monotonic() + budget
    executor = ThreadPoolExecutor(max_workers=len(requests))
    jobs = []
    try:
        for origin, label, url in requests:
            future = executor.submit(fetch_articles, url, origin, budget)
            jobs.append((origin, label, future))
        done, pending = wait([job[2] for job in jobs], timeout=max(0, deadline - monotonic()))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    entries = []
    source_urls = {origin: set() for origin in SOURCE_NAMES}
    for origin, label, future in jobs:
        status = result["sources"][origin]
        try:
            if future not in done:
                raise TimeoutError
            matches = list(candidates_for(future.result(), origin, cutoff, now))
            entries.extend(matches)
            source_urls[origin].update(item["url"] for _, item in matches)
            status["ok"] = True
        except Exception as error:
            status["error"] += f"{label}: {error_label(error)}, "

    for origin, status in result["sources"].items():
        status["count"] = len(source_urls[origin])
        status["error"] = status["error"].removesuffix(", ")

    unique = {}
    for _, item in sorted(entries, key=lambda entry: entry[0], reverse=True):
        unique.setdefault(item["url"], item)
    result["candidates"] = list(unique.values())[:limit]
    return bool(pending)


def save_result(out, result):
    out.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=out.parent, delete=False) as temp:
            temp_path = Path(temp.name)
            json.dump(result, temp, ensure_ascii=False, indent=2)
            temp.write("\n")
        os.replace(temp_path, out)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hours", default="36")
    parser.add_argument("--max", dest="limit", default="30")
    parser.add_argument("--timeout", default="12")
    parser.add_argument("--now", metavar="ISO")

    now = datetime.now(KST)
    out = DEFAULT_OUT
    pending = False
    result = {
        "generatedAt": now.isoformat(timespec="seconds"),
        "windowHours": 36,
        "sources": {origin: {"ok": False, "count": 0, "error": ""} for origin in SOURCE_NAMES},
        "candidates": [],
    }
    stage = "arguments"
    try:
        args = parser.parse_args()
        out = args.out
        hours, limit, timeout = int(args.hours), int(args.limit), float(args.timeout)
        if hours <= 0 or limit < 0 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("invalid limits")
        if args.now:
            now = iso_time(args.now)
        cutoff = now - timedelta(hours=hours)
        result["generatedAt"] = now.isoformat(timespec="seconds")
        result["windowHours"] = hours
        stage = "collection"
        pending = collect(result, cutoff, now, limit, timeout)
    except (Exception, KeyboardInterrupt) as error:
        pending = stage == "collection"
        label = f"{stage}: {error_label(error)}"
        result["errors"] = [label]
        for status in result["sources"].values():
            if not status["ok"] and not status["error"]:
                status["error"] = label

    statuses = [f"{origin} {'ok' if status['ok'] else '실패'}"
                for origin, status in result["sources"].items()]
    try:
        save_result(out, result)
    except (Exception, KeyboardInterrupt) as error:
        result.setdefault("errors", []).append(f"output: {error_label(error)}")
        statuses.append("저장 실패")
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir="/tmp", delete=False,
                                    prefix="kg-tj-candidates-error-", suffix=".json") as fallback:
                json.dump(result, fallback, ensure_ascii=False, indent=2)
                fallback.write("\n")
            statuses.append(fallback.name)
        except (Exception, KeyboardInterrupt):
            pass
    try:
        print(f"한국 관련 후보 {len(result['candidates'])}건 ({', '.join(statuses)})", flush=True)
    except (OSError, KeyboardInterrupt):
        # Bypass the final flush if stdout was closed by a downstream process.
        pending = True
    return pending


if __name__ == "__main__":
    if main():
        # ThreadPoolExecutor joins its workers at interpreter exit. A stuck DNS
        # lookup or read must not keep the CLI alive after its result is saved.
        os._exit(0)
