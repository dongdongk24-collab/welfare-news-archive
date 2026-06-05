import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "posts"
DATA = ROOT / "data"
APP_JS = ROOT / "assets" / "app.js"

FEEDS = [
    {
        "name": "보건복지부 보도자료",
        "section": "복지 전반에 관련된 주요 뉴스",
        "url": "https://www.mohw.go.kr/rss/board.es?mid=a10503000000&bid=0027&info",
        "sourceName": "보건복지부",
        "priority": 5,
    },
    {
        "name": "대한민국 정책브리핑 보도자료",
        "section": "복지 전반에 관련된 주요 뉴스",
        "url": "https://www.korea.kr/rss/pressrelease.xml",
        "sourceName": "정책브리핑",
        "priority": 4,
    },
    {
        "name": "서울시 보도자료",
        "section": "서울시 복지 정책 및 복지 현장 관련 뉴스",
        "url": "https://seoulboard.seoul.go.kr/rss/RSSGenerator?bbsNo=158",
        "sourceName": "서울특별시",
        "priority": 4,
    },
    {
        "name": "내 손안에 서울 복지 RSS",
        "section": "서울시 복지 정책 및 복지 현장 관련 뉴스",
        "url": "https://mediahub.seoul.go.kr/news/rss/07",
        "sourceName": "내 손안에 서울",
        "priority": 3,
    },
    {
        "name": "광진구 보도자료",
        "section": "광진구 지역 복지 관련 뉴스",
        "url": "https://www.gwangjin.go.kr/portal/bbs/B0000002/rssService.do?viewType=CONTBODY&bbsId=B02",
        "sourceName": "광진구청",
        "priority": 4,
    },
]

SECTION_ORDER = [
    "복지 전반에 관련된 주요 뉴스",
    "서울시 복지 정책 및 복지 현장 관련 뉴스",
    "광진구 지역 복지 관련 뉴스",
]

WELFARE_KEYWORDS = [
    "복지", "돌봄", "통합돌봄", "사회보장", "기초생활", "수급", "긴급복지", "취약",
    "저소득", "장애", "노인", "어르신", "고독사", "1인가구", "아동", "청소년",
    "청년", "가족돌봄", "주거", "자립", "자활", "보육", "아동수당", "기초연금",
    "의료비", "건강", "안부", "폭염", "한파", "급식", "일자리", "사회서비스",
    "복지관", "지역사회보장", "동행", "희망두배", "꿈나래", "장애인", "발달장애",
]

NOISE_KEYWORDS = ["행사", "축제", "공연", "관광", "스포츠"]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())

    def text(self):
        return " ".join(self.parts)


def strip_html(value):
    parser = TextExtractor()
    parser.feed(unescape(value or ""))
    return re.sub(r"\s+", " ", parser.text()).strip()


def yesterday_kst():
    return (datetime.now(KST).date() - timedelta(days=1)).isoformat()


def korean_date(value):
    y, m, d = map(int, value.split("-"))
    return f"{y}년 {m}월 {d}일"


def stars(n):
    n = max(1, min(5, int(n or 1)))
    return "★" * n + "☆" * (5 - n)


def fetch_bytes(url):
    req = Request(url, headers={"User-Agent": "welfare-news-archive/1.0"})
    with urlopen(req, timeout=30) as res:
        return res.read()


def parse_date(value):
    if not value:
        return None
    value = strip_html(value)
    for pattern in ("%Y-%m-%d", "%Y.%m.%d", "%Y. %m. %d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value[:10], pattern).date()
        except ValueError:
            pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).date()
    except Exception:
        return None


def element_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    for child in list(element):
        tag = child.tag.split("}")[-1].lower()
        if tag in names and child.text:
            return child.text.strip()
    return ""


