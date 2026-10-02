const OWNER = document.body.dataset.owner;
const API_BASE = `/u/${OWNER}`;

const searchInput = document.getElementById("search");
const courseList = document.getElementById("course-list");
const countLabel = document.getElementById("course-count");
const saveBtn = document.getElementById("save-btn");
const clearBtn = document.getElementById("clear-btn");
const saveResult = document.getElementById("save-result");
const selectedCountEl = document.getElementById("selected-count");

function esc(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}


// ==================================================================
// Date de dernière mise à jour des cours
// ==================================================================
(function showLastSynced() {
  const el = document.getElementById("sync-status");
  const raw = el.dataset.lastSynced;
  if (!raw) { el.textContent = ""; return; }
  const d = new Date(raw);
  const mins = Math.round((Date.now() - d) / 60000);
  let rel;
  if (mins < 2) rel = "à l'instant";
  else if (mins < 60) rel = `il y a ${mins} min`;
  else if (mins < 60 * 24) rel = `il y a ${Math.round(mins / 60)} h`;
  else rel = `le ${d.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`;
  el.textContent = `Cours mis à jour ${rel}`;
  el.title = d.toLocaleString("fr-FR");
})();

// ==================================================================
// Sélection des cours : chargée seulement à la première ouverture de l'onglet
// ==================================================================
let coursesLoaded = false;
let coursesLoading = false;
let directionBlocks = [];

async function loadCourses() {
  if (coursesLoaded || coursesLoading) return;
  coursesLoading = true;
  try {
    const res = await fetch(`${API_BASE}/api/courses`);
    const data = await res.json();
    renderCourses(data);
    coursesLoaded = true;
  } catch (e) {
    courseList.innerHTML = `<div class="calendar-empty">Erreur de chargement : ${esc(e.message)} <button type="button" class="btn btn-ghost" id="retry-courses">Réessayer</button></div>`;
    document.getElementById("retry-courses").addEventListener("click", loadCourses);
  } finally {
    coursesLoading = false;
  }
}

function renderCourses(data) {
  const selected = new Set(data.selected.map(([c, s]) => `${c}\u0000${s}`));
  if (!data.groups.length) {
    courseList.innerHTML = `<div class="calendar-empty">Aucun cours disponible pour le moment (synchronisation pas encore effectuée).</div>`;
    countLabel.textContent = "";
    return;
  }
  // Construction en une seule chaîne HTML : beaucoup plus rapide que des centaines d'appels DOM
  let html = "";
  for (const g of data.groups) {
    let open = false;
    let cards = "";
    for (const c of g.courses) {
      let chips = "";
      for (const [sessionKey, label] of c.sessions) {
        const checked = selected.has(`${c.course_key}\u0000${sessionKey}`);
        if (checked) open = true;
        chips += `<label class="chip"><input type="checkbox" data-course="${esc(c.course_key)}" data-session="${esc(sessionKey)}"${checked ? " checked" : ""}><span>${esc(label)}</span></label>`;
      }
      cards += `<div class="course-card" data-key="${esc((c.course_key + " " + g.master_group).toLowerCase())}">
        <div class="course-title"><span class="course-name">${esc(c.course_key)}</span></div>
        <div class="session-row">${chips}</div></div>`;
    }
    html += `<details class="direction-block"${open ? " open" : ""}>
      <summary class="direction-title">${esc(g.master_group)} <span class="direction-count">(${g.courses.length})</span></summary>
      <div class="direction-courses">${cards}</div></details>`;
  }
  courseList.innerHTML = html;
  directionBlocks = [...courseList.querySelectorAll(".direction-block")];
  countLabel.textContent = `${data.total} cours`;
  updateSelectedCount();
  if (searchInput.value) searchInput.dispatchEvent(new Event("input"));
}

function currentSelection() {
  return [...courseList.querySelectorAll("input[type=checkbox]:checked")].map((el) => ({
    course_key: el.dataset.course,
    session_type: el.dataset.session,
  }));
}

function updateSelectedCount() {
  const n = courseList.querySelectorAll("input[type=checkbox]:checked").length;
  selectedCountEl.textContent = n === 0 ? "Aucun groupe sélectionné" : `${n} groupe${n > 1 ? "s" : ""} sélectionné${n > 1 ? "s" : ""}`;
}

// ---- Recherche ----
searchInput.addEventListener("input", () => {
  const q = searchInput.value.trim().toLowerCase();
  let visibleCourses = 0;
  directionBlocks.forEach((block) => {
    let visibleInBlock = 0;
    block.querySelectorAll(".course-card").forEach((card) => {
      const match = card.dataset.key.includes(q);
      card.classList.toggle("hidden", !match);
      if (match) { visibleInBlock += 1; visibleCourses += 1; }
    });
    block.classList.toggle("hidden", visibleInBlock === 0);
    if (q) block.open = visibleInBlock > 0;
  });
  if (coursesLoaded) countLabel.textContent = `${visibleCourses} cours`;
});

// ---- Enregistrement automatique (plus besoin de cliquer sur "Enregistrer") ----
let saveTimer = null;
let saveSeq = 0;
let pendingSave = null;

function setSaveStatus(text, cls = "") {
  saveResult.textContent = text;
  saveResult.className = `save-result ${cls}`;
}

function scheduleSave() {
  updateSelectedCount();
  setSaveStatus("Modifications non enregistrées…");
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 600);
}

