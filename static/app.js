const searchInput = document.getElementById("search");
const courseList = document.getElementById("course-list");
const courseCards = [...document.querySelectorAll(".course-card")];
const countLabel = document.getElementById("course-count");
const saveBtn = document.getElementById("save-btn");
const saveResult = document.getElementById("save-result");
const syncBtn = document.getElementById("sync-btn");
const syncStatus = document.getElementById("sync-status");

// ---- 搜索过滤 ----
searchInput.addEventListener("input", () => {
  const q = searchInput.value.trim().toLowerCase();
  let visible = 0;
  courseCards.forEach((card) => {
    const match = card.dataset.key.includes(q);
    card.classList.toggle("hidden", !match);
    if (match) visible += 1;
  });
  countLabel.textContent = `${visible} 门课程`;
});

// ---- 保存勾选结果 ----
saveBtn.addEventListener("click", async () => {
  const checked = [...courseList.querySelectorAll("input[type=checkbox]:checked")];
  const selection = checked.map((el) => ({
    course_key: el.dataset.course,
    session_type: el.dataset.session,
  }));

  saveBtn.disabled = true;
  saveResult.textContent = "保存中...";
  saveResult.className = "save-result";

  try {
    const res = await fetch("/api/save-selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selection }),
    });
    const data = await res.json();
    if (data.ok) {
      saveResult.textContent = `已保存 ${data.count} 个场次，生成了 ${data.event_count} 条日历事件`;
      saveResult.className = "save-result ok";
    } else {
      throw new Error(data.message || "保存失败");
    }
  } catch (e) {
    saveResult.textContent = `出错了：${e.message}`;
    saveResult.className = "save-result err";
  } finally {
    saveBtn.disabled = false;
  }
});

// ---- 手动触发同步 ----
syncBtn.addEventListener("click", async () => {
  syncBtn.disabled = true;
  syncStatus.textContent = "正在从学校服务器同步，可能需要一点时间...";
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
    syncStatus.textContent = `触发失败：${e.message}`;
    syncBtn.disabled = false;
  }
});

function pollSyncStatus() {
  const timer = setInterval(async () => {
    const res = await fetch("/api/sync-status");
    const data = await res.json();
    if (!data.running) {
      clearInterval(timer);
      syncStatus.textContent = data.last_result || "同步完成";
      syncBtn.disabled = false;
      // 同步可能带来新课程，刷新页面重新渲染课程列表
      setTimeout(() => location.reload(), 800);
    }
  }, 2000);
}
