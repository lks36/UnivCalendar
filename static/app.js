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
