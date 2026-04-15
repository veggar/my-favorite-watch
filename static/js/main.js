// ===== 카드 펼침/접기 =====
function toggleCard(id) {
  const detail = document.getElementById("detail-" + id);
  if (!detail) return;
  const visible = detail.style.display !== "none";
  detail.style.display = visible ? "none" : "block";
}

// ===== 관람 여부 토글 (AJAX) =====
async function toggleWatched(id, currentWatched) {
  const newWatched = currentWatched === "true" || currentWatched === true ? false : true;
  const url = TOGGLE_WATCHED_URL.replace("__ID__", id);
  showLoading(true);
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ watched: newWatched }),
    });
    const data = await resp.json();
    if (data.ok) {
      location.reload();
    } else {
      alert("변경에 실패했습니다. 다시 시도해주세요.");
    }
  } catch {
    alert("네트워크 오류가 발생했습니다.");
  } finally {
    showLoading(false);
  }
}

// ===== 등록 모달 =====
function openRegisterModal() {
  resetForm();
  document.getElementById("register-overlay").style.display = "flex";
  document.getElementById("reg-form-title").focus();
}

function closeModal(name) {
  document.getElementById(name + "-overlay").style.display = "none";
}

// ===== 수정 모달 =====
let _currentEditId = null;

function openEditModal(id) {
  const item = ITEMS_DATA.find(it => it.id === id);
  if (!item) return;
  _currentEditId = id;

  // 폼 액션 설정
  const form = document.getElementById("edit-form");
  form.action = UPDATE_URL_TEMPLATE.replace("__ID__", id);

  // 필드 채우기
  document.getElementById("edit-form-title").value = item.title || "";
  document.getElementById("edit-form-category").value = item.category || "";
  document.getElementById("edit-form-genre").value = item.genre || "";
  document.getElementById("edit-form-officialRating").value = item.officialRating || "";
  document.getElementById("edit-form-originalTitle").value = item.originalTitle || "";
  document.getElementById("edit-form-titleLink").value = item.titleLink || "";
  document.getElementById("edit-form-review").value = item.review || "";
  document.getElementById("edit-form-synopsis").value = item.synopsis || "";
  document.getElementById("edit-original-title").value = item.title || "";

  const rating = parseFloat(item.rating) || 0;
  document.getElementById("edit-form-rating").value = rating;
  document.getElementById("edit-rating-display").textContent = rating;

  const watched = (item.watched || "").toLowerCase() === "true";
  setWatched(watched, "edit");

  if (item.watchedAt) {
    document.getElementById("edit-form-watchedAt").value = item.watchedAt.slice(0, 10);
  }

  // "업데이트 by TMDb" 버튼 노출
  document.getElementById("edit-btn-tmdb-update").style.display = "block";
  document.getElementById("edit-tmdb-update-result").style.display = "none";
  document.getElementById("edit-tmdb-update-result").textContent = "";

  // title 변경 감지 → 링크 재검색 여부 물어보기
  document.getElementById("edit-form-title").addEventListener("change", function () {
    const newTitle = this.value.trim();
    const original = document.getElementById("edit-original-title").value.trim();
    if (newTitle && newTitle !== original) {
      const refresh = confirm(`제목이 변경되었습니다.\n"${newTitle}"으로 작품 링크를 새로 검색할까요?`);
      document.getElementById("edit-refresh-link").value = refresh ? "true" : "false";
    }
  }, { once: true });

  document.getElementById("edit-overlay").style.display = "flex";
  document.getElementById("edit-form-title").focus();
}

