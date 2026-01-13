import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Set
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

BASE_DOMAINS = {"www.kmetija-urska.si", "shop.kmetija-urska.si"}
SITEMAP_INDEX = ""
OUTPUT_PATH = Path("knowledge.jsonl")
SEED_URLS = [
    "https://www.kmetija-urska.si/kulinarika/",
    "https://www.kmetija-urska.si/wellness/",
    "https://www.kmetija-urska.si/druzina/",
    "https://www.kmetija-urska.si/namestitev/",
    "https://www.kmetija-urska.si/cenik/",
    "https://www.kmetija-urska.si/kontakt/",
    "https://shop.kmetija-urska.si/trgovina/",
    "https://shop.kmetija-urska.si/product/darilni-bon-100-eur",
    "https://shop.kmetija-urska.si/product/leseni-noz-za-maslo/",
]
HEADERS = {
    "User-Agent": "UrskaRAGBot/1.0 (+https://www.kmetija-urska.si)"
}
REQUEST_TIMEOUT = 20
PAUSE_SECONDS = 0.5


@dataclass
class PageData:
    url: str
    title: str
    content: str
    fetched_at: str


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_url(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_sitemap(xml_content: str) -> List[str]:
    urls: List[str] = []
    root = ET.fromstring(xml_content)
    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    if root.tag.endswith("sitemapindex"):
        for sitemap in root.findall(f"{namespace}sitemap"):
            loc = sitemap.find(f"{namespace}loc")
            if loc is not None and loc.text:
                urls.extend(parse_sitemap(fetch_url(loc.text)))
    else:
        for url in root.findall(f"{namespace}url"):
            loc = url.find(f"{namespace}loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
    return urls


def filter_domain(urls: Iterable[str], domains: Set[str]) -> List[str]:
    filtered: List[str] = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.netloc in domains:
            filtered.append(url)
    return filtered


def extract_content(url: str) -> PageData:
    html = fetch_url(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "form"]):
        tag.decompose()
    title_tag = soup.find("h1") or soup.find("title")
    title = clean_text(title_tag.get_text()) if title_tag else url
    main = soup.find("main") or soup.body
    text = clean_text(main.get_text(separator=" ")) if main else clean_text(soup.get_text())
    return PageData(
        url=url,
        title=title,
        content=text,
        fetched_at=datetime.utcnow().isoformat(),
    )


def scrape_all() -> List[PageData]:
    urls: List[str]
    if SITEMAP_INDEX:
        print("Fetching sitemap index...")
        raw_urls = parse_sitemap(fetch_url(SITEMAP_INDEX))
        urls = sorted(set(filter_domain(raw_urls, BASE_DOMAINS)))
        print(f"Found {len(urls)} URLs in sitemap")
    else:
        urls = list(dict.fromkeys(SEED_URLS))
        print(f"Using {len(urls)} seed URLs")
    pages: List[PageData] = []
    for idx, url in enumerate(urls, start=1):
        try:
            page = extract_content(url)
            pages.append(page)
            print(f"[{idx}/{len(urls)}] scraped {url}")
        except Exception as exc:
            print(f"[{idx}/{len(urls)}] failed {url}: {exc}")
            pages.append(
                PageData(
                    url=url,
                    title="ERROR",
                    content=f"Failed to fetch content: {exc}",
                    fetched_at=datetime.utcnow().isoformat(),
                )
            )
        time.sleep(PAUSE_SECONDS)
    return pages


def write_jsonl(pages: List[PageData], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for page in pages:
            json.dump(page.__dict__, f, ensure_ascii=False)
            f.write("\n")
    print(f"Wrote {len(pages)} records to {path}")


if __name__ == "__main__":
    data = scrape_all()
    write_jsonl(data, OUTPUT_PATH)
