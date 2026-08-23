/**
 * Google Picker 연동 (task-2026-08-004).
 *
 * 원칙
 *  - drive.file 단일 범위의 단기 access token 만 브라우저 메모리에서 사용한다.
 *  - 토큰은 DOM · localStorage · sessionStorage · 쿠키 · URL 에 저장하지 않고,
 *    Picker 완료 · 취소 · 오류 후 참조를 제거한다.
 *  - 서버 세션의 복합 범위 access/refresh token 은 이 파일에서 다루지 않는다.
 *  - GIS(Google Identity Services)와 Google API Loader 는 사용자가 Picker 를
 *    요청한 시점에만 공식 HTTPS URL 에서 지연 로드한다.
 *
 * 사용법
 *   MFWPicker.open(config, {
 *     onPicked: function (doc) {...},   // {id, name}
 *     onCancel: function () {...},
 *     onError:  function (message) {...}
 *   });
 *   config = { client_id, api_key, project_number, scope }
 */
(function (global) {
  'use strict';

  var GSI_SRC = 'https://accounts.google.com/gsi/client';
  var GAPI_SRC = 'https://apis.google.com/js/api.js';
  var SPREADSHEET_MIME = 'application/vnd.google-apps.spreadsheet';
  var LOAD_TIMEOUT_MS = 15000;

  var loadPromises = {};

  function loadScript(src) {
    if (loadPromises[src]) { return loadPromises[src]; }
    loadPromises[src] = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src="' + src + '"]');
      if (existing && existing.getAttribute('data-mfw-loaded') === '1') {
        resolve();
        return;
      }
      var s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.defer = true;
      var timer = setTimeout(function () {
        reject(new Error('script load timeout'));
      }, LOAD_TIMEOUT_MS);
      s.onload = function () {
        clearTimeout(timer);
        s.setAttribute('data-mfw-loaded', '1');
        resolve();
      };
      s.onerror = function () {
        clearTimeout(timer);
        delete loadPromises[src];
        reject(new Error('script load failed'));
      };
      document.head.appendChild(s);
    });
    return loadPromises[src];
  }

  function loadPickerApi() {
    return loadScript(GAPI_SRC).then(function () {
      return new Promise(function (resolve, reject) {
        if (global.google && global.google.picker) { resolve(); return; }
        if (!global.gapi) { reject(new Error('gapi unavailable')); return; }
        global.gapi.load('picker', {
          callback: resolve,
          onerror: function () { reject(new Error('picker module load failed')); },
          timeout: LOAD_TIMEOUT_MS,
          ontimeout: function () { reject(new Error('picker module load timeout')); }
        });
      });
    });
  }

  /**
   * drive.file 단기 토큰을 요청한다. 사용자 버튼 클릭 흐름에서만 호출한다.
   * 성공 시 access token 문자열을 resolve 한다.
   */
  function requestDriveFileToken(config) {
    return loadScript(GSI_SRC).then(function () {
      return new Promise(function (resolve, reject) {
        if (!(global.google && global.google.accounts && global.google.accounts.oauth2)) {
          reject(new Error('gis unavailable'));
          return;
        }
        var client;
        try {
          client = global.google.accounts.oauth2.initTokenClient({
            client_id: config.client_id,
            scope: config.scope,
            callback: function (resp) {
              if (resp && resp.access_token) { resolve(resp.access_token); }
              else { reject(new Error('token response empty')); }
            },
            error_callback: function (err) {
              // popup_closed / popup_failed_to_open(팝업 차단) / access_denied 등
              reject(new Error((err && err.type) || 'token request failed'));
            }
          });
        } catch (e) {
          reject(e);
          return;
        }
        client.requestAccessToken();
      });
    });
  }

  function buildAndShowPicker(config, token, handlers) {
    var view = new global.google.picker.DocsView(global.google.picker.ViewId.SPREADSHEETS)
      .setMimeTypes(SPREADSHEET_MIME);
    var picker = new global.google.picker.PickerBuilder()
      .setAppId(config.project_number)
      .setDeveloperKey(config.api_key)
      .setOAuthToken(token)
      .addView(view)
      .setSelectableMimeTypes(SPREADSHEET_MIME)
      .setOrigin(global.location.protocol + '//' + global.location.host)
      .setCallback(function (data) {
        var action = data && data[global.google.picker.Response.ACTION];
        if (action === global.google.picker.Action.PICKED) {
          var doc = (data[global.google.picker.Response.DOCUMENTS] || [])[0] || {};
          handlers.done();
          handlers.onPicked({
            id: doc[global.google.picker.Document.ID] || '',
            name: doc[global.google.picker.Document.NAME] || ''
          });
        } else if (action === global.google.picker.Action.CANCEL) {
          handlers.done();
          handlers.onCancel();
        }
        // 그 외 중간 이벤트(loaded 등)는 무시한다.
      })
      .build();
    picker.setVisible(true);
    return picker;
  }

  var MFWPicker = {
    /**
     * Picker 를 연다. 실패 유형과 무관하게 onError(사용자용 메시지)로 수렴한다.
     */
    open: function (config, callbacks) {
      var onPicked = callbacks.onPicked || function () {};
      var onCancel = callbacks.onCancel || function () {};
      var onError = callbacks.onError || function () {};

      if (!config || !config.client_id || !config.api_key || !config.project_number) {
        onError('Google Drive 선택 기능이 설정되지 않았습니다. URL 직접 연결을 이용해주세요.');
        return;
      }

      var token = null; // 이 스코프 안에서만 유지되는 drive.file 단기 토큰

      Promise.all([requestDriveFileToken(config), loadPickerApi()])
        .then(function (results) {
          token = results[0];
          var handlers = {
            onPicked: onPicked,
            onCancel: onCancel,
            done: function () { token = null; } // 완료·취소 후 토큰 참조 제거
          };
          buildAndShowPicker(config, token, handlers);
        })
        .catch(function (err) {
          token = null;
          var type = (err && err.message) || '';
          var msg;
          if (type.indexOf('popup_failed_to_open') !== -1) {
            msg = '팝업이 차단되어 있습니다. 팝업 허용 후 다시 시도하거나 URL 직접 연결을 이용해주세요.';
          } else if (type.indexOf('popup_closed') !== -1 || type.indexOf('access_denied') !== -1 ||
                     type.indexOf('user_logged_out') !== -1) {
            msg = 'Google Drive 접근이 승인되지 않았습니다. 다시 시도하거나 URL 직접 연결을 이용해주세요.';
          } else if (type.indexOf('load') !== -1 || type.indexOf('unavailable') !== -1) {
            msg = 'Google 스크립트를 불러오지 못했습니다. 네트워크 확인 후 다시 시도하거나 URL 직접 연결을 이용해주세요.';
          } else {
            msg = 'Google Drive 선택 중 문제가 발생했습니다. 다시 시도하거나 URL 직접 연결을 이용해주세요.';
          }
          onError(msg);
        });
    }
  };

  global.MFWPicker = MFWPicker;
})(window);
