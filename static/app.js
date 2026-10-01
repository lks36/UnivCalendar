const OWNER = document.body.dataset.owner;
const API_BASE = `/u/${OWNER}`;

const searchInput = document.getElementById("search");
const courseList = document.getElementById("course-list");
const directionBlocks = [...document.querySelectorAll(".direction-block")];
const countLabel = document.getElementById("course-count");
const saveBtn = document.getElementById("save-btn");
const saveResult = document.getElementById("save-result");
const syncBtn = document.getElementById("sync-btn");
const syncStatus = document.getElementById("sync-status");

// ---- 打开时自动展开已有勾选项的分类，方便看到自己之前选过什么 ----
directionBlocks.forEach((block) => {
  if (block.querySelector("input[type=checkbox]:checked")) {
    block.open = true;
  }
});

// ---- 搜索过滤（按方向分区，匹配课程名或方向代码；有匹配自动展开，清空搜索恢复收起）----
searchInput.addEventListener("input", () => {
  const q = searchInput.value.trim().toLowerCase();
  let visibleCourses = 0;

  directionBlocks.forEach((block) => {
    const cards = [...block.querySelectorAll(".course-card")];
    let visibleInBlock = 0;

    cards.forEach((card) => {
      const match = card.dataset.key.includes(q);
      card.classList.toggle("hidden", !match);
      if (match) {
        visibleInBlock += 1;
        visibleCourses += 1;
      }
    });

    block.classList.toggle("hidden", visibleInBlock === 0);
    // 搜索时自动展开命中结果的分类；清空搜索时恢复默认收起状态
    block.open = q.length > 0 && visibleInBlock > 0;
  });

  countLabel.textContent = `${visibleCourses} cours`;
});

// ---- 保存勾选结果 ----
saveBtn.addEventListener("click", async () => {
  const checked = [...courseList.querySelectorAll("input[type=checkbox]:checked")];
  const selection = checked.map((el) => ({
    course_key: el.dataset.course,
    session_type: el.dataset.session,
  }));

  saveBtn.disabled = true;
  saveResult.textContent = "Enregistrement...";
  saveResult.className = "save-result";

  try {
    const res = await fetch(`${API_BASE}/api/save-selection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection }),
    });
    const data = await res.json();
    if (data.ok) {
      saveResult.textContent = `Enregistré : ${data.count} groupe(s) sélectionné(s), ${data.event_count} événement(s) générés`;
      saveResult.className = "save-result ok";
      // 选课变了，日历必须重新从服务器加载（之前的bug：这里没重置，日历一直显示旧数据）
      calendarLoaded = false;
      showTab("calendar");
    } else {
      throw new Error(data.message || "Échec de l'enregistrement");
    }
  } catch (e) {
    saveResult.textContent = `Erreur : ${e.message}`;
    saveResult.className = "save-result err";
  } finally {
    saveBtn.disabled = false;
  }
});

// ---- 手动触发同步 ----
syncBtn.addEventListener("click", async () => {
  syncBtn.disabled = true;
  syncStatus.textContent = "Synchronisation avec le serveur de l'université en cours, cela peut prendre un moment...";
  try {
    const res = await fetch(`/api/sync`, { method: "POST" });
    const data = await res.json();
    syncStatus.textContent = data.message;
    if (data.ok) {
      pollSyncStatus();
    } else {
      syncBtn.disabled = false;
    }
  } catch (e) {
    syncStatus.textContent = `Échec du déclenchement : ${e.message}`;
    syncBtn.disabled = false;
  }
});

function pollSyncStatus() {
  const timer = setInterval(async () => {
    const res = await fetch(`/api/sync-status`);
    const data = await res.json();
    if (!data.running) {
      clearInterval(timer);
      syncStatus.textContent = data.last_result || "Synchronisation terminée";
      syncBtn.disabled = false;
      // 同步可能带来新课程，刷新页面重新渲染课程列表
      setTimeout(() => location.reload(), 800);
    }
  }, 2000);
}

// ==================================================================
// Onglets (Sélection des cours / Mon calendrier)
// ==================================================================
const tabButtons = [...document.querySelectorAll(".tab-btn")];
const tabPanels = [...document.querySelectorAll(".tab-panel")];
let calendarLoaded = false;

function showTab(name) {
  document.querySelector(".layout").classList.toggle("calendar-mode", name === "calendar");
  tabButtons.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  tabPanels.forEach((p) => {
    p.hidden = p.dataset.tabPanel !== name;
  });
  if (name === "calendar" && !calendarLoaded) {
    loadCalendar();
  }
}

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => showTab(btn.dataset.tab));
});

// ==================================================================
// Tout désélectionner
// ==================================================================
const clearBtn = document.getElementById("clear-btn");
clearBtn.addEventListener("click", async () => {
  const checked = [...courseList.querySelectorAll("input[type=checkbox]:checked")];
  if (checked.length === 0) return;

  checked.forEach((el) => (el.checked = false));

  clearBtn.disabled = true;
  saveResult.textContent = "Désélection en cours...";
  saveResult.className = "save-result";
  try {
    const res = await fetch(`${API_BASE}/api/save-selection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection: [] }),
    });
    const data = await res.json();
    if (data.ok) {
      saveResult.textContent = "Tous les cours ont été désélectionnés";
      saveResult.className = "save-result ok";
      calendarLoaded = false; // le calendrier devra être rechargé s'il est rouvert
    } else {
      throw new Error(data.message || "Échec");
    }
  } catch (e) {
    saveResult.textContent = `Erreur : ${e.message}`;
    saveResult.className = "save-result err";
  } finally {
    clearBtn.disabled = false;
  }
});

