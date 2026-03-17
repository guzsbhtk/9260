#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

INDEX_NAME = "מה הסיכוי שגדוד 9260 יוקפץ"
MANUAL_SIGNALS_FILE = "data/manual_signals.json"
BASELINE_CALIBRATION_OFFSET = 0.0
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_LLM_MAX_ARTICLES = 120

SIGNAL_RAW_AT_75 = {
    # Current observed intensity baseline (March 2026).
    # If raw grows beyond these levels, the score can rise above 75 up to 100.
    "fire_from_lebanon": 555.0,
    "idf_strikes_in_lebanon": 1452.0,
}

# Public RSS/Atom feeds chosen for robust daily polling.
FEEDS = {
    "google_news_en": "https://news.google.com/rss/search?q=Israel+Lebanon+IDF+reservists&hl=en-US&gl=US&ceid=US:en",
    "google_news_he": "https://news.google.com/rss/search?q=%D7%99%D7%A9%D7%A8%D7%90%D7%9C+%D7%9C%D7%91%D7%A0%D7%95%D7%9F+%D7%A6%D7%94%D7%9C+%D7%9E%D7%99%D7%9C%D7%95%D7%90%D7%99%D7%9D&hl=he&gl=IL&ceid=IL:he",
    "google_news_rocket_fire": "https://news.google.com/rss/search?q=Hezbollah+rockets+north+Israel+Lebanon&hl=en-US&gl=US&ceid=US:en",
    "google_news_division_36": "https://news.google.com/rss/search?q=%D7%90%D7%95%D7%92%D7%93%D7%94+36+%D7%9C%D7%91%D7%A0%D7%95%D7%9F&hl=he&gl=IL&ceid=IL:he",
    "google_news_brigade_282": "https://news.google.com/rss/search?q=%D7%97%D7%98%D7%99%D7%91%D7%94+282+%D7%9C%D7%91%D7%A0%D7%95%D7%9F&hl=he&gl=IL&ceid=IL:he",
    "google_news_battalion_9260": "https://news.google.com/rss/search?q=%D7%92%D7%93%D7%95%D7%93+9260+%D7%9C%D7%91%D7%A0%D7%95%D7%9F&hl=he&gl=IL&ceid=IL:he",
    "times_of_israel": "https://www.timesofisrael.com/feed/",
    "idf_news": "https://www.idf.il/rss/"
}

DIVISION_36_TERMS = [
    r"\b36th division\b",
    r"\bdivision 36\b",
    r"אוגדה\s*36",
    r"עוצבת\s*געש",
    r"gaash",
]

BRIGADE_282_TERMS = [
    r"\b282nd brigade\b",
    r"\bbrigade 282\b",
    r"\b282nd artillery brigade\b",
    r"חטיבה\s*282",
    r"תותחנים.*282",
    r"אש.*282",
]

BATTALION_9260_TERMS = [
    r"\b9260\b",
    r"\bbattalion 9260\b",
    r"\b9260 battalion\b",
    r"גדוד\s*9260",
    r"תותחנים.*9260",
    r"סוללה.*9260",
]

