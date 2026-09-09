// 录制器。
//
// 通过 add_init_script 注入，所以整页导航后会自动重装——这点很重要，
// 页面一跳转 window 上的东西就没了，靠页面内缓冲必然丢事件。
// 事件不在页面里攒，而是通过 exposeBinding 直接推给 Python，一条都不留在页面上。
(() => {
  if (window.__atpRecorder) return;

  const BADGE_ID = '__atp_recorder_badge';
  const INPUT_SETTLE_MS = 600;

  const inBadge = (el) => !!(el && el.closest && el.closest('#' + BADGE_ID));

  const emit = (payload) => {
    if (!window.__atpEmit) return;
    try {
      window.__atpEmit({ ...payload, ts: Date.now(), url: location.href });
    } catch (_) {
      // 录制器自身不能影响被测页面
    }
  };

  const describe = (el) => (window.__atpDescribe ? window.__atpDescribe(el) : null);
  const contextOf = (el) => (window.__atpContext ? window.__atpContext(el) : {});
  const comboHost = (el) => (window.__atpComboHost ? window.__atpComboHost(el) : null);
  const selectedChoice = (el) => (window.__atpSelectedChoice ? window.__atpSelectedChoice(el) : '');
  const fieldSelectHost = (el) => (window.__atpFieldSelectHost ? window.__atpFieldSelectHost(el) : null);
  const isComboSearch = (el) => !!(window.__atpIsComboSearch && window.__atpIsComboSearch(el));
  const inDropdown = (el) => !!(window.__atpInDropdown && window.__atpInDropdown(el));
  const optionTitle = (el) => (window.__atpOptionTitle ? window.__atpOptionTitle(el) : '');
  const selectOption = (el) => (window.__atpSelectOption ? window.__atpSelectOption(el) : null);
  const selectTag = (el) => (window.__atpSelectTag ? window.__atpSelectTag(el) : null);
  const selectTab = (el) => (window.__atpSelectTab ? window.__atpSelectTab(el) : null);
  const pickDate = (el) => (window.__atpPickDate ? window.__atpPickDate(el) : null);
  const pickerHost = (el) => (window.__atpPickerHost ? window.__atpPickerHost(el) : null);
  const eventEl = (e) => (window.__atpDeepNode ? window.__atpDeepNode(e) : e.target);
  let lastPickerHost = null;
  let lastPickerHostTs = 0;

  // ---------------------------------------------------------------- 输入合并
  // 每敲一个字符一个 input 事件。不合并的话，填「款式A」会录成三步。
  let pending = null;
  let pendingTimer = null;

  const flushInput = () => {
    if (pendingTimer) { clearTimeout(pendingTimer); pendingTimer = null; }
    if (!pending) return;
    const { el, target, context } = pending;
    pending = null;
    emit({ type: 'fill', target, context, value: el.value });
  };

  const noteInput = (el) => {
    // 下拉的搜索框不是输入框：敲的是过滤关键字，真正选中的是选项
    if (isComboSearch(el) || comboHost(el)) return;
    if (el && el.type === 'file') return;
    if (pending && pending.el !== el) flushInput();
    if (!pending) pending = { el, target: describe(el), context: contextOf(el) };
    if (pendingTimer) clearTimeout(pendingTimer);
    pendingTimer = setTimeout(flushInput, INPUT_SETTLE_MS);
  };

  let lastChooseKey = '';
  let lastChooseTs = 0;
  let lastComboTrigger = null;
  let lastComboInfo = { widget: null, panel: null, trigger_css: null };
  let lastClickKey = '';
  let lastClickTs = 0;
  let lastEarlyDownKey = '';
  let lastEarlyDownTs = 0;
  let lastClosingDownTs = 0;
  const ACTION_SEL = 'button, [role=button], [role=menuitem], .oio-action-item, [data-action-name], .ant-btn, .el-button';
  const ACTION_TEXT = /^(保存|提交|确定|确认|取消|Save|OK|Submit)$/i;
  const OVERLAY_SEL = [
    '[role=dialog]',
    'dialog[open]',
    '.oio-modal-wrapper',
    '.ant-modal-wrap',
    '.ant-modal-content',
    '.ant-modal',
    '.ant-modal-root',
    '.default-dialog',
    '.ant-drawer-content',
    '.el-dialog',
    '.el-dialog__wrapper',
    '.el-overlay',
    '.el-overlay-dialog',
    '.oio-modal',
    '.oio-dialog',
  ].join(',');
  const TABLE_SEL = '.el-table, .ant-table, table, [class*="el-table"], [class*="table-body"]';
  const TABLE_ACTION_TEXT = /^(带回|选择|确定|查看|编辑|删除|详情)$/i;

  const clickKeyOf = (el) => {
    if (!el) return '';
    const text = (el.innerText || '').trim().slice(0, 40);
    return `${el.tagName || ''}|${text}`;
  };

  const inOverlay = (el) => !!(el && el.closest && el.closest(OVERLAY_SEL));

  const tableActionText = (node) => ((node && node.innerText) || '').trim().split('\n')[0].trim();

  // Oinone 款式 lookup：td.el-table__cell 内 button.el-button.is-link（带回）
  const lookupTableActionEl = (el) => {
    if (!el || !el.closest) return null;
    const cell = el.closest('td.el-table__cell, .el-table__cell');
    let btn = el.closest('button.el-button, button, a, .ant-btn, .ant-btn-link');
    if (cell) {
      if (!btn || !cell.contains(btn)) {
        btn = cell.querySelector('button.el-button, button, a, .ant-btn');
      }
    }
    if (!btn) {
      btn = el.closest(
        'td.el-table__cell button, .el-table .el-button, .el-table button, .ant-table button, table button'
      );
    }
    if (!btn) return null;
    const inTable = btn.closest('td.el-table__cell, .el-table__cell, .el-table, .ant-table, table, .el-table__body');
    if (!inTable) return null;
    const text = tableActionText(btn);
    if (!text || text.length > 12 || !TABLE_ACTION_TEXT.test(text)) return null;
    return btn;
  };

  const overlayActionEl = (el) => {
    const lookup = lookupTableActionEl(el);
    if (lookup) return lookup;
    if (!el || !el.closest) return null;
    const overlay = el.closest(OVERLAY_SEL);
    if (!overlay) return null;
    let node = el;
    for (let depth = 0; node && node !== overlay && depth < 8; depth++) {
      if (!node.tagName) {
        node = node.parentElement;
        continue;
      }
      const text = tableActionText(node);
      if (text && text.length <= 12 && TABLE_ACTION_TEXT.test(text)) {
        const host = node.closest('button, .el-button, a, .ant-btn, .ant-btn-link') || node;
        return host;
      }
      const inTable = node.closest && node.closest(TABLE_SEL);
      if (inTable) {
        const link = node.closest('a, .ant-btn-link, .el-button, button, [role=button]') || node;
        const linkText = tableActionText(link);
        if (
          linkText && linkText.length <= 12 && TABLE_ACTION_TEXT.test(linkText)
          && (link.tagName === 'A' || link.tagName === 'BUTTON' || link.closest('.ant-btn-link, .el-button'))
        ) {
          return link;
        }
      }
      node = node.parentElement;
    }
    return null;
  };

  const isClosingAction = (el) => {
    if (!el) return false;
    const text = ((el.innerText || '').trim().split('\n')[0] || '');
    return ACTION_TEXT.test(text);
  };

  // 只提前录两类：lookup「带回」、保存/确定（会关弹窗）。
  // 不要把所有 button（如新增PO）都拦到 mousedown，否则会和后续 click 互相干扰。
  const resolveCaptureEl = (el) => {
    const lookup = lookupTableActionEl(el);
    if (lookup) return lookup;
    if (isClosingAction(el)) return el.closest(ACTION_SEL) || el;
    return null;
  };

  const fromBadge = (e) => {
    if (inBadge(e && e.target)) return true;
    const path = e && e.composedPath ? e.composedPath() : [];
    return path.some((n) => n && (n.id === BADGE_ID || (n.closest && n.closest('#' + BADGE_ID))));
  };

  const isActionControl = (el) => {
    if (!el || !el.closest) return false;
    if (el.closest(ACTION_SEL)) return true;
    const text = ((el.innerText || '').trim().split('\n')[0] || '');
    return ACTION_TEXT.test(text);
  };

  const emitPlainClick = (el) => {
    const text = (el.innerText || '').trim().slice(0, 40);
    const key = (el.tagName || '') + '|' + text;
    const now = Date.now();
    if (key === lastClickKey && now - lastClickTs < 800) return false;
    lastClickKey = key;
    lastClickTs = now;
    const portal = inDropdown(el);
    const context = contextOf(el);
    const extra = portal
      ? {
          context,
          skipWidget: true,
          widget: lastComboInfo.widget,
          trigger_css: lastComboInfo.trigger_css,
        }
      : { context };
    const target = decorateTarget(el, describe(el), extra);
    if (!target) return false;
    if (portal) rememberCombo(target, context);
    emit({
      type: 'click',
      target,
      context: {
        ...context,
        widget: target.widget,
        panel: target.panel,
        trigger_css: target.trigger_css,
      },
      text: (target.candidates.find((c) => c.kind === 'text') || {}).value || text,
    });
    return true;
  };

  const comboTrigger = (host) => (
    window.__atpComboDescribeEl ? window.__atpComboDescribeEl(host) : host
  );
  const widgetOf = (el) => (window.__atpWidgetInfo ? window.__atpWidgetInfo(el) : null);
  const panelOf = (el) => (window.__atpPanelInfo ? window.__atpPanelInfo(el) : null);

  const decorateTarget = (el, target, extra) => {
    if (!target) return null;
    extra = extra || {};
    const inherit = extra.inheritCombo !== false;
    const info = extra.skipWidget ? null : widgetOf(el);
    const panel = panelOf(el);
    const ctx = extra.context || {};
    const widget = extra.widget
      || target.widget
      || (info && info.kind)
      || ctx.widget
      || (inherit ? lastComboInfo.widget : null)
      || null;
    const panelKey = extra.panel
      || target.panel
      || (panel ? `${panel.kind}:${panel.attach}` : null)
      || ctx.panel
      || (inherit ? lastComboInfo.panel : null)
      || null;
    const triggerCss = extra.trigger_css
      || target.trigger_css
      || (info && info.trigger_css)
      || ctx.trigger_css
      || (inherit ? lastComboInfo.trigger_css : null)
      || null;
    if (widget) target.widget = widget;
    if (panelKey) target.panel = panelKey;
    if (triggerCss) target.trigger_css = triggerCss;
    return target;
  };

  const rememberCombo = (target, context) => {
    lastComboInfo = {
      widget: (target && target.widget) || (context && context.widget) || lastComboInfo.widget,
      panel: (target && target.panel) || (context && context.panel) || lastComboInfo.panel,
      trigger_css: (target && target.trigger_css) || (context && context.trigger_css) || lastComboInfo.trigger_css,
    };
  };

  const emitComboOpen = (host) => {
    lastComboTrigger = host;
    const trigger = comboTrigger(host) || host;
    const context = contextOf(trigger);
    const info = widgetOf(trigger) || widgetOf(host);
    const target = decorateTarget(trigger, describe(trigger), {
      context,
      inheritCombo: false,
      widget: info && info.kind,
      trigger_css: info && info.trigger_css,
    });
    if (!target) return;
    rememberCombo(target, context);
    const field = (target.candidates || []).find((c) => c.kind === 'field');
    const name = ((context && context.label) || (info && info.name) || (field && field.value) || '').trim()
      || (target.candidates.find((c) => c.kind === 'text' && c.value && c.value !== '请选择') || {}).value
      || '下拉';
    const key = 'combo-open|' + (target.trigger_css || name);
    const now = Date.now();
    if (key === lastClickKey && now - lastClickTs < 800) return;
    lastClickKey = key;
    lastClickTs = now;
    flushInput();
    emit({ type: 'click', target, context: { ...context, ...lastComboInfo }, text: name });
  };

  const formKindOf = (context) => {
    const hay = [
      (context && context.dialog) || '',
      (context && context.scope && context.scope.name) || '',
    ].join(' ');
    if (/新建|新增/.test(hay)) return 'create';
    if (/编辑|修改|更新/.test(hay)) return 'edit';
    return null;
  };

  const emitChooseFromOption = (option) => {
    const title = optionTitle(option);
    if (!title) return false;
    const now = Date.now();
    const key = title;
    if (key === lastChooseKey && now - lastChooseTs < 800) return true;
    const host = (inDropdown(option) && lastComboTrigger) || comboHost(option) || lastComboTrigger || option;
    const context = contextOf(host);
    const target = decorateTarget(host, describe(host), { context });
    if (!target) return false;
    lastChooseKey = key;
    lastChooseTs = now;
    flushInput();
    rememberCombo(target, context);
    const trigger = lastComboTrigger || host;
    emit({
      type: 'choose',
      target,
      context: {
        ...context,
        widget: target.widget,
        trigger_css: target.trigger_css,
        panel: target.panel,
        form_kind: formKindOf(context),
      },
      value: title,
      text: title,
      already_selected: selectedChoice(trigger) || '',
      form_kind: formKindOf(context),
    });
    return true;
  };

  const resolvePickerHost = (el) => {
    const now = Date.now();
    if (lastPickerHost && now - lastPickerHostTs < 30_000) {
      const activeInput = lastPickerHost.querySelector('.ant-picker-input input, .el-date-editor input');
      if (activeInput && activeInput.getAttribute('aria-expanded') === 'true') {
        return lastPickerHost;
      }
    }
    return pickerHost(el) || lastPickerHost;
  };

  const emitDateFill = (dateHit, el) => {
    const host = resolvePickerHost(el);
    if (!host) return false;
    const trigger = (host.querySelector && host.querySelector('.ant-picker-input input, .el-date-editor input')) || host;
    const context = contextOf(host);
    const info = widgetOf(host) || {};
    const target = decorateTarget(host, describe(host) || describe(trigger), {
      context,
      inheritCombo: false,
      widget: info.kind,
      trigger_css: info.trigger_css,
    });
    if (!target) return false;
    const now = Date.now();
    const key = 'date|' + dateHit.date;
    if (key === lastChooseKey && now - lastChooseTs < 800) return true;
    lastChooseKey = key;
    lastChooseTs = now;
    flushInput();
    emit({
      type: 'fill',
      target,
      context: { ...context, widget: info.kind, trigger_css: info.trigger_css },
      value: dateHit.date,
      text: dateHit.date,
    });
    return true;
  };

  const emitPanelClick = (el, text) => {
    const title = (text || optionTitle(el) || '').trim();
    if (!title) return false;
    const now = Date.now();
    const key = 'panel|' + title;
    if (key === lastClickKey && now - lastClickTs < 800) return true;
    const context = contextOf(el);
    const target = decorateTarget(el, describe(el), {
      context,
      skipWidget: true,
      widget: lastComboInfo.widget,
      trigger_css: lastComboInfo.trigger_css,
    });
    if (!target) return false;
    lastClickKey = key;
    lastClickTs = now;
    flushInput();
    rememberCombo(target, context);
    emit({
      type: 'click',
      target,
      context: {
        ...context,
        widget: target.widget,
        panel: target.panel,
        trigger_css: target.trigger_css,
      },
      text: title,
    });
    return true;
  };

  // ---------------------------------------------------------------- 监听
  // 用 capture 阶段：框架常在冒泡阶段做事件代理并阻止传播，
  // 挂在冒泡上会漏掉一部分点击。
  const opts = { capture: true, passive: true };

  document.addEventListener('input', (e) => {
    const el = eventEl(e);
    if (inBadge(el) || !el || !('value' in el)) return;
    if (el.type === 'checkbox' || el.type === 'radio' || el.type === 'file') return;
    if (isComboSearch(el) || comboHost(el)) return;
    noteInput(el);
  }, opts);

  document.addEventListener('change', (e) => {
    const el = eventEl(e);
    if (inBadge(el) || !el) return;
    if (isComboSearch(el) || (comboHost(el) && el.tagName !== 'SELECT')) return;
    if (el.tagName === 'SELECT') {
      flushInput();
      emit({
        type: 'select', target: describe(el), context: contextOf(el),
        value: el.value,
        text: el.selectedOptions && el.selectedOptions[0] ? el.selectedOptions[0].text : null,
      });
    } else if (el.type === 'checkbox' || el.type === 'radio') {
      flushInput();
      emit({ type: 'click', target: describe(el), context: contextOf(el), checked: el.checked });
    } else if (el.type === 'file') {
      flushInput();
      const host = (el.closest && el.closest('[data-name]')) || el;
      const context = contextOf(host);
      const target = decorateTarget(host, describe(host) || describe(el), {
        context,
        inheritCombo: false,
      });
      if (!target) return;
      const picked = (el.files && el.files[0] && el.files[0].name) || 'image.png';
      emit({
        type: 'upload',
        target,
        context,
        value: 'fixtures/uploads/ScreenShot_2026-04-16_084203_890.png',
        text: picked,
      });
    }
  }, opts);

  const tryEarlyCapture = (e) => {
    if (fromBadge(e)) return;
    const el = eventEl(e);
    if (inBadge(el) || !el) return;
    const captureEl = resolveCaptureEl(el);
    if (!captureEl) return;
    const lookupAct = lookupTableActionEl(el);
    // lookup「带回」在 el-popper 里也要录；保存/确定仍跳过下拉内误触
    if (!lookupAct && (inDropdown(el) || comboHost(el) || fieldSelectHost(el))) return;
    if (emitPlainClick(captureEl)) {
      lastEarlyDownKey = clickKeyOf(captureEl);
      lastEarlyDownTs = Date.now();
      if (isClosingAction(captureEl)) lastClosingDownTs = Date.now();
    }
  };

  // capture：业务关弹窗前记下「带回 / 保存」（日期改动前「带回」靠普通 click，这里只补关层场景）
  document.addEventListener('mousedown', tryEarlyCapture, { capture: true, passive: true });

  document.addEventListener('mousedown', (e) => {
    if (fromBadge(e)) return;
    const el = eventEl(e);
    if (inBadge(el) || !el) return;
    if (selectTab(el)) return;
    const tag = selectTag(el);
    if (tag) {
      emitPanelClick(tag);
      return;
    }
    const option = selectOption(el);
    if (option) {
      emitChooseFromOption(option);
      return;
    }
  }, opts);

  document.addEventListener('click', (e) => {
    if (fromBadge(e)) return;
    let el = eventEl(e);
    if (inBadge(el) || !el) return;
    const lookupAct = lookupTableActionEl(el);
    if (lookupAct) {
      const lk = clickKeyOf(lookupAct);
      if (lk === lastEarlyDownKey && Date.now() - lastEarlyDownTs < 700) return;
      emitPlainClick(lookupAct);
      return;
    }
    // 仅保存/确定后拦穿透 click，不因「新增PO→带回」快慢丢弃任何 click
    if (lastClosingDownTs && Date.now() - lastClosingDownTs < 400 && !inOverlay(el)) return;
    // 输入框内的点击紧接着往往是输入，Python 侧会把这类点击去掉
    flushInput();
    if (el.tagName === 'CANVAS' || (el.closest && el.closest('canvas'))) {
      emit({ type: 'unsupported', reason: 'canvas 内的操作', context: contextOf(el) });
      return;
    }
    const tab = selectTab(el);
    if (tab) el = tab;
    const tag = selectTag(el);
    if (tag) {
      emitPanelClick(tag);
      return;
    }
    const option = selectOption(el);
    if (option) {
      emitChooseFromOption(option);
      return;
    }
    if (inDropdown(el) && isComboSearch(el)) return;
    const host = comboHost(el);
    if (host && !inDropdown(el)) {
      emitComboOpen(host);
      return;
    }
    const fieldHost = fieldSelectHost(el);
    if (fieldHost && !inDropdown(el)) {
      emitComboOpen(fieldHost);
      return;
    }
    const dateHit = pickDate(el);
    if (dateHit && emitDateFill(dateHit, el)) return;
    const pickerCtl = (el.closest && (
      el.closest('.ant-picker:not(.ant-picker-dropdown)')
      || el.closest('.el-date-editor:not(.el-picker-panel)')
    )) || null;
    if (pickerCtl && !inDropdown(el)) {
      lastPickerHost = pickerCtl;
      lastPickerHostTs = Date.now();
    }
    emitPlainClick(el);
  }, opts);

  document.addEventListener('keydown', (e) => {
    if (inBadge(e.target)) return;
    if (e.key === 'Enter') {
      flushInput();
      const active = document.querySelector(
        '.ant-select-item-option-active, .el-select-dropdown__item.selected, [role=option][aria-selected=true]'
      );
      if ((isComboSearch(e.target) || comboHost(e.target)) && active) {
        emitChooseFromOption(active);
        return;
      }
      emit({ type: 'press', key: 'Enter', target: describe(e.target), context: contextOf(e.target) });
    }
  }, opts);

  document.addEventListener('dragstart', (e) => {
    if (inBadge(e.target)) return;
    emit({ type: 'unsupported', reason: '拖拽操作', context: contextOf(e.target) });
  }, opts);

  let pendingScroll = null;
  let scrollTimer = null;
  const shouldSkipScroll = (el) => {
    if (!el) return true;
    if (inDropdown(el)) return true;
    const cls = String((el.className || '')).toLowerCase();
    if (/el-select-dropdown|select-options|select-body|ant-select-dropdown|el-scrollbar__wrap/.test(cls)) {
      return true;
    }
    return !!(el.closest && el.closest(
      '.el-select-dropdown, .ant-select-dropdown, .select-options, .select-body, .el-popper.el-select__popper'
    ));
  };

  const flushScroll = () => {
    if (scrollTimer) { clearTimeout(scrollTimer); scrollTimer = null; }
    if (!pendingScroll) return;
    const { el, top } = pendingScroll;
    pendingScroll = null;
    if (shouldSkipScroll(el)) return;
    const context = contextOf(el);
    const target = decorateTarget(el, describe(el), { context, inheritCombo: false });
    if (!target) return;
    emit({
      type: 'scroll',
      target,
      context: {
        ...context,
        widget: target.widget,
        panel: target.panel,
        trigger_css: target.trigger_css,
      },
      value: String(top),
    });
  };
  document.addEventListener('scroll', (e) => {
    const raw = e.target;
    if (!raw || inBadge(raw)) return;
    const node = (raw.nodeType === 1) ? raw : (document.scrollingElement || document.documentElement);
    const container = window.__atpScrollContainer ? window.__atpScrollContainer(node) : null;
    if (!container) return;
    pendingScroll = { el: container, top: container.scrollTop };
    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(flushScroll, 280);
  }, opts);

  // 失焦时立刻结算，别等 600ms
  document.addEventListener('blur', (e) => { if (!inBadge(e.target)) flushInput(); }, opts);
  window.addEventListener('beforeunload', flushInput);

  // ---------------------------------------------------------------- 悬浮条
  const mountBadge = () => {
    if (!document.body || document.getElementById(BADGE_ID)) return;
    const badge = document.createElement('div');
    badge.id = BADGE_ID;
    badge.setAttribute('style', [
      'position:fixed', 'top:12px', 'right:12px', 'z-index:2147483647',
      'background:#171a21', 'color:#e6e8ec', 'border:1px solid #4c8bf5',
      'border-radius:8px', 'padding:10px 14px', 'font:13px/1.5 system-ui,sans-serif',
      'box-shadow:0 4px 20px rgba(0,0,0,.5)', 'display:flex', 'align-items:center', 'gap:12px',
    ].join(';'));
    badge.innerHTML = `
      <span style="display:flex;align-items:center;gap:6px">
        <span style="width:8px;height:8px;border-radius:50%;background:#e05252;
                     animation:__atp_pulse 1s infinite"></span>
        正在录制 <b id="${BADGE_ID}_count">0</b> 步
      </span>
      <button id="${BADGE_ID}_stop" style="background:#4c8bf5;color:#fff;border:none;
              border-radius:5px;padding:5px 12px;font-weight:600;cursor:pointer">结束录制</button>`;
    const style = document.createElement('style');
    style.textContent = '@keyframes __atp_pulse{50%{opacity:.2}}';
    badge.appendChild(style);
    document.body.appendChild(badge);
    document.getElementById(BADGE_ID + '_stop').addEventListener('click', (e) => {
      e.stopPropagation();
      flushInput();
      flushScroll();
      badge.querySelector('span').textContent = '正在整理步骤…';
      emit({ type: 'stop' });
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountBadge);
  } else {
    mountBadge();
  }
  // 单页应用可能整块重绘 body，掉了就补回来
  setInterval(mountBadge, 1000);

  window.__atpLookupTableAction = lookupTableActionEl;
  window.__atpRecorder = {
    version: '2026-09-09-matrix-grid',
    setCount: (n) => {
      const node = document.getElementById(BADGE_ID + '_count');
      if (node) node.textContent = String(n);
    },
  };

  // ---------------------------------------------------------------- 观察者快照
  let lastSnapshotKey = '';
  let snapshotCooldown = 0;
  let lastOverlayCount = 0;
  let lastHref = location.href;
  let snapshotTimer = null;

  const maybeEmitSnapshot = (trigger) => {
    if (!window.__atpCollectObservation) return;
    const now = Date.now();
    if (now - snapshotCooldown < 450) return;
    const snap = window.__atpCollectObservation(trigger);
    if (!snap || !snap.fields || !snap.fields.length) return;
    const layer = snap.layer || {};
    const key = [
      snap.trigger,
      snap.url,
      layer.kind,
      layer.name || '',
      snap.fields.map((f) => f.label).join(','),
    ].join('|');
    if (key === lastSnapshotKey && trigger !== 'manual' && trigger !== 'record_end') return;
    lastSnapshotKey = key;
    snapshotCooldown = now;
    emit({ type: 'observe_snapshot', ...snap });
  };

  const scheduleSnapshot = (trigger) => {
    if (snapshotTimer) clearTimeout(snapshotTimer);
    snapshotTimer = setTimeout(() => maybeEmitSnapshot(trigger), 320);
  };

  const overlayCount = () => {
    return Array.from(document.querySelectorAll(OVERLAY_SEL)).filter((node) => {
      if (!node || !node.getBoundingClientRect) return false;
      const st = getComputedStyle(node);
      if (st.display === 'none' || st.visibility === 'hidden') return false;
      const box = node.getBoundingClientRect();
      return box.width >= 2 && box.height >= 2;
    }).length;
  };

  const watchObserver = () => {
    lastOverlayCount = overlayCount();
    scheduleSnapshot('navigation');
    setInterval(() => {
      if (location.href !== lastHref) {
        lastHref = location.href;
        scheduleSnapshot('navigation');
      }
    }, 600);
    const observer = new MutationObserver(() => {
      const count = overlayCount();
      if (count > lastOverlayCount) scheduleSnapshot('layer_open');
      else if (count < lastOverlayCount) scheduleSnapshot('layer_close');
      else scheduleSnapshot('form_visible');
      lastOverlayCount = count;
    });
    if (document.documentElement) {
      observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true });
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', watchObserver);
  } else {
    watchObserver();
  }
})();