// ==================================================================
// Calendrier visuel : vues Jour / Semaine / Mois (style app Calendrier)
// ==================================================================
const WEEKDAYS_SHORT = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];
const MONTH_NAMES = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];
const HOUR_PX = 56;          // hauteur d'une heure dans les vues Jour/Semaine
const DEFAULT_START_H = 8;   // plage horaire affichée par défaut
const DEFAULT_END_H = 19;

const cal = {
  events: [],              // [{course_key, session_type, location, start: Date, end: Date}]
  view: window.innerWidth < 700 ? "day" : "week",
  cursor: startOfDay(new Date()),
};

function startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function startOfWeek(d) { const x = startOfDay(d); return addDays(x, -((x.getDay() + 6) % 7)); }
function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate(); }
function dateKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function formatTime(d) { return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); }
function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Couleur stable par cours (même cours = même couleur partout)
function courseColor(key) {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return { bg: `hsl(${h} 75% 93%)`, bar: `hsl(${h} 60% 50%)`, text: `hsl(${h} 55% 28%)` };
}

function eventsOn(day) {
  return cal.events.filter((ev) => sameDay(ev.start, day)).sort((a, b) => a.start - b.start);
}

async function loadCalendar() {
  const loadingEl = document.getElementById("calendar-loading");
  const emptyEl = document.getElementById("calendar-empty");
  const viewEl = document.getElementById("cal-view");

  loadingEl.hidden = false;
  emptyEl.hidden = true;
  viewEl.hidden = true;
  document.getElementById("cal-detail").hidden = true;

  try {
    const res = await fetch(`${API_BASE}/api/calendar`);
    const data = await res.json();
    cal.events = (data.events || []).map((ev) => ({ ...ev, start: new Date(ev.start), end: new Date(ev.end) }));
    loadingEl.hidden = true;
    calendarLoaded = true;

    if (cal.events.length === 0) {
      emptyEl.hidden = false;
      return;
    }
    viewEl.hidden = false;
    renderCalendar();
  } catch (e) {
    loadingEl.hidden = true;
    emptyEl.hidden = false;
    emptyEl.textContent = `Erreur de chargement du calendrier : ${e.message}`;
  }
}