// ===== TMDb 업데이트 (기존 항목) =====
async function tmdbUpdateItem() {
  if (!_currentEditId) return;
  const btn = document.getElementById("edit-btn-tmdb-update");
  const resultEl = document.getElementById("edit-tmdb-update-result");

  btn.disabled = true;
  btn.textContent = "검색 중...";
  resultEl.style.display = "none";

  try {
    const url = TMDB_UPDATE_URL.replace("__ID__", _currentEditId);
    const resp = await fetch(url, { method: "POST" });
    const data = await resp.json();

    if (data.ok) {
      if (data.titleLink) document.getElementById("edit-form-titleLink").value = data.titleLink;
      if (data.officialRating) document.getElementById("edit-form-officialRating").value = data.officialRating;
      if (data.originalTitle) document.getElementById("edit-form-originalTitle").value = data.originalTitle;
      resultEl.textContent = `✓ 업데이트 완료: 링크${data.titleLink ? " ✓" : " -"} / 공식평점 ${data.officialRating || "-"}`;
      resultEl.style.color = "#166534";
    } else {
      resultEl.textContent = `✗ ${data.error || "TMDb에서 찾지 못했습니다."}`;
      resultEl.style.color = "#dc2626";
    }
    resultEl.style.display = "block";
  } catch {
    resultEl.textContent = "✗ 네트워크 오류";
    resultEl.style.color = "#dc2626";
    resultEl.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "↺ TMDb로 링크·공식평점 업데이트";
  }
}

// ===== 폼 초기화 =====
function resetForm() {
  _currentEditId = null;
  document.getElementById("reg-form-title").value = "";
  document.getElementById("reg-form-category").value = "";
  document.getElementById("reg-form-genre").value = "";
  document.getElementById("reg-form-officialRating").value = "";
  document.getElementById("reg-form-originalTitle").value = "";
  document.getElementById("reg-form-titleLink").value = "";
  document.getElementById("reg-form-review").value = "";
  document.getElementById("reg-form-synopsis").value = "";
  document.getElementById("reg-form-rating").value = "0";
  document.getElementById("reg-rating-display").textContent = "0";
  document.getElementById("reg-tmdb-preview").style.display = "none";
  // 등록 모달에서는 TMDb 업데이트 버튼 숨김
  const updateBtn = document.getElementById("reg-btn-tmdb-update");
  if (updateBtn) updateBtn.style.display = "none";
  setWatched(false, "reg");
}

// ===== 관람 여부 설정 =====
function setWatched(watched, ns) {
  document.getElementById(ns + "-form-watched").value = watched ? "true" : "false";
  document.getElementById(ns + "-btn-want").classList.toggle("active", !watched);
  document.getElementById(ns + "-btn-watched").classList.toggle("active", watched);
  document.getElementById(ns + "-watched-at-group").style.display = watched ? "block" : "none";
}

// ===== 필터 설정 =====
function setFilter(name, value) {
  if (name === "category") {
    document.getElementById("category-input").value = value;
    document.querySelectorAll("#category-chips .chip").forEach(btn => {
      btn.classList.toggle("active", btn.textContent.trim() === value);
    });
  } else if (name === "watched") {
    document.getElementById("watched-input").value = value;
  }
  sessionStorage.setItem("focusSearch", "1");
  document.getElementById("filter-form").submit();
}

// ===== TMDb 미리보기 =====
async function previewTmdb(ns) {
  const title = document.getElementById(ns + "-form-title").value.trim();
  const category = document.getElementById(ns + "-form-category").value;
  if (!title) { alert("제목을 먼저 입력해주세요."); return; }

  const preview = document.getElementById(ns + "-tmdb-preview");
  preview.style.display = "block";
  preview.textContent = "검색 중...";

  try {
    const resp = await fetch(`/item/tmdb-search?title=${encodeURIComponent(title)}&category=${encodeURIComponent(category)}`);
    const data = await resp.json();
    if (data.titleLink) {
      document.getElementById(ns + "-form-titleLink").value = data.titleLink;
      if (data.officialRating && !document.getElementById(ns + "-form-officialRating").value) {
        document.getElementById(ns + "-form-officialRating").value = data.officialRating;
      }
      preview.textContent = `✓ 링크 찾음: ${data.titleLink}${data.officialRating ? ` | 공식 평점: ${data.officialRating}` : ""}`;
    } else {
      preview.textContent = "TMDb에서 작품을 찾지 못했습니다.";
    }
  } catch {
    preview.textContent = "검색 실패. TMDb API 키를 확인해주세요.";
  }
}

