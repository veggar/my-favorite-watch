// ===== 앱 스타일 확인 모달 (P2-3) =====
//
// 네이티브 confirm() 은 스타일을 맞출 수 없고, 모바일 브라우저에서 위치·문구가
// 제각각이며 스크린리더 대응도 브라우저에 종속된다. 이 스크립트는 앱 모달로
// 대체한다.
//
// 사용법 (선언형):
//   <form method="post" action="..."
//         data-confirm="정말 삭제하시겠습니까?"
//         data-confirm-title="작품 삭제"
//         data-confirm-label="삭제"
//         data-confirm-variant="danger">
//
// 사용법 (명령형):
//   appConfirm({ title, message, confirmLabel, variant }).then(ok => ...)
//
// 주의: submit 이벤트를 document 의 **캡처 단계**에서 가로챈다. 그래야 form 에
// 직접 걸린 리스너(main.js 의 로딩 오버레이 표시, 인라인 onsubmit)가 취소 시
// 실행되지 않는다. 확인을 받으면 form.requestSubmit() 으로 다시 제출하여 원래
// 리스너가 정상 동작하게 한다.

(function () {
  "use strict";

  var overlay = null;
  var lastFocused = null;
  var resolveCurrent = null;

  function build() {
    overlay = document.createElement("div");
    overlay.className = "modal-overlay confirm-overlay";
    overlay.id = "app-confirm-overlay";
    overlay.style.display = "none";
    overlay.innerHTML =
      '<div class="modal confirm-modal" role="alertdialog" aria-modal="true"' +
      ' aria-labelledby="app-confirm-title" aria-describedby="app-confirm-message">' +
      '  <div class="modal-header">' +
      '    <h2 id="app-confirm-title"></h2>' +
      '    <button type="button" class="modal-close" data-confirm-action="cancel" aria-label="닫기">✕</button>' +
      "  </div>" +
      '  <p class="confirm-message" id="app-confirm-message"></p>' +
      '  <div class="form-actions">' +
      '    <button type="button" class="btn btn-secondary" data-confirm-action="cancel">취소</button>' +
      '    <button type="button" class="btn btn-primary" data-confirm-action="ok"></button>' +
      "  </div>" +
      "</div>";

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close(false);
      var action = e.target.getAttribute && e.target.getAttribute("data-confirm-action");
      if (action === "cancel") close(false);
      if (action === "ok") close(true);
    });

    document.body.appendChild(overlay);
  }

  function onKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      close(false);
    }
  }

  function close(result) {
    if (!overlay || overlay.style.display === "none") return;
    overlay.style.display = "none";
    document.removeEventListener("keydown", onKeydown, true);
    if (lastFocused && lastFocused.focus) lastFocused.focus();
    lastFocused = null;
    var resolve = resolveCurrent;
    resolveCurrent = null;
    if (resolve) resolve(result);
  }

  function appConfirm(options) {
    options = options || {};
    if (!overlay) build();

    // 이미 열려 있으면 이전 요청은 취소로 처리한다.
    if (resolveCurrent) close(false);

    overlay.querySelector("#app-confirm-title").textContent = options.title || "확인";
    overlay.querySelector("#app-confirm-message").textContent = options.message || "";

    var okBtn = overlay.querySelector('[data-confirm-action="ok"]');
    okBtn.textContent = options.confirmLabel || "확인";
    okBtn.className = "btn " + (options.variant === "danger" ? "btn-danger" : "btn-primary");

    lastFocused = document.activeElement;
    overlay.style.display = "flex";
    document.addEventListener("keydown", onKeydown, true);
    okBtn.focus();

    return new Promise(function (resolve) {
      resolveCurrent = resolve;
    });
  }

  // ── 선언형 폼 가로채기 ──────────────────────────────────────────────
  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (!form || !form.hasAttribute || !form.hasAttribute("data-confirm")) return;
      if (form.dataset.confirmed === "1") {
        // 확인을 받은 뒤 다시 제출된 경우. 다음 제출을 위해 표시를 지운다.
        delete form.dataset.confirmed;
        return;
      }

      e.preventDefault();
      e.stopPropagation();

      appConfirm({
        title: form.getAttribute("data-confirm-title") || "확인",
        message: form.getAttribute("data-confirm"),
        confirmLabel: form.getAttribute("data-confirm-label") || "확인",
        variant: form.getAttribute("data-confirm-variant") || "primary",
      }).then(function (ok) {
        if (!ok) return;
        form.dataset.confirmed = "1";
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          // requestSubmit 미지원 브라우저 폴백. form.submit() 은 submit 이벤트를
          // 발생시키지 않으므로 로딩 표시를 직접 켠다.
          if (typeof window.showLoading === "function") window.showLoading(true);
          form.submit();
        }
      });
    },
    true // 캡처 단계
  );

  window.appConfirm = appConfirm;
})();
