const SIGNAL_LABELS = {
  fire_from_lebanon: "ירי מלבנון",
  idf_strikes_in_lebanon: "תקיפות צה\"ל בלבנון",
  ground_campaign_indicators: "אינדיקציות תמרון קרקעי",
  reserve_mobilization: "גיוס מילואים",
  decision_maker_signals: "איתותי דרג מדיני",
  multi_front_pressure: "לחץ רב-זירתי",
  division_36_specific: "אינדיקציות לאוגדה 36",
  brigade_282_specific: "אינדיקציות לחטיבה 282",
  battalion_9260_specific: "אינדיקציות לגדוד 9260",
};

function colorByScore(score) {
  if (score >= 80) return "#8b1e1e";
  if (score >= 60) return "#c96f00";
  if (score >= 45) return "#8a8f18";
  return "#1f6d43";
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const cols = line.split(",");
    const obj = {};
    header.forEach((h, i) => {
      obj[h] = cols[i] || "";
    });
    return obj;
  });
}

function drawTrend(canvas, rows) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  ctx.strokeStyle = "#d7e2d8";
  ctx.lineWidth = 1;
  for (let y = 20; y <= 220; y += 50) {
    ctx.beginPath();
    ctx.moveTo(40, y);
    ctx.lineTo(w - 20, y);
    ctx.stroke();
  }

  if (!rows.length) return;

  const scores = rows.map((r) => Number(r.score || 0));
  const min = Math.min(...scores, 0);
  const max = Math.max(...scores, 100);
  const xStep = rows.length > 1 ? (w - 70) / (rows.length - 1) : 0;

  ctx.strokeStyle = "#1f6d43";
  ctx.lineWidth = 3;
  ctx.beginPath();
  rows.forEach((r, i) => {
    const score = Number(r.score || 0);
    const x = 40 + i * xStep;
    const y = 220 - ((score - min) / Math.max(max - min, 1)) * 180;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  const last = Number(rows[rows.length - 1].score || 0);
  ctx.fillStyle = colorByScore(last);
  ctx.font = "bold 14px sans-serif";
  ctx.fillText(`נוכחי: ${last.toFixed(2)}`, w - 130, 24);
}

async function load() {
  const [latestRes, histRes] = await Promise.all([
    fetch("./data/latest_index.json?" + Date.now()),
    fetch("./data/history.csv?" + Date.now()),
  ]);

  if (!latestRes.ok) throw new Error("latest_index.json not found");

  const latest = await latestRes.json();
  const historyText = histRes.ok ? await histRes.text() : "";
  const history = historyText ? parseCsv(historyText).slice(-30) : [];

  const score = Number(latest.score || 0);
  const scoreEl = document.getElementById("score-value");
  scoreEl.textContent = score.toFixed(2);
  scoreEl.style.color = colorByScore(score);

  document.getElementById("band").textContent = `רמת סבירות: ${latest.band || "לא זמין"}`;
  document.getElementById("band").style.color = colorByScore(score);
  const updatedAtText = new Date(latest.as_of).toLocaleString("he-IL");
  document.getElementById("updated-at").textContent = `עודכן: ${updatedAtText}`;
  document.getElementById("last-update-date").textContent = `תאריך עדכון אחרון: ${updatedAtText}`;
  document.getElementById("campaign-mode").textContent = latest.assume_wide_campaign
    ? "תרחיש פעיל: מניחים מערכה רחבה בלבנון"
    : "תרחיש פעיל: מצב רגיל (ללא הנחת מערכה רחבה)";
  const misc = latest.misc_signals || {};
  const shimelVal = Number(misc.shimel_loser ?? 0);
  document.getElementById("meta").textContent = `כתבות שנסרקו: ${latest.articles_scanned || 0} | בוסט מערכה: ${latest.wide_campaign_boost || 0} | בוסט ידני: ${latest.manual_boost || 0} | שימל. לוזר: ${shimelVal}`;

  const signalsBox = document.getElementById("signals");
  signalsBox.innerHTML = "";
  const scores = latest.signal_scores || {};
  const hits = latest.signal_hits || {};
  Object.keys(scores).forEach((key) => {
    const v = Number(scores[key] || 0);
    const title = SIGNAL_LABELS[key] || key;
    const card = document.createElement("article");
    card.className = "signal";
    card.innerHTML = `
      <div class="signal-title">${title}</div>
      <div class="bar"><i style="width:${Math.max(0, Math.min(100, v))}%;background:${colorByScore(v)}"></i></div>
      <div class="signal-foot">ציון: ${v.toFixed(1)} | ידיעות: ${hits[key] || 0}</div>
    `;
    signalsBox.appendChild(card);
  });

  const miscCard = document.createElement("article");
  miscCard.className = "signal";
  miscCard.innerHTML = `
    <div class="signal-title">שימל. לוזר</div>
    <div class="bar"><i style="width:${Math.max(0, Math.min(100, shimelVal))}%;background:#586174"></i></div>
    <div class="signal-foot">ציון: ${shimelVal}</div>
  `;
  signalsBox.appendChild(miscCard);

  drawTrend(document.getElementById("trend"), history);
}

load().catch((err) => {
  document.getElementById("updated-at").textContent = `שגיאה בטעינת נתונים: ${err.message}`;
});
