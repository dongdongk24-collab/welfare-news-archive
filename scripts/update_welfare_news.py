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
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "posts"
DATA = ROOT / "data"
APP_JS = ROOT / "assets" / "app.js"

FEEDS = [
    {"name": "웰페어뉴스", "section": "복지 전반에 관련된 주요 뉴스", "url": "https://www.welfarenews.net/rss/allArticle.xml", "sourceName": "웰페어뉴스", "priority": 4, "contentType": "언론기사"},
    {"name": "복지타임즈", "section": "복지 전반에 관련된 주요 뉴스", "url": "https://www.bokjitimes.com/rss/allArticle.xml", "sourceName": "복지타임즈", "priority": 4, "contentType": "언론기사"},
    {"name": "에이블뉴스", "section": "복지 전반에 관련된 주요 뉴스", "url": "https://www.ablenews.co.kr/rss/allArticle.xml", "sourceName": "에이블뉴스", "priority": 4, "contentType": "언론기사"},
    {"name": "경향신문 사회", "section": "복지 전반에 관련된 주요 뉴스", "url": "https://www.khan.co.kr/rss/rssdata/society_news.xml", "sourceName": "경향신문", "priority": 3, "contentType": "언론기사", "linkOnly": True},
    {"name": "경향신문 오피니언", "section": "복지 전반에 관련된 주요 뉴스", "url": "https://www.khan.co.kr/rss/rssdata/opinion_news.xml", "sourceName": "경향신문", "priority": 3, "contentType": "칼럼·기고", "linkOnly": True},
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
STRONG_WELFARE = ["사회복지", "복지", "돌봄", "사회보장", "기초생활", "수급자", "긴급복지", "빈곤", "저소득", "취약계층", "장애", "고독사", "고립", "은둔", "자립준비", "자활", "사례관리", "노인", "어르신", "기초연금", "아동학대", "사회서비스", "주거취약", "노숙", "정신건강", "중독", "학대", "가정폭력", "한부모", "가족돌봄", "지역아동센터", "발달장애", "주거권"]
OPINION_MARKERS = ["칼럼", "기고", "사설", "시론", "오피니언", "기자수첩", "논단", "시평"]


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
        value = res.read(4_000_001)
        if len(value) > 4_000_000:
            raise ValueError("RSS 응답 크기 초과")
        return value


def parse_date(value):
    if not value:
        return None
    value = strip_html(value)
    if "T" in value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=dt.tzinfo or KST).astimezone(KST).date()
        except ValueError:
            pass
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
        category = element_text(node, ["category"])
        link = element_text(node, ["link"])
        if not link:
            for child in list(node):
                if child.tag.split("}")[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    break
        link = urljoin(feed["url"], link)
        parsed_link = urlsplit(link)
        if parsed_link.scheme not in ("https", "http"):
            continue
        link = urlunsplit((parsed_link.scheme, parsed_link.netloc, parsed_link.path, urlencode([(k, v) for k, v in parse_qsl(parsed_link.query) if not k.startswith("utm_")]), ""))
        pub_date = parse_date(element_text(node, ["pubDate", "published", "updated", "dc:date", "date"]))
        items.append({
            "feed": feed,
            "title": title,
            "description": description,
            "category": category,
            "url": link,
            "published": pub_date.isoformat() if pub_date else "",
        })
    return items, errors


def is_welfare_item(item):
    text = f"{item['title']} {item['description']}"
    if not re.sub(r"\[[^\]]*\]", "", item["title"]).strip():
        return False
    if item["title"].startswith("[포토") and any(k in item["title"] for k in ["수상", "표창", "화합상"]):
        return False
    if "뉴스 브리핑" in item["title"]:
        embedded = re.search(r"(20\d{2})[.-](\d{2})[.-](\d{2})", item["title"])
        if embedded and "-".join(embedded.groups()) != item.get("published"):
            return False
    # 건강·청년·행사 같은 포괄 단어 하나만으로 복지 기사로 분류하지 않습니다.
    if not any(keyword in text for keyword in STRONG_WELFARE):
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
    if item["feed"].get("contentType") and not any(k in item["title"] for k in STRONG_WELFARE):
        score -= 1
    if any(k in text for k in ["긴급", "기초생활", "통합돌봄", "장애", "저소득", "취약", "폭염", "고독사"]):
        score += 1
    if any(k in text for k in NOISE_KEYWORDS) and not any(k in text for k in ["복지", "취약", "장애", "노인"]):
        score -= 1
    return max(1, min(5, score))


def make_summary(item):
    desc = item["description"]
    if item["feed"].get("linkOnly"):
        return "제목에서 복지 관련 의제가 확인된 기사입니다. 본문 요약을 제공하지 않으므로 구체적인 주장과 근거는 원문에서 확인해 주세요."
    if not desc:
        return "RSS에 본문 요약이 없어 기사 제목만 확인했습니다. 자세한 내용은 원문에서 확인해 주세요."
    desc = re.sub(r"\s+", " ", desc).strip()
    if item["feed"].get("contentType"):
        # 언론 원문을 복제하지 않고 짧은 RSS 소개만 제공합니다.
        desc = " ".join(desc.split()[:12])
        if len(desc) > 110:
            desc = desc[:107].rstrip()
        return desc + "…"
    if len(desc) > 220:
        desc = desc[:217].rstrip() + "..."
    return desc


def make_insight(item):
    title = item["title"]
    section = item["feed"]["section"]
    if content_type(item) == "칼럼·기고":
        return "이 글의 주장과 우리 현장 경험은 어디에서 만나고, 어떤 반례가 있을까요? 필자의 의견과 확인된 사실을 구분하며 팀에서 논의할 질문을 골라 보세요."
    if any(k in title for k in ["정신", "중독", "자살", "우울"]):
        return "우리 지역에서 지원이 끊기기 쉬운 지점은 어디일까요? 당사자의 의사와 안전을 함께 고려하며 정신건강·의료·지역복지 기관의 의뢰 경로를 점검해 보세요."
    if "폭염" in title or "한파" in title or "안부" in title:
        return "연락이 닿지 않거나 지원 정보를 접하기 어려운 가구는 누구일까요? 안부확인 주기와 긴급연계 연락망에 빠진 대상이 없는지 살펴보세요."
    if "통합돌봄" in title or "돌봄" in title:
        return "지원 대상과 실제로 이용할 수 있는 서비스 사이에 어떤 빈틈이 있을까요? 동주민센터·보건소·복지관의 역할과 의뢰 경로를 구체적으로 비교해 보세요."
    if "청년" in title or "꿈나래" in title or "희망두배" in title:
        return "기존 지원 기준으로 발견하지 못하는 청년·가구가 있을까요? 신청 조건과 기간뿐 아니라 정보를 접하고 참여하기 어려운 이유도 함께 살펴보세요."
    if "장애" in title:
        return "당사자의 선택권과 접근권을 가로막는 환경은 무엇일까요? 우리 기관의 안내·동선·서비스 이용 절차에도 비슷한 장벽이 있는지 점검해 보세요."
    if any(k in title for k in ["빈곤", "수급", "기초생활", "주거", "노숙", "자활", "저소득"]):
        return "제도 기준과 실제 생활의 어려움이 어긋나는 지점은 어디일까요? 사례관리에서 반복되는 미충족 욕구와 지역 자원으로 보완할 수 있는 범위를 구분해 보세요."
    if section.startswith("광진구"):
        return "광진구 현장에서도 비슷한 요구가 관찰되나요? 주민에게 필요한 정보와 참여 장벽, 우리 팀이 연결할 수 있는 지역 자원을 함께 확인해 보세요."
    return "이 기사에서 다루는 문제가 우리 지역에서는 누구의 경험으로 나타날까요? 기사에 제시된 근거와 현장의 관찰을 비교하고, 추가로 확인할 질문을 정리해 보세요."


def content_type(item):
    feed = item["feed"]
    if not feed.get("contentType"):
        return "공식보도자료"
    if feed["contentType"] == "칼럼·기고" or any(k in item["title"] + item.get("category", "") for k in OPINION_MARKERS):
        return "칼럼·기고"
    return "언론기사"


def section_for(item):
    if not item["feed"].get("contentType"):
        return item["feed"]["section"]
    text = item["title"] + " " + item["description"]
    return SECTION_ORDER[2] if "광진" in text else SECTION_ORDER[1] if any(k in text for k in ["서울시", "서울특별시", "서울형"]) else SECTION_ORDER[0]


def make_item(item):
    title = item["title"]
    source = item["feed"]["sourceName"]
    published = item.get("published") or "날짜 확인 필요"
    return {
        "rating": rating_for(item),
        "title": title,
        "subtitles": [
            f"{source} RSS에서 확인된 {published} {content_type(item)}",
            "AI 생성 요약 없이 제목·본문 요약문·출처 링크를 기준으로 자동 수집",
        ],
        "summary": make_summary(item),
        "insight": make_insight(item),
        "sourceName": source,
        "contentType": content_type(item),
        "summaryBasis": "제목 확인·본문 미확인" if item["feed"].get("linkOnly") or not item["description"] else "언론사 RSS 소개 발췌" if item["feed"].get("contentType") else "공식 RSS 요약문",
        "insightBasis": "실무 검토 질문",
        "url": item["url"],
    }


def collect_news(target_date):
    all_items = []
    excluded = []
    coverage = []
    with ThreadPoolExecutor(max_workers=6) as pool:
      for feed, (items, errors) in zip(FEEDS, pool.map(parse_feed, FEEDS)):
        excluded.extend(errors)
        all_items.extend(items)
        coverage.append({"name": feed["name"], "url": feed["url"], "status": "error" if errors else "ok", "feedItems": len(items)})
    if all(c["status"] == "error" for c in coverage):
        raise RuntimeError("모든 수집처 연결 실패: 날짜를 빈 수집 결과로 저장하지 않습니다.")

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
        key = re.sub(r"[\W_]+", "", item["title"]).lower()
        if key in seen:
            continue
        seen.add(key)
        sections[section_for(item)].append(make_item(item))

    # 재실행 시 이미 확인한 해당 날짜 기사를 보존합니다. RSS의 최근 기사 수 제한으로 과거 기사가 사라질 수 있습니다.
    old = {"sections": []}
    previous = DATA / f"news-{target_date}.json"
    if previous.exists():
        old = json.loads(previous.read_text(encoding="utf-8"))
        for section in old.get("sections", []):
            for item in section.get("items", []):
                key = re.sub(r"[\W_]+", "", item.get("title", "")).lower()
                if key in seen or section.get("name") not in sections:
                    continue
                seen.add(key)
                item.setdefault("contentType", "공식보도자료" if any(h in item.get("url", "") for h in ["mohw.go.kr", "seoul.go.kr", "gwangjin.go.kr", "korea.kr"]) else "언론기사")
                sections[section["name"]].append(item)

    section_data = []
    for name in SECTION_ORDER:
        items = balanced_selection(sections[name])
        # 후보 수 제한 때문에 이미 저장한 과거 기사가 삭제되지 않게 합니다.
        kept = {i.get("url") for i in items}
        for prior_section in old.get("sections", []):
            if prior_section.get("name") != name:
                continue
            for prior in prior_section.get("items", []):
                if prior.get("url") not in kept:
                    prior.setdefault("contentType", "공식보도자료" if any(h in prior.get("url", "") for h in ["mohw.go.kr", "seoul.go.kr", "gwangjin.go.kr", "korea.kr"]) else "언론기사")
                    items.append(prior)
                    kept.add(prior.get("url"))
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
        "sourceCoverage": coverage,
        "sections": section_data,
        "excluded": excluded[:40],
    }


def balanced_selection(items):
    selected = []
    source_counts = {}
    for kind, maximum in [("칼럼·기고", 3), ("언론기사", 9), ("공식보도자료", 5)]:
        count = 0
        for item in sorted(items, key=lambda i: i.get("rating", 0), reverse=True):
            if item.get("contentType", "공식보도자료") != kind:
                continue
            source = item.get("sourceName") or urlsplit(item.get("url", "")).hostname
            if kind != "공식보도자료" and source_counts.get(source, 0) >= 3:
                continue
            selected.append(item)
            source_counts[source] = source_counts.get(source, 0) + 1
            count += 1
            if count >= maximum:
                break
    return selected


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
                "sourceName": item.get("sourceName", ""),
                "contentType": item.get("contentType", ""),
                "summaryBasis": item.get("summaryBasis", ""),
                "insightBasis": item.get("insightBasis", ""),
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