function renderCalendar() {
  document.querySelectorAll(".cal-view-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === cal.view));
  const title = document.getElementById("cal-title");
  const c = cal.cursor;
  if (cal.view === "day") {
    title.textContent = c.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    renderTimeGrid([c]);
  } else if (cal.view === "week") {
    const monday = startOfWeek(c);
    const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
    title.textContent = `${MONTH_NAMES[monday.getMonth()]} ${monday.getFullYear()}`;
    renderTimeGrid(days);
  } else {
    title.textContent = `${MONTH_NAMES[c.getMonth()]} ${c.getFullYear()}`;
    renderMonth(c);
  }
}

// ---- Vues Jour / Semaine : grille horaire ----
function renderTimeGrid(days) {
  const viewEl = document.getElementById("cal-view");
  const today = startOfDay(new Date());

  // Plage horaire : par défaut 8h-19h, élargie si un cours dépasse
  let startH = DEFAULT_START_H, endH = DEFAULT_END_H;
  days.forEach((d) => eventsOn(d).forEach((ev) => {
    startH = Math.min(startH, ev.start.getHours());
    endH = Math.max(endH, ev.end.getHours() + (ev.end.getMinutes() > 0 ? 1 : 0));
  }));
  const bodyHeight = (endH - startH) * HOUR_PX;
  const cols = `56px repeat(${days.length}, minmax(0, 1fr))`;

  let header = `<div class="tg-header" style="grid-template-columns:${cols}"><div></div>`;
  days.forEach((d) => {
    const isToday = sameDay(d, today);
    const weekend = d.getDay() === 0 || d.getDay() === 6;
    header += `<button type="button" class="tg-dayhead${weekend ? " weekend" : ""}" data-date="${dateKey(d)}">
      <span class="tg-daynum${isToday ? " today" : ""}">${d.getDate()}</span>
      <span class="tg-dayname">${WEEKDAYS_SHORT[(d.getDay() + 6) % 7]}</span>
    </button>`;
  });
  header += "</div>";

  let hours = "";
  for (let h = startH; h <= endH; h++) {
    hours += `<div class="tg-hour" style="top:${(h - startH) * HOUR_PX}px">${String(h).padStart(2, "0")}:00</div>`;
  }

  let columns = "";
  days.forEach((d) => {
    const weekend = d.getDay() === 0 || d.getDay() === 6;
    let inner = "";
    layoutDay(eventsOn(d)).forEach(({ ev, lane, lanes }) => {
      const top = ((ev.start.getHours() - startH) * 60 + ev.start.getMinutes()) / 60 * HOUR_PX;
      const height = Math.max(22, (ev.end - ev.start) / 3600000 * HOUR_PX - 2);
      const col = courseColor(ev.course_key);
      const idx = cal.events.indexOf(ev);
      inner += `<button type="button" class="tg-event" data-idx="${idx}"
          style="top:${top}px;height:${height}px;left:calc(${(lane / lanes) * 100}% + 2px);width:calc(${100 / lanes}% - 4px);background:${col.bg};border-left-color:${col.bar};color:${col.text}">
        <span class="tg-ev-title">${esc(ev.course_key)}-${esc(ev.session_type)}</span>
        ${ev.location ? `<span class="tg-ev-meta">📍 ${esc(ev.location)}</span>` : ""}
        <span class="tg-ev-meta">${formatTime(ev.start)}–${formatTime(ev.end)}</span>
      </button>`;
    });
    if (sameDay(d, today)) {
      const now = new Date();
      const mins = (now.getHours() - startH) * 60 + now.getMinutes();
      if (mins >= 0 && mins <= (endH - startH) * 60) {
        inner += `<div class="tg-now" style="top:${mins / 60 * HOUR_PX}px"></div>`;
      }
    }
    columns += `<div class="tg-col${weekend ? " weekend" : ""}">${inner}</div>`;
  });

  viewEl.innerHTML = `${header}
    <div class="tg-body" style="grid-template-columns:${cols};height:${bodyHeight}px;--hour:${HOUR_PX}px">
      <div class="tg-hours">${hours}</div>${columns}
    </div>`;

  viewEl.querySelectorAll(".tg-event").forEach((el) =>
    el.addEventListener("click", () => showEventDetail(cal.events[+el.dataset.idx])));
  // En vue semaine, cliquer sur un jour ouvre la vue Jour
  viewEl.querySelectorAll(".tg-dayhead").forEach((el) =>
    el.addEventListener("click", () => {
      const [y, m, dd] = el.dataset.date.split("-").map(Number);
      cal.cursor = new Date(y, m - 1, dd);
      cal.view = "day";
      renderCalendar();
    }));
}

// Cours qui se chevauchent : affichés côte à côte
function layoutDay(events) {
  const result = [];
  let cluster = [], clusterEnd = null;
  const flush = () => {
    const laneEnds = [];
    const placed = cluster.map((ev) => {
      let lane = laneEnds.findIndex((end) => end <= ev.start);
      if (lane === -1) { lane = laneEnds.length; laneEnds.push(ev.end); } else laneEnds[lane] = ev.end;
      return { ev, lane };
    });
    placed.forEach((p) => result.push({ ...p, lanes: laneEnds.length }));
    cluster = [];
  };
  events.forEach((ev) => {
    if (cluster.length && ev.start >= clusterEnd) flush();
    if (!cluster.length) clusterEnd = ev.end;
    cluster.push(ev);
    if (ev.end > clusterEnd) clusterEnd = ev.end;
  });
  if (cluster.length) flush();
  return result;
}

// ---- Vue Mois ----
function renderMonth(c) {
  const viewEl = document.getElementById("cal-view");
  const today = startOfDay(new Date());
  const first = new Date(c.getFullYear(), c.getMonth(), 1);
  const gridStart = startOfWeek(first);

  let html = `<div class="mv-grid">`;
  WEEKDAYS_SHORT.forEach((w) => (html += `<div class="mv-weekday">${w}</div>`));
  for (let i = 0; i < 42; i++) {
    const d = addDays(gridStart, i);
    if (i >= 35 && d.getMonth() !== c.getMonth()) break; // pas de 6e ligne inutile
    const evs = eventsOn(d);
    const other = d.getMonth() !== c.getMonth();
    let chips = evs.slice(0, 3).map((ev) => {
      const col = courseColor(ev.course_key);
      return `<div class="mv-chip" style="background:${col.bg};color:${col.text};border-left-color:${col.bar}">${formatTime(ev.start)} ${esc(ev.course_key.split("-").slice(1).join("-") || ev.course_key)}</div>`;
    }).join("");
    if (evs.length > 3) chips += `<div class="mv-more">+${evs.length - 3}</div>`;
    html += `<button type="button" class="mv-cell${other ? " other" : ""}" data-date="${dateKey(d)}">
      <span class="mv-daynum${sameDay(d, today) ? " today" : ""}">${d.getDate()}</span>${chips}
    </button>`;
  }
  html += `</div>`;
  viewEl.innerHTML = html;

  viewEl.querySelectorAll(".mv-cell").forEach((el) =>
    el.addEventListener("click", () => {
      const [y, m, dd] = el.dataset.date.split("-").map(Number);
      cal.cursor = new Date(y, m - 1, dd);
      cal.view = "day";
      renderCalendar();
    }));
}

function showEventDetail(ev) {
  const box = document.getElementById("cal-detail");
  const col = courseColor(ev.course_key);
  box.style.borderLeftColor = col.bar;
  box.innerHTML = `<button type="button" class="cal-detail-close" aria-label="Fermer">×</button>
    <div class="cal-detail-title">${esc(ev.course_key)} — ${esc(ev.session_type)}</div>
    <div>${ev.start.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}, ${formatTime(ev.start)}–${formatTime(ev.end)}</div>
    ${ev.location ? `<div>📍 ${esc(ev.location)}</div>` : ""}`;
  box.hidden = false;
  box.querySelector(".cal-detail-close").addEventListener("click", () => (box.hidden = true));
}

// ---- Barre d'outils ----
document.querySelectorAll(".cal-view-btn").forEach((b) =>
  b.addEventListener("click", () => { cal.view = b.dataset.view; renderCalendar(); }));
document.getElementById("cal-today").addEventListener("click", () => { cal.cursor = startOfDay(new Date()); renderCalendar(); });
function shiftCursor(dir) {
  if (cal.view === "day") cal.cursor = addDays(cal.cursor, dir);
  else if (cal.view === "week") cal.cursor = addDays(cal.cursor, 7 * dir);
  else cal.cursor = new Date(cal.cursor.getFullYear(), cal.cursor.getMonth() + dir, 1);
  renderCalendar();
}
document.getElementById("cal-prev").addEventListener("click", () => shiftCursor(-1));
document.getElementById("cal-next").addEventListener("click", () => shiftCursor(1));

// Ligne "maintenant" mise à jour chaque minute
setInterval(() => {
  if (calendarLoaded && cal.view !== "month" && !document.getElementById("cal-view").hidden) renderCalendar();
}, 60000);


// ==================================================================
// Ouverture de la page : calendrier direct si on a déjà choisi ses cours
// ==================================================================
showTab(document.body.dataset.initialTab || "select");

// Copier le lien personnel
const copyLinkBtn = document.getElementById("copy-link-btn");
if (copyLinkBtn) {
  copyLinkBtn.addEventListener("click", async () => {
    const link = document.getElementById("personal-link").textContent.trim();
    try {
      await navigator.clipboard.writeText(link);
      copyLinkBtn.textContent = "Copié !";
    } catch (e) {
      copyLinkBtn.textContent = "Copie impossible, sélectionnez le lien";
    }
    setTimeout(() => (copyLinkBtn.textContent = "Copier le lien"), 2000);
  });
}
