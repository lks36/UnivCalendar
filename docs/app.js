const WEEKDAYS_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const MONTH_NAMES = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

function dateKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function formatTime(d) {
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

// 订阅地址用当前页面的完整绝对地址拼出来，方便直接复制到手机日历
document.getElementById("ics-url").textContent =
  new URL("mon_emploi_du_temps.ics", window.location.href).href;

async function loadCalendar() {
  const loadingEl = document.getElementById("calendar-loading");
  const emptyEl = document.getElementById("calendar-empty");
  const contentEl = document.getElementById("calendar-content");
  const generatedAtEl = document.getElementById("generated-at");

  try {
    const res = await fetch("calendar-data.json", { cache: "no-store" });
    const data = await res.json();
    const events = data.events || [];

    if (data.generated_at) {
      const gen = new Date(data.generated_at);
      generatedAtEl.textContent = `Mis à jour le ${gen.toLocaleString("fr-FR")}`;
    }

    loadingEl.hidden = true;

    if (events.length === 0) {
      emptyEl.hidden = false;
      return;
    }
    contentEl.hidden = false;

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
  const startOffset = (firstDay.getDay() + 6) % 7;

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
      cell.addEventListener("click", () => showDayDetail(cellDate, byDay.get(key)));
    } else {
      cell.disabled = true;
    }
    grid.appendChild(cell);
  }

  wrapper.appendChild(grid);
  return wrapper;
}

function showDayDetail(date, dayEvents) {
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

loadCalendar();