SIGNALS = {
    "fire_from_lebanon": {
        "weight": 0.18,
        "patterns": [
            r"rockets? from lebanon",
            r"hezbollah.*rockets?",
            r"rockets?.*north",
            r"fire on israel",
            r"missiles? from lebanon",
            r"drone.*from lebanon",
            r"mortar.*from lebanon",
            r"ירי.*מלבנון",
            r"ירי.*מתוך שטח לבנון",
            r"אש.*מלבנון",
            r"שיגור.*מלבנון",
            r"מטחים?.*לצפון",
            r"חילופי אש.*גבול הצפון",
            r"siren.*north",
            r"אזעקות?.*צפון",
            r"רקטות?.*חיזבאללה",
            r"שיגורים?.*לגליל",
        ],
    },
    "idf_strikes_in_lebanon": {
        "weight": 0.17,
        "patterns": [
            r"idf.*strike.*lebanon",
            r"airstrikes?.*lebanon",
            r"תקיפות?.*בלבנון",
            r"targets?.*hezbollah",
            r"מטרות?.*חיזבאללה",
        ],
    },
    "ground_campaign_indicators": {
        "weight": 0.17,
        "patterns": [
            r"ground operation",
            r"ground offensive",
            r"incursion",
            r"תמרון קרקעי",
            r"כניסה קרקעית",
            r"פעולה קרקעית",
        ],
    },
    "reserve_mobilization": {
        "weight": 0.15,
        "patterns": [
            r"reservists? called up",
            r"reserve division",
            r"צו\s*8",
            r"גיוס מילואים",
            r"מילואימניקים",
        ],
    },
    "decision_maker_signals": {
        "weight": 0.12,
        "patterns": [
            r"security cabinet",
            r"war cabinet",
            r"cabinet.*approved",
            r"הקבינט",
            r"אישור מדיני",
            r"הנחיית הדרג המדיני",
        ],
    },
    "multi_front_pressure": {
        "weight": 0.09,
        "patterns": [
            r"gaza and lebanon",
            r"iran-backed",
            r"multi-front",
            r"רב[- ]זירתי",
            r"גם בעזה וגם בצפון",
        ],
    },
    "division_36_specific": {
        "weight": 0.05,
        "patterns": DIVISION_36_TERMS + [
            r"northern command.*36",
            r"artillery.*36",
            r"תותחנים.*אוגדה\s*36",
        ],
    },
    "brigade_282_specific": {
        "weight": 0.04,
        "patterns": BRIGADE_282_TERMS + [
            r"artillery brigade.*282",
            r"reserve.*282",
            r"מילואים.*282",
        ],
    },
    "battalion_9260_specific": {
        "weight": 0.03,
        "patterns": BATTALION_9260_TERMS + [
            r"מילואים.*9260",
            r"גדוד.*תותחנים.*9260",
        ],
    },
}

WIDE_CAMPAIGN_PATTERNS = [
    r"wide campaign in lebanon",
    r"expanded campaign in lebanon",
    r"major escalation in lebanon",
    r"מערכה רחבה בלבנון",
    r"הרחבת המערכה בצפון",
]


@dataclass
class NewsItem:
    source: str
    title: str
    summary: str
    link: str
    published: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.summary}".lower()


def fetch_url(url: str, timeout_sec: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        return response.read().decode("utf-8", errors="ignore")


def _find_text(elem: ET.Element, tags: List[str]) -> str:
    for tag in tags:
        found = elem.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_feed_xml(xml_text: str, source: str, max_items: int = 80) -> List[NewsItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items: List[NewsItem] = []

    # RSS
    for item in root.findall(".//item")[:max_items]:
        items.append(
            NewsItem(
                source=source,
                title=_find_text(item, ["title"]),
                summary=_find_text(item, ["description", "summary"]),
                link=_find_text(item, ["link"]),
                published=_find_text(item, ["pubDate", "published"]),
            )
        )

    # Atom fallback
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns)[:max_items]:
            link = ""
            link_elem = entry.find("atom:link", ns)
            if link_elem is not None:
                link = link_elem.attrib.get("href", "")
            items.append(
                NewsItem(
                    source=source,
                    title=_find_text(entry, ["{http://www.w3.org/2005/Atom}title"]),
                    summary=_find_text(entry, [
                        "{http://www.w3.org/2005/Atom}summary",
                        "{http://www.w3.org/2005/Atom}content",
                    ]),
                    link=link,
                    published=_find_text(entry, ["{http://www.w3.org/2005/Atom}updated"]),
                )
            )
    return items


def collect_news() -> Tuple[List[NewsItem], List[str]]:
    errors: List[str] = []
    all_items: List[NewsItem] = []
    for source, url in FEEDS.items():
        try:
            xml_text = fetch_url(url)
            all_items.extend(parse_feed_xml(xml_text, source))
        except (urllib.error.URLError, TimeoutError) as exc:
            errors.append(f"{source}: {exc}")
    return all_items, errors


def pattern_hits(text: str, patterns: List[str]) -> int:
    hits = 0
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits += 1
    return hits


def score_signal(items: List[NewsItem], patterns: List[str]) -> Tuple[float, int]:
    total_hits = 0
    hit_articles = 0
    for item in items:
        hits = pattern_hits(item.text, patterns)
        if hits:
            hit_articles += 1
            total_hits += hits

    # Raw intensity before normalization to 0..100
    raw = hit_articles * 15.0 + total_hits * 3.0
    return raw, hit_articles


def score_signal_with_llm(
    items: List[NewsItem],
    patterns: List[str],
    signal_name: str,
    llm_labels: Dict[str, Set[int]],
) -> Tuple[float, int]:
    total_hits = 0
    hit_articles = 0
    labeled = llm_labels.get(signal_name, set())
    for idx, item in enumerate(items):
        regex_hits = pattern_hits(item.text, patterns)
        llm_match = idx in labeled
        if regex_hits or llm_match:
            hit_articles += 1
            total_hits += regex_hits
            # Semantic-only positives still count even when keywords miss the phrasing.
            if llm_match and regex_hits == 0:
                total_hits += 2

    raw = hit_articles * 15.0 + total_hits * 3.0
    return raw, hit_articles


def _post_json(url: str, payload: Dict[str, object], headers: Dict[str, str], timeout_sec: int = 45) -> Dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_sec) as response:
        text = response.read().decode("utf-8", errors="ignore")
    return json.loads(text)


