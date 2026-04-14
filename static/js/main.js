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
function openEditModal(id) {
  const item = ITEMS_DATA.find(it => it.id === id);
  if (!item) return;

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
    // ISO 문자열을 날짜 형식으로 변환
    document.getElementById("form-watchedAt").value = item.watchedAt.slice(0, 10);
  }

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

// ===== 폼 초기화 =====
function resetForm() {
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
