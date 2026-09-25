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
    const res = await fetch("/api/save-selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection }),
    });
    const data = await res.json();
    if (data.ok) {
      saveResult.textContent = `Enregistré : ${data.count} groupe(s) sélectionné(s), ${data.event_count} événement(s) générés`;
      saveResult.className = "save-result ok";
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
    const res = await fetch("/api/sync", { method: "POST" });
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
    const res = await fetch("/api/sync-status");
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

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => b.classList.toggle("active", b === btn));
    tabPanels.forEach((p) => {
      p.hidden = p.dataset.tabPanel !== btn.dataset.tab;
    });
    if (btn.dataset.tab === "calendar" && !calendarLoaded) {
      loadCalendar();
    }
  });
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
    const res = await fetch("/api/save-selection", {
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
// Calendrier visuel : agenda 14 jours + vue mensuelle 4 mois
// ==================================================================
const WEEKDAYS_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const MONTH_NAMES = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

function dateKey(d) {
  // clé locale YYYY-MM-DD (pas d.toISOString() qui bascule en UTC)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatTime(d) {
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

async function loadCalendar() {
  const loadingEl = document.getElementById("calendar-loading");
  const emptyEl = document.getElementById("calendar-empty");
  const contentEl = document.getElementById("calendar-content");

  loadingEl.hidden = false;
  emptyEl.hidden = true;
  contentEl.hidden = true;

  try {
    const res = await fetch("/api/calendar");
    const data = await res.json();
    const events = data.events || [];

    loadingEl.hidden = true;
    calendarLoaded = true;

    if (events.length === 0) {
      emptyEl.hidden = false;
      return;
    }
    contentEl.hidden = false;

    // Regrouper les événements par jour (clé locale)
    const byDay = new Map();
    events.forEach((ev) => {
      const start = new Date(ev.start);
      const key = dateKey(start);
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key).push(ev);
    });
    byDay.forEach((list) => list.sort((a, b) => new Date(a.start) - new Date(b.start)));

    renderAgenda(byDay);
    renderMonthGrids(byDay);
  } catch (e) {
    loadingEl.hidden = true;
    emptyEl.hidden = false;
    emptyEl.textContent = `Erreur de chargement du calendrier : ${e.message}`;
  }
}

function renderAgenda(byDay) {
  const container = document.getElementById("agenda-list");
  container.innerHTML = "";

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = 0; i < 14; i++) {
    const day = new Date(today);
    day.setDate(today.getDate() + i);
    const key = dateKey(day);
    const dayEvents = byDay.get(key);
    if (!dayEvents || dayEvents.length === 0) continue;

    const dayBlock = document.createElement("div");
    dayBlock.className = "agenda-day";

    const label = document.createElement("div");
    label.className = "agenda-day-label";
    label.textContent = `${WEEKDAYS_SHORT[(day.getDay() + 6) % 7]} ${day.getDate()} ${MONTH_NAMES[day.getMonth()]}`;
    dayBlock.appendChild(label);

    dayEvents.forEach((ev) => {
      const row = document.createElement("div");
      row.className = "agenda-event";
      const start = new Date(ev.start);
      const end = new Date(ev.end);
      row.innerHTML = `
        <span class="agenda-time">${formatTime(start)}–${formatTime(end)}</span>
        <span class="agenda-course">${ev.course_key} <span class="agenda-session">${ev.session_type}</span></span>
        ${ev.location ? `<span class="agenda-location">${ev.location}</span>` : ""}
      `;
      dayBlock.appendChild(row);
    });

    container.appendChild(dayBlock);
  }

  if (container.children.length === 0) {
    container.innerHTML = '<p class="side-hint">Aucun cours dans les 14 prochains jours.</p>';
  }
}

function renderMonthGrids(byDay) {
  const container = document.getElementById("month-grids");
  container.innerHTML = "";

  const today = new Date();
  const detailPanel = document.createElement("div");
  detailPanel.className = "day-detail";
  detailPanel.id = "day-detail";
  detailPanel.textContent = "Cliquez sur un jour marqué pour voir le détail.";

  for (let m = 0; m < 4; m++) {
    const monthDate = new Date(today.getFullYear(), today.getMonth() + m, 1);
    container.appendChild(buildMonthGrid(monthDate, byDay));
  }

  container.after(detailPanel);
}

function buildMonthGrid(monthDate, byDay) {
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startOffset = (firstDay.getDay() + 6) % 7; // lundi = 0

  const wrapper = document.createElement("div");
  wrapper.className = "month-card";

  const title = document.createElement("div");
  title.className = "month-title";
  title.textContent = `${MONTH_NAMES[month]} ${year}`;
  wrapper.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "month-grid";

  WEEKDAYS_SHORT.forEach((w) => {
    const head = document.createElement("div");
    head.className = "month-weekday";
    head.textContent = w[0];
    grid.appendChild(head);
  });

  for (let i = 0; i < startOffset; i++) {
    grid.appendChild(document.createElement("div"));
  }

  for (let day = 1; day <= lastDay.getDate(); day++) {
    const cellDate = new Date(year, month, day);
    const key = dateKey(cellDate);
    const hasEvents = byDay.has(key);

    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "month-day" + (hasEvents ? " has-event" : "");
    cell.textContent = day;

    if (hasEvents) {
      cell.addEventListener("click", () => showDayDetail(key, cellDate, byDay.get(key)));
    } else {
      cell.disabled = true;
    }
    grid.appendChild(cell);
  }

  wrapper.appendChild(grid);
  return wrapper;
}

function showDayDetail(key, date, dayEvents) {
  const panel = document.getElementById("day-detail");
  const label = `${WEEKDAYS_SHORT[(date.getDay() + 6) % 7]} ${date.getDate()} ${MONTH_NAMES[date.getMonth()]}`;
  const rows = dayEvents
    .map((ev) => {
      const start = new Date(ev.start);
      const end = new Date(ev.end);
      return `<div class="agenda-event">
        <span class="agenda-time">${formatTime(start)}–${formatTime(end)}</span>
        <span class="agenda-course">${ev.course_key} <span class="agenda-session">${ev.session_type}</span></span>
        ${ev.location ? `<span class="agenda-location">${ev.location}</span>` : ""}
      </div>`;
    })
    .join("");
  panel.innerHTML = `<div class="agenda-day-label">${label}</div>${rows}`;
}