def llm_classify_signals(items: List[NewsItem]) -> Tuple[Dict[str, Set[int]], Optional[str]]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return {}, "GROQ_API_KEY not set"

    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    max_articles_env = os.getenv("LLM_MAX_ARTICLES", str(DEFAULT_LLM_MAX_ARTICLES)).strip()
    try:
        max_articles = max(10, min(300, int(max_articles_env)))
    except ValueError:
        max_articles = DEFAULT_LLM_MAX_ARTICLES

    target_items = items[:max_articles]
    signal_names = list(SIGNALS.keys())
    labels: Dict[str, Set[int]] = {name: set() for name in signal_names}

    batch_size = 12
    for start in range(0, len(target_items), batch_size):
        chunk = target_items[start:start + batch_size]
        batch_payload = [
            {"id": start + i, "title": it.title, "summary": it.summary}
            for i, it in enumerate(chunk)
        ]
        prompt = (
            "You classify security news for artillery call-up signals.\n"
            "Return ONLY JSON in this exact shape:\n"
            "{\"results\":[{\"id\":0,\"signals\":{\"fire_from_lebanon\":true}}]}\n"
            "Use only these signal keys: " + ", ".join(signal_names) + ".\n"
            "For each article id, return all keys with boolean values.\n"
            "Be strict: mark true only if the article meaning clearly matches the signal.\n"
            "Articles JSON:\n" + json.dumps(batch_payload, ensure_ascii=False)
        )

        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            response = _post_json(GROQ_API_URL, payload, headers)
            content = response["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            for row in parsed.get("results", []):
                rid = row.get("id")
                if not isinstance(rid, int):
                    continue
                signals = row.get("signals", {})
                if not isinstance(signals, dict):
                    continue
                for name in signal_names:
                    if bool(signals.get(name, False)):
                        labels[name].add(rid)
        except Exception as exc:  # noqa: BLE001
            return {}, f"LLM classification failed: {exc}"

    return labels, None


def normalize_signal_score(signal_name: str, raw: float) -> float:
    baseline = SIGNAL_RAW_AT_75.get(signal_name)
    if baseline and baseline > 0:
        # Baseline raw intensity maps to 75; stronger conditions can still increase toward 100.
        return min(100.0, max(0.0, (raw / baseline) * 75.0))
    return min(100.0, max(0.0, raw))


def compute_index(items: List[NewsItem], assume_wide_campaign: bool = False, use_llm: bool = True) -> Dict[str, object]:
    signal_scores: Dict[str, float] = {}
    signal_hits: Dict[str, int] = {}
    llm_labels: Dict[str, Set[int]] = {}
    llm_error = None
    llm_used = False
    weighted = 0.0

    if use_llm:
        llm_labels, llm_error = llm_classify_signals(items)
        llm_used = bool(llm_labels)

    for name, cfg in SIGNALS.items():
        if llm_used:
            raw, h = score_signal_with_llm(items, cfg["patterns"], name, llm_labels)
        else:
            raw, h = score_signal(items, cfg["patterns"])
        s = normalize_signal_score(name, raw)
        signal_scores[name] = round(s, 2)
        signal_hits[name] = h
        weighted += s * cfg["weight"]

    wide_campaign_articles = [
        x for x in items if pattern_hits(x.text, WIDE_CAMPAIGN_PATTERNS) > 0
    ]
    wide_campaign_boost = min(12.0, 4.0 * len(wide_campaign_articles))

    base = min(100.0, weighted)
    if assume_wide_campaign:
        # Scenario mode: if a wider Lebanon campaign starts, artillery call-up pressure rises sharply.
        base = min(100.0, max(base, 65.0))
        wide_campaign_boost = max(wide_campaign_boost, 22.0)

        # Division 36-specific doctrine assumption: this formation is likely to be in the first reinforcement wave.
        if signal_scores.get("division_36_specific", 0.0) < 30.0:
            signal_scores["division_36_specific"] = 30.0
            signal_hits["division_36_specific"] = max(signal_hits.get("division_36_specific", 0), 1)

    # Calibration so current baseline conditions map closer to the requested operating range.
    final = min(100.0, max(0.0, base + wide_campaign_boost + BASELINE_CALIBRATION_OFFSET))

    manual_boost, manual_details = load_manual_boosts()
    final = min(100.0, final + manual_boost)

    # Map to simpler categories.
    if final >= 80:
        band = "גבוה מאוד"
    elif final >= 65:
        band = "גבוה"
    elif final >= 45:
        band = "בינוני"
    else:
        band = "נמוך"

    return {
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "articles_scanned": len(items),
        "score": round(final, 2),
        "base_score": round(base, 2),
        "wide_campaign_boost": round(wide_campaign_boost, 2),
        "band": band,
        "signal_scores": signal_scores,
        "signal_hits": signal_hits,
        "wide_campaign_hit_count": len(wide_campaign_articles),
        "assume_wide_campaign": assume_wide_campaign,
        "manual_boost": manual_boost,
        "manual_signals": manual_details,
        "llm_used": llm_used,
        "llm_model": (os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL) if llm_used else None),
        "llm_error": llm_error,
        "misc_signals": {
            # Requested by user: random display-only signal, not part of score.
            "shimel_loser": random.randint(51, 100),
        },
    }


