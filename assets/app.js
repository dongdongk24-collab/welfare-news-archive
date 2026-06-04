const archiveEntries = [
  {
    date: "2026-06-03",
    label: "2026년 6월 3일",
    href: "posts/2026-06-03.html",
    summary: "복지 전반 2건, 서울시 1건, 광진구 확인된 뉴스 없음"
  },
  {
    date: "2026-06-01",
    label: "2026년 6월 1일",
    href: "posts/2026-06-01.html",
    summary: "복지 전반 3건, 서울시 3건, 광진구 1건"
  }
];

const normalize = (value) => value.toString().trim().toLowerCase().replace(/\s+/g, " ");
const compactDate = (value) => value.replace(/[^0-9]/g, "");

function renderArchiveList(entries) {
  const list = document.querySelector("[data-archive-list]");
  if (!list) return;

  list.innerHTML = entries.map((entry) => `
    <a class="archive-link" href="${entry.href}">
      <span class="date">${entry.label}</span>
      <span class="summary">${entry.summary}</span>
    </a>
  `).join("");
}

function bindDateSearch() {
  const input = document.querySelector("[data-date-search]");
  const message = document.querySelector("[data-date-message]");
  const button = document.querySelector("[data-date-button]");
  if (!input || !message || !button) return;

  const findEntry = () => {
    const raw = input.value;
    const normalized = normalize(raw);
    const digits = compactDate(raw);

    return archiveEntries.find((entry) => {
      const entryDigits = compactDate(entry.date);
      return entry.date === normalized || entry.label.includes(raw.trim()) || entryDigits === digits;
    });
  };

  const goToDate = () => {
    const entry = findEntry();
    if (entry) {
      window.location.href = entry.href;
      return;
    }

    message.textContent = "아직 해당 날짜의 아카이브가 없습니다.";
  };

  input.addEventListener("input", () => {
    const entry = findEntry();
    message.textContent = entry ? `${entry.label} 페이지가 있습니다.` : "예: 2026-06-03 또는 2026년 6월 3일";
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") goToDate();
  });

  button.addEventListener("click", goToDate);
}

function resultTemplate(item) {
  const stars = "★".repeat(item.rating) + "☆".repeat(5 - item.rating);
  return `
    <article class="result-item">
      <div class="result-meta">${item.dateLabel} · ${item.section} · <span>${stars}</span></div>
      <h3><a href="${item.page}">${item.title}</a></h3>
      <p>${item.summary}</p>
      <p class="source"><a href="${item.url}">원문 보기</a></p>
    </article>
  `;
}

async function bindKeywordSearch() {
  const input = document.querySelector("[data-keyword-search]");
  const results = document.querySelector("[data-search-results]");
  const count = document.querySelector("[data-result-count]");
  if (!input || !results || !count) return;

  let index = [];
  try {
    const response = await fetch("data/search-index.json", { cache: "no-store" });
    index = await response.json();
  } catch (error) {
    results.innerHTML = `<p class="empty">검색 데이터를 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>`;
    return;
  }

  const renderResults = () => {
    const query = normalize(input.value);
    if (!query) {
      count.textContent = "검색어를 입력하면 누적된 기사 중에서 찾아드립니다.";
      results.innerHTML = "";
      return;
    }

    const terms = query.split(" ").filter(Boolean);
    const matches = index.filter((item) => {
      const haystack = normalize([
        item.dateLabel,
        item.section,
        item.title,
        item.summary,
        item.insight,
        ...(item.subtitles || [])
      ].join(" "));
      return terms.every((term) => haystack.includes(term));
    });

    count.textContent = `${matches.length}건을 찾았습니다.`;
    results.innerHTML = matches.length
      ? matches.map(resultTemplate).join("")
      : `<p class="empty">일치하는 기사가 없습니다. 다른 표현으로 검색해 보세요.</p>`;
  };

  input.addEventListener("input", renderResults);
}

renderArchiveList(archiveEntries);
bindDateSearch();
bindKeywordSearch();