def parse_feed(feed):
    try:
        root = ET.fromstring(fetch_bytes(feed["url"]))
    except Exception as exc:
        return [], [f"{feed['name']} 수집 실패: {exc}"]

    items = []
    errors = []
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for node in nodes:
        title = strip_html(element_text(node, ["title"]))
        description = strip_html(element_text(node, ["description", "summary", "content"]))
        link = element_text(node, ["link"])
        if not link:
            for child in list(node):
                if child.tag.split("}")[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    break
        link = urljoin(feed["url"], link)
        pub_date = parse_date(element_text(node, ["pubDate", "published", "updated", "dc:date", "date"]))
        items.append({
            "feed": feed,
            "title": title,
            "description": description,
            "url": link,
            "published": pub_date.isoformat() if pub_date else "",
        })
    return items, errors


def is_welfare_item(item):
    text = f"{item['title']} {item['description']}"
    if not any(keyword in text for keyword in WELFARE_KEYWORDS):
        return False
    if item["feed"]["section"] == "광진구 지역 복지 관련 뉴스":
        return True
    if item["feed"]["section"] == "서울시 복지 정책 및 복지 현장 관련 뉴스":
        return True
    # 정책브리핑 전체 RSS는 범위가 넓어서 복지부 또는 강한 복지 키워드가 있어야 포함합니다.
    if item["feed"]["sourceName"] == "정책브리핑":
        return "보건복지부" in text or any(k in text for k in ["복지", "돌봄", "장애", "기초생활", "아동수당", "기초연금", "사회서비스"])
    return True


def rating_for(item):
    text = f"{item['title']} {item['description']}"
    score = item["feed"].get("priority", 3)
    if any(k in text for k in ["긴급", "기초생활", "통합돌봄", "장애", "저소득", "취약", "폭염", "고독사"]):
        score += 1
    if any(k in text for k in NOISE_KEYWORDS) and not any(k in text for k in ["복지", "취약", "장애", "노인"]):
        score -= 1
    return max(1, min(5, score))


def make_summary(item):
    desc = item["description"]
    if not desc:
        desc = f"{item['feed']['sourceName']}에서 보도한 복지 관련 소식입니다."
    desc = re.sub(r"\s+", " ", desc).strip()
    if len(desc) > 220:
        desc = desc[:217].rstrip() + "..."
    return desc


def make_insight(item):
    title = item["title"]
    section = item["feed"]["section"]
    if "폭염" in title or "한파" in title or "안부" in title:
        return "복지관에서는 고위험가구 명단, 안부확인 주기, 긴급연계 연락망을 미리 점검할 필요가 있습니다."
    if "통합돌봄" in title or "돌봄" in title:
        return "사례관리와 지역 돌봄 연계를 강화할 수 있는 의제입니다. 동주민센터, 보건소, 제공기관과의 의뢰 경로를 확인하면 좋습니다."
    if "청년" in title or "꿈나래" in title or "희망두배" in title:
        return "청년·가구 자립 상담에서 신청 조건과 기간을 확인해 대상자에게 안내할 수 있습니다."
    if "장애" in title:
        return "장애등록, 활동지원, 의료비, 가족돌봄 부담과 연결해 상담할 수 있는 이슈입니다."
    if section.startswith("광진구"):
        return "광진구 지역 사업이므로 복지관 프로그램, 후원, 사례관리 연계 가능성을 우선 확인할 필요가 있습니다."
    return "현장 사회복지사는 대상자 발굴, 제도 안내, 지역 자원 연계 가능성을 함께 살펴볼 필요가 있습니다."


def make_item(item):
    title = item["title"]
    source = item["feed"]["sourceName"]
    published = item.get("published") or "날짜 확인 필요"
    return {
        "rating": rating_for(item),
        "title": title,
        "subtitles": [
            f"{source} RSS에서 확인된 {published} 보도자료/기사",
            "AI 생성 요약 없이 제목·본문 요약문·출처 링크를 기준으로 자동 수집",
        ],
        "summary": make_summary(item),
        "insight": make_insight(item),
        "sourceName": source,
        "url": item["url"],
    }


def collect_news(target_date):
    all_items = []
    excluded = []
    for feed in FEEDS:
        items, errors = parse_feed(feed)
        excluded.extend(errors)
        all_items.extend(items)

    seen = set()
    sections = {name: [] for name in SECTION_ORDER}
    for item in all_items:
        if item.get("published") and item["published"] != target_date:
            continue
        if not item.get("published"):
            excluded.append(f"날짜 확인 불가: {item.get('title')}")
            continue
        if not item["title"] or not item["url"]:
            continue
        if not is_welfare_item(item):
            excluded.append(f"복지 키워드 제외: {item['title']}")
            continue
        key = (item["title"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        section = item["feed"]["section"]
        if len(sections[section]) < 5:
            sections[section].append(make_item(item))

    section_data = []
    for name in SECTION_ORDER:
        items = sections[name]
        note = ""
        if not items:
            note = f"{target_date} 00:00~23:59(KST) 기준, RSS 수집 범위에서 확인된 관련 뉴스가 없습니다."
        elif len(items) < 3:
            note = f"RSS 수집 범위에서 {len(items)}건만 확인했습니다."
        section_data.append({"name": name, "items": items, "note": note})

    return {
        "date": target_date,
        "title": f"{korean_date(target_date)} 복지 뉴스",
        "generatedAt": datetime.now(KST).isoformat(timespec="seconds"),
        "collectionMode": "rss-no-ai",
        "sections": section_data,
        "excluded": excluded[:40],
    }


def render_html(data):
    date = data["date"]
    title = data.get("title") or f"{korean_date(date)} 복지 뉴스"
    sections_html = []
    for section in data.get("sections", []):
        parts = [f'<section class="topic">\n<h2>{escape(section.get("name", ""))}</h2>']
        for item in section.get("items", []):
            subtitles = "".join(f"<li>{escape(s)}</li>" for s in item.get("subtitles", [])[:2])
            source = escape(item.get("sourceName") or "원문")
            url = escape(item.get("url") or "#")
            parts.append(f'''
<article class="news-item">
  <div class="rating">{stars(item.get("rating", 1))}</div>
  <h3><strong>{escape(item.get("title", ""))}</strong></h3>
  <ul>{subtitles}</ul>
  <p>{escape(item.get("summary", ""))}</p>
  <p class="think"><strong>생각해 봅시다</strong>{escape(item.get("insight", ""))}</p>
  <p class="source">참고 URL: <a href="{url}" target="_blank" rel="noopener noreferrer">{source}</a></p>
</article>''')
        if section.get("note"):
            parts.append(f'<p class="empty">{escape(section["note"])}</p>')
        parts.append("</section>")
        sections_html.append("\n".join(parts))

    return f'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="../assets/style.css?v=20260605-unified1">
</head>
<body>
  <header class="site-header">
    <div>
      <nav class="detail-nav" aria-label="상세 페이지 이동">
        <a class="nav-button" href="../index.html">홈으로</a>
        <a class="nav-button" href="../index.html#latest-title">날짜 목록</a>
      </nav>
      <p class="eyebrow">Daily Welfare News</p>
      <h1>{escape(title)}</h1>
      <p class="lead">{escape(date)} 00:00~23:59(KST)에 보도된 복지 뉴스를 RSS 기반으로 자동 수집했습니다.</p>
    </div>
  </header>
  <main class="article-layout">
    <a class="back-link" href="../index.html">← 날짜 목록으로</a>
    {' '.join(sections_html)}
  </main>
</body>
</html>
'''


def section_counts(data):
    counts = []
    for section in data.get("sections", []):
        name = section.get("name", "")
        label = "복지 전반" if "전반" in name else "서울시" if "서울" in name else "광진구" if "광진" in name else name
        count = len(section.get("items", []))
        counts.append(f"{label} {count}건" if count else f"{label} 확인된 뉴스 없음")
    return ", ".join(counts)


def update_app_js(data):
    if not APP_JS.exists():
        return
    text = APP_JS.read_text(encoding="utf-8")
    date = data["date"]
    entry = f'''  {{
    date: "{date}",
    label: "{korean_date(date)}",
    href: "posts/{date}.html",
    summary: "{section_counts(data)}"
  }},
'''
    if f'date: "{date}"' in text:
        pattern = re.compile(r'  \{\n    date: "' + re.escape(date) + r'",\n    label: "[^"]+",\n    href: "[^"]+",\n    summary: "[^"]*"\n  \},\n')
        text = pattern.sub(entry, text, count=1)
    else:
        text = re.sub(r"const archiveEntries = \[\n", "const archiveEntries = [\n" + entry, text, count=1)
    APP_JS.write_text(text, encoding="utf-8")


def update_search_index(data):
    path = DATA / "search-index.json"
    index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    index = [item for item in index if item.get("date") != data["date"]]
    additions = []
    for section in data.get("sections", []):
        for item in section.get("items", []):
            additions.append({
                "date": data["date"],
                "dateLabel": korean_date(data["date"]),
                "page": f"posts/{data['date']}.html",
                "section": section.get("name", ""),
                "rating": item.get("rating", 1),
                "title": item.get("title", ""),
                "subtitles": item.get("subtitles", []),
                "summary": item.get("summary", ""),
                "insight": item.get("insight", ""),
                "url": item.get("url", ""),
            })
    path.write_text(json.dumps(additions + index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    target_date = os.environ.get("TARGET_DATE") or yesterday_kst()
    data = collect_news(target_date)

    POSTS.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    (DATA / f"news-{target_date}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (POSTS / f"{target_date}.html").write_text(render_html(data), encoding="utf-8")
    update_app_js(data)
    update_search_index(data)

    total = sum(len(s.get("items", [])) for s in data.get("sections", []))
    print(json.dumps({"targetDate": target_date, "newsItems": total, "page": f"posts/{target_date}.html"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
