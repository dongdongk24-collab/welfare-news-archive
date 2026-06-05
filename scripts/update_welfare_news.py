import json
import os
import re
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "posts"
DATA = ROOT / "data"
APP_JS = ROOT / "assets" / "app.js"
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")


def yesterday_kst():
    return (datetime.now(KST).date() - timedelta(days=1)).isoformat()


def korean_date(value):
    y, m, d = map(int, value.split("-"))
    return f"{y}년 {m}월 {d}일"


def stars(n):
    n = max(1, min(5, int(n or 1)))
    return "★" * n + "☆" * (5 - n)


def call_openai(target_date, existing_titles):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY secret is not set")

    prompt = f"""
You are a Korean welfare news assistant for a social worker at a comprehensive social welfare center in Gwangjin-gu.
Target date: {target_date} 00:00-23:59 Asia/Seoul. Include only welfare-related news or official press releases published on that date.

Categories:
1. 복지 전반에 관련된 주요 뉴스
2. 서울시 복지 정책 및 복지 현장 관련 뉴스
3. 광진구 지역 복지 관련 뉴스

Topics include welfare policy, care, older adults, disability, children/youth, youth support, single-person households, social isolation, housing welfare, self-support, low-income support, community welfare, welfare agencies.

Use reliable media, government, local government, public institution, or official organization links. Exclude blogs, ads, dead links, old articles, and duplicates.
Existing titles to avoid:
{json.dumps(existing_titles, ensure_ascii=False)}

Return JSON only:
{{
  "date": "{target_date}",
  "title": "{korean_date(target_date)} 복지 뉴스",
  "sections": [
    {{
      "name": "복지 전반에 관련된 주요 뉴스",
      "items": [
        {{
          "rating": 1,
          "title": "title",
          "subtitles": ["핵심 내용", "배경 또는 영향"],
          "summary": "facts and figures in Korean",
          "insight": "social worker perspective in Korean",
          "sourceName": "source name",
          "url": "https://..."
        }}
      ],
      "note": "if fewer than 3 items, explain briefly"
    }}
  ],
  "excluded": ["short reasons"]
}}
"""
    body = {
        "model": MODEL,
        "tools": [{"type": "web_search"}],
        "input": prompt,
        "text": {"format": {"type": "json_object"}},
    }
    req = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=180) as res:
        payload = json.loads(res.read().decode("utf-8"))
    text = payload.get("output_text")
    if not text:
        parts = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    parts.append(content.get("text", ""))
        text = "".join(parts)
    if not text:
        raise RuntimeError("OpenAI response did not contain text")
    return json.loads(text)


def load_existing_titles():
    titles = []
    for path in DATA.glob("news-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for section in data.get("sections", []):
            for item in section.get("items", []):
                if item.get("title"):
                    titles.append(item["title"])
    return titles


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
  <p class="source">참고 URL: <a href="{url}">{source}</a></p>
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
  <link rel="stylesheet" href="../assets/style.css?v={date.replace('-', '')}">
</head>
<body>
  <header class="site-header">
    <div>
      <nav class="detail-nav" aria-label="상세 페이지 이동"><a class="nav-button" href="../index.html">홈으로</a><a class="nav-button" href="../index.html#latest-title">날짜 목록</a></nav>
      <p class="eyebrow">Daily Welfare News</p>
      <h1>{escape(title)}</h1>
      <p class="lead">{escape(date)} 00:00~23:59(KST)에 보도된 복지 뉴스를 사회복지 실무 관점으로 정리했습니다.</p>
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
    if f'date: "{date}"' in text:
        return
    entry = f'''  {{
    date: "{date}",
    label: "{korean_date(date)}",
    href: "posts/{date}.html",
    summary: "{section_counts(data)}"
  }},
'''
    text = re.sub(r"const archiveEntries = \[\n", "const archiveEntries = [\n" + entry, text, count=1)
    APP_JS.write_text(text, encoding="utf-8")


def update_search_index(data):
    path = DATA / "search-index.json"
    index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    existing = {(i.get("date"), i.get("title"), i.get("url")) for i in index}
    additions = []
    for section in data.get("sections", []):
        for item in section.get("items", []):
            key = (data["date"], item.get("title"), item.get("url"))
            if key in existing:
                continue
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
    if additions:
        path.write_text(json.dumps(additions + index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    target_date = os.environ.get("TARGET_DATE") or yesterday_kst()
    existing_titles = load_existing_titles()
    data = call_openai(target_date, existing_titles)
    data["date"] = target_date

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
