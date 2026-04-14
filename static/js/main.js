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
  document.getElementById("form-title").focus();
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
  document.getElementById("form-title").value = item.title || "";
  document.getElementById("form-category").value = item.category || "";
  document.getElementById("form-genre").value = item.genre || "";
  document.getElementById("form-officialRating").value = item.officialRating || "";
  document.getElementById("form-titleLink").value = item.titleLink || "";
  document.getElementById("form-review").value = item.review || "";
  document.getElementById("form-synopsis").value = item.synopsis || "";
  document.getElementById("edit-original-title").value = item.title || "";

  const rating = parseFloat(item.rating) || 0;
  document.getElementById("form-rating").value = rating;
  document.getElementById("rating-display").textContent = rating;

  const watched = (item.watched || "").toLowerCase() === "true";
  setWatched(watched);

  if (item.watchedAt) {
    document.getElementById("form-watchedAt").value = item.watchedAt.slice(0, 10);
  }

  // "업데이트 by TMDb" 버튼 노출
  document.getElementById("btn-tmdb-update").style.display = "block";
  document.getElementById("tmdb-update-result").style.display = "none";
  document.getElementById("tmdb-update-result").textContent = "";

  // title 변경 감지 → 링크 재검색 여부 물어보기
  document.getElementById("form-title").addEventListener("change", function () {
    const newTitle = this.value.trim();
    const original = document.getElementById("edit-original-title").value.trim();
    if (newTitle && newTitle !== original) {
      const refresh = confirm(`제목이 변경되었습니다.\n"${newTitle}"으로 작품 링크를 새로 검색할까요?`);
      document.getElementById("edit-refresh-link").value = refresh ? "true" : "false";
    }
  }, { once: true });

  document.getElementById("edit-overlay").style.display = "flex";
  document.getElementById("form-title").focus();
}

// ===== TMDb 업데이트 (기존 항목) =====
async function tmdbUpdateItem() {
  if (!_currentEditId) return;
  const btn = document.getElementById("btn-tmdb-update");
  const resultEl = document.getElementById("tmdb-update-result");

  btn.disabled = true;
  btn.textContent = "검색 중...";
  resultEl.style.display = "none";

  try {
    const url = TMDB_UPDATE_URL.replace("__ID__", _currentEditId);
    const resp = await fetch(url, { method: "POST" });
    const data = await resp.json();

    if (data.ok) {
      if (data.titleLink) document.getElementById("form-titleLink").value = data.titleLink;
      if (data.officialRating) document.getElementById("form-officialRating").value = data.officialRating;
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
  document.getElementById("form-title").value = "";
  document.getElementById("form-category").value = "";
  document.getElementById("form-genre").value = "";
  document.getElementById("form-officialRating").value = "";
  document.getElementById("form-titleLink").value = "";
  document.getElementById("form-review").value = "";
  document.getElementById("form-synopsis").value = "";
  document.getElementById("form-rating").value = "0";
  document.getElementById("rating-display").textContent = "0";
  document.getElementById("tmdb-preview").style.display = "none";
  // 등록 모달에서는 TMDb 업데이트 버튼 숨김
  const updateBtn = document.getElementById("btn-tmdb-update");
  if (updateBtn) updateBtn.style.display = "none";
  setWatched(false);
}

// ===== 관람 여부 설정 =====
function setWatched(watched) {
  document.getElementById("form-watched").value = watched ? "true" : "false";
  document.getElementById("btn-want").classList.toggle("active", !watched);
  document.getElementById("btn-watched").classList.toggle("active", watched);
  document.getElementById("watched-at-group").style.display = watched ? "block" : "none";
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
  document.getElementById("filter-form").submit();
}

// ===== TMDb 미리보기 =====
async function previewTmdb() {
  const title = document.getElementById("form-title").value.trim();
  const category = document.getElementById("form-category").value;
  if (!title) { alert("제목을 먼저 입력해주세요."); return; }

  const preview = document.getElementById("tmdb-preview");
  preview.style.display = "block";
  preview.textContent = "검색 중...";

  try {
    const resp = await fetch(`/item/tmdb-search?title=${encodeURIComponent(title)}&category=${encodeURIComponent(category)}`);
    const data = await resp.json();
    if (data.titleLink) {
      document.getElementById("form-titleLink").value = data.titleLink;
      if (data.officialRating && !document.getElementById("form-officialRating").value) {
        document.getElementById("form-officialRating").value = data.officialRating;
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
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      document.getElementById("filter-form").submit();
    }, 400);
  });
}

// ===== 폼 제출 시 로딩 표시 =====
document.querySelectorAll("form[method=post]").forEach(form => {
  form.addEventListener("submit", () => showLoading(true));
});
