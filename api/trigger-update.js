const OWNER = process.env.GITHUB_OWNER || "dongdongk24-collab";
const REPO = process.env.GITHUB_REPO || "welfare-news-archive";
const WORKFLOW_ID = process.env.GITHUB_WORKFLOW_ID || "daily-welfare-news.yml";
const REF = process.env.GITHUB_REF || "main";

function json(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    return json(res, 405, { ok: false, message: "POST 요청만 사용할 수 있습니다." });
  }

  const token = process.env.GITHUB_WORKFLOW_TOKEN;
  if (!token) {
    return json(res, 500, {
      ok: false,
      message: "Vercel 환경변수 GITHUB_WORKFLOW_TOKEN이 설정되어 있지 않습니다.",
    });
  }

  const pin = process.env.UPDATE_PIN;
  if (pin) {
    const provided = req.headers["x-update-pin"];
    if (provided !== pin) {
      return json(res, 401, { ok: false, message: "실행 비밀번호가 맞지 않습니다." });
    }
  }

  const targetDate = typeof req.query?.target_date === "string" ? req.query.target_date : "";
  const payload = { ref: REF, inputs: {} };
  if (/^\d{4}-\d{2}-\d{2}$/.test(targetDate)) {
    payload.inputs.target_date = targetDate;
  }

  const url = `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW_ID}/dispatches`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "welfare-news-archive-vercel",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    return json(res, response.status, {
      ok: false,
      message: "GitHub Actions 실행 요청에 실패했습니다.",
      detail: text.slice(0, 500),
    });
  }

  return json(res, 202, {
    ok: true,
    message: targetDate
      ? `${targetDate} 뉴스 수집 작업을 시작했습니다. 보통 1~3분 뒤 새로고침하면 반영됩니다.`
      : "밀린 날짜의 뉴스 수집 작업을 시작했습니다. 저장되지 않은 날짜를 어제까지 순서대로 만들며, 보통 1~3분 뒤 새로고침하면 반영됩니다.",
  });
};
