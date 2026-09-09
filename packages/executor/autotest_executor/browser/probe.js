// 页面探针。
//
// 存在的理由：很多系统接口失败仍返回 HTTP 200，错误藏在响应体的 errors 里，
// 不读 body 根本发现不了；页面看着完全正常，接口测试也测不到那个接口。
//
// 底层错误（console / JS / 请求体）不绑 UI 框架。
// 右上角失败弹出用常见通知层选择器采集（Ant / Element / role=alert），
// 只收失败、忽略「保存成功」。业务字段名不写死。
(() => {
  if (window.__atpProbe) return;

  const CONFIG = window.__atpProbeConfig || { errorUrlPatterns: [] };
  const MAX_ITEMS = 50;
  const TRUNCATE = 300;

  const store = {
    consoleErrors: [],
    jsErrors: [],
    requestErrors: [],
    uiErrors: [],
    installedAt: Date.now(),
  };

  const seenUi = new Set();

  const push = (bucket, item) => {
    if (bucket.length >= MAX_ITEMS) return;
    bucket.push(item);
  };

  const clip = (value) => {
    const text = typeof value === "string" ? value : String(value);
    return text.length > TRUNCATE ? text.slice(0, TRUNCATE) + "…" : text;
  };

  // 右上角失败弹出：常见通知层 + 失败文案。不绑某个业务字段。
  const TOAST_SEL = [
    ".ant-message-notice",
    ".ant-notification-notice",
    ".el-message",
    ".el-notification",
    "[role=alert]",
  ].join(",");

  const classBlob = (el) => {
    let s = String((el && el.className) || "");
    try {
      const kids = el.querySelectorAll ? el.querySelectorAll("[class]") : [];
      for (let i = 0; i < kids.length && i < 8; i++) s += " " + kids[i].className;
    } catch (_) {
      /* ignore */
    }
    return s;
  };

  const toastKind = (el) => {
    const cls = classBlob(el);
    if (/(message-error|notice-error|message--error|notification-error|alert-error|alert-danger|is-error|--error)/i.test(cls)) {
      return "error";
    }
    if (/(message-success|notice-success|message--success|alert-success)/i.test(cls)) return "success";
    if (/(message-warning|notice-warning|message--warning)/i.test(cls)) return "warning";
    const text = ((el && el.innerText) || "").replace(/\s+/g, " ").trim();
    if (/(失败|错误|异常|不能|无法|禁止|不允许)/.test(text)) return "error";
    if (/成功/.test(text)) return "success";
    return "info";
  };

  const inTopBand = (el) => {
    try {
      const rect = el.getBoundingClientRect();
      if (!rect || rect.width < 8 || rect.height < 8) return false;
      return rect.top >= -8 && rect.top < 280 && rect.bottom > 0;
    } catch (_) {
      return false;
    }
  };

  const captureToast = (el) => {
    if (!el || el.nodeType !== 1) return;
    let node = el;
    if (node.matches && !node.matches(TOAST_SEL) && node.querySelector) {
      node = node.querySelector(TOAST_SEL) || node;
    }
    if (!inTopBand(node)) return;
    if (toastKind(node) !== "error") return;
    const message = clip(((node.innerText || "") + "").replace(/\s+/g, " ").trim());
    if (!message || message.length < 2) return;
    if (seenUi.has(message)) return;
    seenUi.add(message);
    push(store.uiErrors, { message, kind: "toast", at: Date.now() });
  };

  const scrapeVisibleToasts = () => {
    try {
      document.querySelectorAll(TOAST_SEL).forEach(captureToast);
    } catch (_) {
      /* 探针自身不能影响页面 */
    }
  };

  const watchToasts = () => {
    try {
      const mo = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
          for (const node of mutation.addedNodes) {
            if (node.nodeType !== 1) continue;
            captureToast(node);
            try {
              if (node.querySelectorAll) node.querySelectorAll(TOAST_SEL).forEach(captureToast);
            } catch (_) {
              /* ignore */
            }
          }
        }
      });
      mo.observe(document.documentElement || document.body, { childList: true, subtree: true });
    } catch (_) {
      /* ignore */
    }
  };

  if (document.documentElement) watchToasts();
  else document.addEventListener("DOMContentLoaded", watchToasts);

  // 1) 控制台错误
  const originalConsoleError = console.error.bind(console);
  console.error = (...args) => {
    try {
      push(store.consoleErrors, {
        message: clip(args.map((a) => (a && a.message) || a).join(" ")),
        at: Date.now(),
      });
    } catch (_) {
      /* 探针自身不能影响页面 */
    }
    return originalConsoleError(...args);
  };

  // 2) 未捕获的运行时错误。用 addEventListener 而非赋值 window.onerror，
  //    避免覆盖页面自己的处理器。
  window.addEventListener("error", (event) => {
    push(store.jsErrors, {
      kind: "error",
      message: clip((event && (event.message || event.error)) || "unknown error"),
      at: Date.now(),
    });
  });

  // 3) 未处理的 Promise 拒绝
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event && event.reason;
    push(store.jsErrors, {
      kind: "unhandledrejection",
      message: clip((reason && (reason.message || reason)) || "unknown rejection"),
      at: Date.now(),
    });
  });

  // 4) 请求级失败：状态码正常但内容表示失败
  const shouldInspect = (url) => {
    const patterns = CONFIG.errorUrlPatterns || [];
    if (!patterns.length) return true; // 不限定后端框架
    return patterns.some((p) => url.indexOf(p) !== -1);
  };

  const inspectBody = (url, status, text, contentType) => {
    const expectsJson = (contentType || "").indexOf("json") !== -1;
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch (_) {
      // 期望 JSON 却拿到别的东西：通常是被中间层返回了 HTML 错误页
      if (expectsJson || /^\s*</.test(text || "")) {
        push(store.requestErrors, {
          url,
          status,
          kind: "non_json",
          message: clip(text || ""),
          at: Date.now(),
        });
      }
      return;
    }
    if (parsed && parsed.errors && (!Array.isArray(parsed.errors) || parsed.errors.length)) {
      push(store.requestErrors, {
        url,
        status,
        kind: "body_errors",
        message: clip(JSON.stringify(parsed.errors)),
        at: Date.now(),
      });
    }
  };

  const originalFetch = window.fetch;
  if (typeof originalFetch === "function") {
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      try {
        const url = (response && response.url) || String(args[0]);
        if (shouldInspect(url)) {
          const clone = response.clone();
          const contentType = clone.headers && clone.headers.get("content-type");
          clone
            .text()
            .then((text) => inspectBody(url, response.status, text, contentType))
            .catch(() => {});
        }
      } catch (_) {
        /* 读不到 body 就放过，不能影响页面逻辑 */
      }
      return response;
    };
  }

  window.__atpProbe = {
    read: () => {
      scrapeVisibleToasts();
      return {
        consoleErrors: store.consoleErrors.slice(),
        jsErrors: store.jsErrors.slice(),
        requestErrors: store.requestErrors.slice(),
        uiErrors: store.uiErrors.slice(),
        installedAt: store.installedAt,
      };
    },
    consumeUiErrors: () => {
      scrapeVisibleToasts();
      const items = store.uiErrors.slice();
      store.uiErrors.length = 0;
      seenUi.clear();
      return items;
    },
    reset: () => {
      store.consoleErrors.length = 0;
      store.jsErrors.length = 0;
      store.requestErrors.length = 0;
      store.uiErrors.length = 0;
      seenUi.clear();
    },
  };
})();
