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
const pad = (value) => value.toString().padStart(2, "0");
const formatDate = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

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
  const toggle = document.querySelector("[data-calendar-toggle]");
  const calendar = document.querySelector("[data-calendar]");
  const field = document.querySelector(".calendar-field");
  if (!input || !message || !button || !toggle || !calendar || !field) return;

  const availableDates = new Set(archiveEntries.map((entry) => entry.date));
  let selectedDate = archiveEntries[0]?.date || formatDate(new Date());
  let viewDate = new Date(`${selectedDate}T00:00:00`);

  const findEntry = () => {
    const raw = input.value;
    const normalized = normalize(raw);
    const digits = compactDate(raw);

    return archiveEntries.find((entry) => {
      const entryDigits = compactDate(entry.date);
      return entry.date === normalized || entry.label.includes(raw.trim()) || entryDigits === digits;
    });
  };

  const syncMessage = () => {
    const entry = findEntry();
    message.textContent = entry ? `${entry.label} 페이지가 있습니다.` : "아직 해당 날짜의 아카이브가 없습니다.";
  };

  const openCalendar = () => {
    calendar.hidden = false;
    renderCalendar();
  };

  const closeCalendar = () => {
    calendar.hidden = true;
  };

  const toggleCalendar = (event) => {
    event.stopPropagation();
    if (calendar.hidden) openCalendar();
    else closeCalendar();
  };

  const goToDate = () => {
    const entry = findEntry();
    if (entry) {
      window.location.href = entry.href;
      return;
    }

    message.textContent = "아직 해당 날짜의 아카이브가 없습니다.";
  };

  function renderCalendar() {
    const year = viewDate.getFullYear();
    const month = viewDate.getMonth();
    const first = new Date(year, month, 1);
    const start = new Date(year, month, 1 - first.getDay());
    const weekdays = ["일", "월", "화", "수", "목", "금", "토"];

    const days = Array.from({ length: 42 }, (_, index) => {
      const day = new Date(start);
      day.setDate(start.getDate() + index);
      const value = formatDate(day);
      const outside = day.getMonth() !== month;
      const available = availableDates.has(value);
      const selected = value === selectedDate;
      const className = [
        "calendar-day",
        outside ? "outside" : "",
        available ? "available" : "unavailable",
        selected ? "selected" : ""
      ].filter(Boolean).join(" ");

      return `<button class="${className}" type="button" data-calendar-date="${value}">${day.getDate()}</button>`;
    }).join("");

    calendar.innerHTML = `
      <div class="calendar-head">
        <button class="calendar-nav" type="button" aria-label="이전 달" data-calendar-prev>‹</button>
        <div class="calendar-title">${year}년 ${month + 1}월</div>
        <button class="calendar-nav" type="button" aria-label="다음 달" data-calendar-next>›</button>
      </div>
      <div class="calendar-weekdays">${weekdays.map((day) => `<span>${day}</span>`).join("")}</div>
      <div class="calendar-grid">${days}</div>
    `;
  }

  input.value = selectedDate;
  syncMessage();

  input.addEventListener("click", (event) => {
    event.stopPropagation();
    openCalendar();
  });
  input.addEventListener("focus", openCalendar);
  toggle.addEventListener("click", toggleCalendar);
  button.addEventListener("click", goToDate);

  calendar.addEventListener("click", (event) => {
    event.stopPropagation();
    const previous = event.target.closest("[data-calendar-prev]");
    const next = event.target.closest("[data-calendar-next]");
    const day = event.target.closest("[data-calendar-date]");

    if (previous) {
      event.preventDefault();
      viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1);
      renderCalendar();
      return;
    }

    if (next) {
      event.preventDefault();
      viewDate = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1);
      renderCalendar();
      return;
    }

    if (day) {
      selectedDate = day.dataset.calendarDate;
      input.value = selectedDate;
      viewDate = new Date(`${selectedDate}T00:00:00`);
      syncMessage();
      renderCalendar();
    }
  });

  field.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  document.addEventListener("click", (event) => {
    if (!field.contains(event.target)) closeCalendar();
  });
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