// ===== 로딩 표시 =====
function showLoading(show) {
  document.getElementById("loading-overlay").style.display = show ? "flex" : "none";
}

// ===== 검색 자동 실행 (디바운스) =====
let searchTimer = null;
const searchInput = document.getElementById("search-input");
if (searchInput) {
  // 페이지 로드 시 포커스 복귀 (검색/필터 후)
  const shouldFocus = sessionStorage.getItem("focusSearch");
  const hasQuery = searchInput.value.trim() !== "";
  if (shouldFocus || hasQuery) {
    sessionStorage.removeItem("focusSearch");
    requestAnimationFrame(() => {
      searchInput.focus();
      // 커서를 텍스트 끝으로
      const len = searchInput.value.length;
      searchInput.setSelectionRange(len, len);
    });
  }

  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      sessionStorage.setItem("focusSearch", "1");
      document.getElementById("filter-form").submit();
    }, 400);
  });
}

// ===== 폼 제출 시 로딩 표시 =====
document.querySelectorAll("form[method=post]").forEach(form => {
  form.addEventListener("submit", () => showLoading(true));
});

// ===== TMDb 상태 아이콘 폴링 =====
const TMDB_STATUS_ICONS = {
  pending:    { icon: "⏳", title: "TMDb 검색 대기 중" },
  searching:  { icon: "🔍", title: "TMDb 검색 중..." },
  done:       { icon: "", title: "" },          // 완료 시 아이콘 제거
  not_found:  { icon: "✕", title: "TMDb 정보 없음" },
};

function updateTmdbStatusIcons(statuses) {
  for (const [id, status] of Object.entries(statuses)) {
    const el = document.getElementById("tmdb-status-" + id);
    if (!el) continue;
    const info = TMDB_STATUS_ICONS[status];
    if (!info) continue;
    if (info.icon) {
      el.textContent = info.icon;
      el.title = info.title;
      el.style.display = "inline";
    } else {
      el.style.display = "none";
    }
  }
}

(function startTmdbPolling() {
  if (typeof TMDB_PENDING_IDS === "undefined" || !TMDB_PENDING_IDS.length) return;

  // 초기 상태를 ⏳로 표시
  TMDB_PENDING_IDS.forEach(id => {
    const el = document.getElementById("tmdb-status-" + id);
    if (el) { el.textContent = "⏳"; el.title = "TMDb 검색 대기 중"; el.style.display = "inline"; }
  });

  let pending = [...TMDB_PENDING_IDS];
  let done = 0;
  const total = pending.length;

  const banner = document.getElementById("import-success-banner");

  async function poll() {
    if (!pending.length) return;
    try {
      const resp = await fetch(TMDB_STATUS_URL + "?ids=" + pending.join(","));
      const statuses = await resp.json();
      updateTmdbStatusIcons(statuses);

      // 완료/실패 항목을 pending에서 제거
      pending = pending.filter(id => {
        const s = statuses[id];
        if (s === "done" || s === "not_found") { done++; return false; }
        return true;
      });

      // 진행률 배너 업데이트
      if (banner && total > 1) {
        const pct = Math.round((done / total) * 100);
        banner.textContent = `TMDb 검색 중... ${pct}% (${done}/${total})`;
        if (!pending.length) banner.textContent = `TMDb 검색 완료 (${done}/${total})`;
      }

      if (pending.length) setTimeout(poll, 2000);
    } catch {
      // 폴링 오류 시 조용히 중단
    }
  }

  setTimeout(poll, 1500);
})();
