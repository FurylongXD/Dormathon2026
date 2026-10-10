"""Reviewed facts plus bounded retrieval from an official-source allowlist.

Live HTML is evidence for review; it never silently changes a rate or policy.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, date
from html.parser import HTMLParser
import json
import re
import urllib.request
from urllib.parse import urlparse
from .client import NoRedirect, ServiceError


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip = 0; self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}: self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}: self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip(): self.parts.append(data.strip())


def fetch_official(source):
    url = source["url"]
    host = urlparse(url).hostname
    allowed = {"www.maybank2u.com.my", "www.cimb.com.my", "www.pbebank.com", "www.bnm.gov.my",
               "www.rhbgroup.com", "www.hlb.com.my", "www.ambank.com.my"}
    if urlparse(url).scheme != "https" or host not in allowed:
        raise ServiceError("SOURCE_NOT_ALLOWED", "This source is outside the official bank allowlist.", 400)
    req = urllib.request.Request(url, headers={"User-Agent": "LoanPolicyDemo/3.0", "Accept": "text/html"})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=12) as response:
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            raise ValueError("Expected HTML")
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000: raise ValueError("Oversized page")
        charset = response.headers.get_content_charset() or "utf-8"
    parser = TextParser(); parser.feed(raw.decode(charset, errors="replace"))
    return re.sub(r"\s+", " ", " ".join(parser.parts))[:160000]


class KnowledgeBase:
    def __init__(self, settings, fetcher=None):
        self.settings = settings
        self.data = json.loads(settings.knowledge_path.read_text(encoding="utf-8"))
        self.sources = {s["id"]: s for s in self.data["sources"]}
        self.fetcher = fetcher or fetch_official

    def select(self, question="", loan_type="all", banks=None, limit=12):
        if loan_type not in {"all", "car", "home", "personal"}:
            raise ServiceError("INVALID_LOAN_TYPE", "Choose car, home, personal or all.", 400)
        banks = banks or ["maybank", "cimb", "public_bank"]
        if not banks or len(banks) > 3 or any(b not in {"maybank", "cimb", "public_bank"} for b in banks):
            raise ServiceError("INVALID_BANK", "Supported banks: maybank, cimb, public_bank.", 400)
        tokens = set(re.findall(r"[a-z]{3,}", question.lower()))
        rows = [f for f in self.data["facts"] if (f["bank"] in banks or f["bank"] == "bnm")
                and (loan_type == "all" or f["loan_type"] in {loan_type, "all"})]
        def score(f):
            words = set(re.findall(r"[a-z]{3,}", f["display"].lower() + " " + " ".join(f.get("keywords", []))))
            return len(tokens & words)
        rows.sort(key=score, reverse=True)
        return {f["id"]: f for f in rows[:limit]}

    def source_cards(self, ids):
        today = date.today()
        cards = []
        for sid in sorted(set(ids)):
            s = dict(self.sources[sid])
            days = (today - date.fromisoformat(s["reviewed_on"])).days
            s.update({"days_since_review": days, "review_due": days > 30,
                      "status": "reviewed_snapshot", "live_fetch_does_not_revalidate_numbers": True})
            cards.append(s)
        return cards

    def banks(self, loan_type="all", banks=None):
        self.select(loan_type=loan_type, banks=banks)  # shared argument validation
        result = []
        for card in self.data["bank_cards"]:
            if (loan_type == "all" or card["loan_type"] == loan_type) and (not banks or card["bank_id"] in banks):
                result.append({**card, "sources": self.source_cards(card["source_ids"])})
        return {"cards": result, "scope": self.data["scope"],
                "rate_ranking": "No advertised-rate winner: quoted rates, fees, tenor, eligibility and calculation basis must be compared together."}

    def _live_source(self, source):
        path = self.settings.cache_dir / (source["id"] + ".json")
        cached = None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            elapsed = datetime.now(timezone.utc).timestamp() - cached["fetched_at_epoch"]
            if 0 <= elapsed < 3600: return {**cached, "fetch_status": "cached"}
        except (OSError, ValueError, KeyError, TypeError): pass
        try:
            text = self.fetcher(source)
            if not isinstance(text, str) or not text.strip(): raise ValueError("Empty page")
            now = datetime.now(timezone.utc)
            result = {"source_id": source["id"], "url": source["url"], "fetched_at": now.isoformat(),
                      "fetched_at_epoch": now.timestamp(), "fetch_status": "fetched", "text": text[:160000],
                      "trust": "unreviewed_live_page"}
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Cache contains public pages only. Concurrent identical writes use distinct temporary files.
                import tempfile, os
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                    json.dump(result, handle); temporary = handle.name
                os.replace(temporary, path)
            except OSError: pass
            return result
        except Exception:
            # Third-party exception strings can echo network paths/content; return a fixed error.
            if cached: return {**cached, "fetch_status": "stale_cache", "refresh_error": "PUBLIC_SOURCE_UNAVAILABLE"}
            return {"source_id": source["id"], "url": source["url"], "fetch_status": "unavailable",
                    "refresh_error": "PUBLIC_SOURCE_UNAVAILABLE", "trust": "no_live_evidence"}

    def live(self, facts, question):
        ids = list(dict.fromkeys(s for f in facts.values() for s in f["source_ids"]))[:4]
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(self._live_source, [self.sources[s] for s in ids]))
        tokens = set(re.findall(r"[a-z]{3,}", question.lower()))
        for row in rows:
            text = row.pop("text", "")
            sentences = re.split(r"(?<=[.!?])\s+", text)
            sentences.sort(key=lambda s: len(tokens & set(re.findall(r"[a-z]{3,}", s.lower()))), reverse=True)
            row["excerpt"] = " ".join(sentences[:3])[:2000]
            row.pop("fetched_at_epoch", None)
        return rows