def load_manual_boosts() -> Tuple[float, List[Dict[str, object]]]:
    if not os.path.exists(MANUAL_SIGNALS_FILE):
        return 0.0, []

    try:
        with open(MANUAL_SIGNALS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0.0, []

    items = payload.get("signals", [])
    today = dt.date.today()
    active: List[Dict[str, object]] = []
    total = 0.0
    for item in items:
        try:
            boost = float(item.get("boost", 0))
        except (TypeError, ValueError):
            continue
        if boost <= 0:
            continue
        expires = item.get("expires_on")
        if expires:
            try:
                exp_date = dt.date.fromisoformat(expires)
                if exp_date < today:
                    continue
            except ValueError:
                continue
        total += boost
        active.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "boost": boost,
                "expires_on": expires,
            }
        )

    # Prevent manual inputs from fully overriding all other signals.
    total = min(total, 30.0)
    return round(total, 2), active


def save_outputs(result: Dict[str, object], items: List[NewsItem], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    data_dir = os.path.join(out_dir, "data")
    reports_dir = os.path.join(out_dir, "reports")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    today = dt.datetime.now().strftime("%Y-%m-%d")

    json_path = os.path.join(data_dir, "latest_index.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    hist_csv = os.path.join(data_dir, "history.csv")
    write_header = not os.path.exists(hist_csv)
    with open(hist_csv, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["date", "score", "base_score", "boost", "band", "articles_scanned"])
        w.writerow([
            today,
            result["score"],
            result["base_score"],
            result["wide_campaign_boost"],
            result["band"],
            result["articles_scanned"],
        ])

    report_path = os.path.join(reports_dir, f"daily_report_{today}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# {INDEX_NAME}\n\n")
        f.write(f"תאריך: {today}\n\n")
        f.write(f"ציון כללי: **{result['score']} / 100** ({result['band']})\n\n")
        f.write(f"ציון בסיס: {result['base_score']}\n\n")
        f.write(f"תוספת מערכה רחבה: {result['wide_campaign_boost']}\n\n")
        f.write(f"תוספת ידנית (ידיעות איכות): {result.get('manual_boost', 0)}\n\n")
        f.write("## אותות\n")
        for name, score in result["signal_scores"].items():
            hits = result["signal_hits"].get(name, 0)
            f.write(f"- {name}: {score} (כתבות תואמות: {hits})\n")

        manual_signals = result.get("manual_signals", [])
        if manual_signals:
            f.write("\n## ידיעות איכות ידניות שנוספו למדד\n")
            for sig in manual_signals:
                f.write(
                    f"- [{sig.get('title','(ללא כותרת)')}]({sig.get('url','')}) "
                    f"| בוסט: {sig.get('boost',0)} | תוקף עד: {sig.get('expires_on','ללא')}\n"
                )
        misc = result.get("misc_signals", {})
        if misc:
            f.write("\n## שונים\n")
            f.write(f"- שימל לוזר: {misc.get('shimel_loser', 0)}\n")

        f.write("\n## דוגמאות ידיעות שנכללו\n")
        for item in items[:20]:
            title = item.title.strip() or "(ללא כותרת)"
            link = item.link.strip()
            f.write(f"- [{title}]({link}) ({item.source})\n")


def run(offline_demo: bool, out_dir: str, assume_wide_campaign: bool, use_llm: bool) -> int:
    if offline_demo:
        sample = [
            NewsItem(
                source="demo",
                title="Reports of rockets from Lebanon as cabinet discusses expanded campaign",
                summary="IDF prepares additional reserve units in northern command.",
                link="https://example.com/demo1",
                published="",
            ),
            NewsItem(
                source="demo",
                title="אוגדה 36 מתגברת כוחות תותחנים בגזרה הצפונית",
                summary="דיווחים על היערכות לתמרון קרקעי בלבנון.",
                link="https://example.com/demo2",
                published="",
            ),
        ]
        result = compute_index(sample, assume_wide_campaign=assume_wide_campaign, use_llm=use_llm)
        save_outputs(result, sample, out_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    items, errors = collect_news()
    if not items:
        print("No items collected from feeds.", file=sys.stderr)
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
        return 2

    result = compute_index(items, assume_wide_campaign=assume_wide_campaign, use_llm=use_llm)
    save_outputs(result, items, out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        print("Warnings:")
        for e in errors:
            print(f"- {e}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily call-up index for artillery battalion (Division 36)")
    parser.add_argument("--offline-demo", action="store_true", help="Run with local demo data (no network)")
    parser.add_argument("--out-dir", default=".", help="Base output directory")
    parser.add_argument(
        "--assume-wide-campaign",
        action="store_true",
        help="Scenario mode: assume broad campaign in Lebanon has started",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable Groq/Llama semantic classification and use keyword mode only",
    )
    args = parser.parse_args()
    return run(args.offline_demo, args.out_dir, args.assume_wide_campaign, use_llm=(not args.no_llm))


if __name__ == "__main__":
    raise SystemExit(main())