async function saveNow() {
  clearTimeout(saveTimer);
  saveTimer = null;
  const seq = ++saveSeq;
  setSaveStatus("Enregistrement…");
  const p = (async () => {
    const res = await fetch(`${API_BASE}/api/save-selection`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection: currentSelection() }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (seq !== saveSeq) return; // une sauvegarde plus récente est en cours
    // Le serveur renvoie directement le nouveau calendrier : pas de 2e requête
    setCalendarEvents(data.events);
    setSaveStatus("Enregistré ✓", "ok");
  })();
  pendingSave = p;
  try { await p; } catch (e) {
    if (seq === saveSeq) setSaveStatus(`Erreur d'enregistrement : ${e.message}`, "err");
  } finally {
    if (pendingSave === p) pendingSave = null;
  }
}

courseList.addEventListener("change", (e) => {
  if (e.target.matches("input[type=checkbox]")) scheduleSave();
});

// "Voir mon calendrier" : enregistre tout de suite si besoin, puis bascule
saveBtn.addEventListener("click", async () => {
  if (saveTimer) await saveNow();
  else if (pendingSave) { try { await pendingSave; } catch (e) {} }
  showTab("calendar");
});

clearBtn.addEventListener("click", () => {
  const checked = [...courseList.querySelectorAll("input[type=checkbox]:checked")];
  if (checked.length === 0) return;
  if (!confirm(`Désélectionner les ${checked.length} groupes ?`)) return;
  checked.forEach((el) => (el.checked = false));
  scheduleSave();
});

// Avertir si on quitte la page avant la fin de l'enregistrement
window.addEventListener("beforeunload", (e) => {
  if (saveTimer || pendingSave) { e.preventDefault(); e.returnValue = ""; }
});

// ==================================================================
// Onglets
// ==================================================================
const tabButtons = [...document.querySelectorAll(".tab-btn")];
const tabPanels = [...document.querySelectorAll(".tab-panel")];
let calendarLoaded = false;

function showTab(name) {
  document.querySelector(".layout").classList.toggle("calendar-mode", name === "calendar");
  tabButtons.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  tabPanels.forEach((p) => { p.hidden = p.dataset.tabPanel !== name; });
  if (name === "calendar") {
    if (!calendarLoaded) loadCalendar(); else renderCalendar();
  } else {
    loadCourses();
  }
}

tabButtons.forEach((btn) => btn.addEventListener("click", () => showTab(btn.dataset.tab)));

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
  view: (() => {
    try { const v = localStorage.getItem("cal-view"); if (["day", "week", "month"].includes(v)) return v; } catch (e) {}
    return window.innerWidth < 700 ? "day" : "week";
  })(),
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

// Couleur stable par cours (même cours = même couleur partout)
function courseColor(key) {
  let h = 0;
  for (const ch of key) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return { bg: `hsl(${h} 75% 93%)`, bar: `hsl(${h} 60% 50%)`, text: `hsl(${h} 55% 28%)` };
}

function eventsOn(day) {
  return cal.events.filter((ev) => sameDay(ev.start, day)).sort((a, b) => a.start - b.start);
}

function setCalendarEvents(raw) {
  cal.events = (raw || []).map((ev) => ({ ...ev, start: new Date(ev.start), end: new Date(ev.end) }));
  calendarLoaded = true;
  const visible = !document.querySelector('[data-tab-panel="calendar"]').hidden;
  if (visible) renderCalendar();
}

async function loadCalendar() {
  const inline = document.getElementById("initial-events");
  if (inline && !calendarLoaded) {
    // Données déjà incluses dans la page : affichage immédiat, sans requête
    const data = JSON.parse(inline.textContent || "[]");
    inline.remove();
    calendarLoaded = true;
    cal.events = data.map((ev) => ({ ...ev, start: new Date(ev.start), end: new Date(ev.end) }));
    renderCalendar();
    return;
  }
  document.getElementById("calendar-loading").hidden = false;
  try {
    const res = await fetch(`${API_BASE}/api/calendar`);
    const data = await res.json();
    calendarLoaded = true;
    cal.events = (data.events || []).map((ev) => ({ ...ev, start: new Date(ev.start), end: new Date(ev.end) }));
    renderCalendar();
  } catch (e) {
    document.getElementById("calendar-loading").hidden = true;
    const emptyEl = document.getElementById("calendar-empty");
    emptyEl.hidden = false;
    emptyEl.textContent = `Erreur de chargement du calendrier : ${e.message}`;
  }
}

function renderCalendar() {
  try { localStorage.setItem("cal-view", cal.view); } catch (e) {}
  document.getElementById("calendar-loading").hidden = true;
  const empty = cal.events.length === 0;
  document.getElementById("calendar-empty").hidden = !empty;
  document.getElementById("cal-view").hidden = empty;
  if (empty) return;
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


// Clavier : ← / → pour changer de période, T pour aujourd'hui
document.addEventListener("keydown", (e) => {
  if (document.querySelector('[data-tab-panel="calendar"]').hidden) return;
  if (e.target.matches("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "ArrowLeft") shiftCursor(-1);
  else if (e.key === "ArrowRight") shiftCursor(1);
  else if (e.key === "t" || e.key === "T") { cal.cursor = startOfDay(new Date()); renderCalendar(); }
  else if (e.key === "Escape") document.getElementById("cal-detail").hidden = true;
});

// Mobile : glisser à gauche / à droite pour changer de période
(function enableSwipe() {
  const el = document.getElementById("cal-view");
  let x0 = null, y0 = null;
  el.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
  el.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    const dy = e.changedTouches[0].clientY - y0;
    x0 = null;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) shiftCursor(dx < 0 ? 1 : -1);
  }, { passive: true });
})();

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
