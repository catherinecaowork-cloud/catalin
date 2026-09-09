// 定位候选计算。踩点和录制共用这一份。
//
// 两处各写一份迟早会漂移：录制时算出来的定位和回放时找的对不上，
// 用例会以「偶发失败」的形式表现出来，极难查。
(() => {
  const ICON_TAGS = new Set(['SVG', 'PATH', 'USE', 'I']);
  const TESTID_ATTRS = ['data-testid', 'data-test-id', 'data-test'];
  const INNER_ATTRS = ['data-value', 'data-color', 'data-code', 'data-key', 'data-id', 'title', 'aria-label'];
  const ICON_TEXT = /^(pushpin|pin|menu|setting|settings|user|home|plus|search|bell|close|more|ellipsis|caret|arrow)$/i;
  const STD_OPTION_SEL = '.ant-select-item-option, .el-select-dropdown__item';
  const PORTAL_SEL = [
    '.ant-select-dropdown:not(.ant-select-dropdown-hidden)',
    '.ant-dropdown:not(.ant-dropdown-hidden)',
    '.ant-picker-dropdown',
    '.ant-cascader-dropdown',
    '.ant-cascader-menus',
    '.ant-mentions-dropdown',
    '.ant-popover:not(.ant-popover-hidden)',
    '.el-select-dropdown',
    '.el-popper.el-select__popper',
    '.el-select__popper',
    '.el-color-dropdown',
    '.el-popper.is-pure.el-select__popper',
    '.el-popper:not(.is-pure)',
    '[class*="color-picker"]',
    '[class*="color-panel"]',
  ].join(',');
  const STD_DROPDOWN_SEL = [
    '.ant-select-dropdown',
    '.el-select-dropdown',
    '.el-popper.el-select__popper',
    '.el-select__popper',
  ].join(',');

  const classStr = (el) => (el && el.className && String(el.className)) || '';

  const isIcon = (el) => {
    if (!el || !el.tagName) return false;
    if (ICON_TAGS.has(el.tagName)) return true;
    return /icon|iconfont|oio-icon|anticon/i.test(classStr(el));
  };

  const parentOf = (node) => {
    if (!node) return null;
    if (node.parentElement) return node.parentElement;
    const root = node.getRootNode && node.getRootNode();
    if (root && root.host) return root.host;
    return null;
  };

  const closestOf = (el, selector) => {
    let node = el;
    for (let i = 0; node && i < 20; i++) {
      if (node.nodeType === 1 && node.matches && node.matches(selector)) return node;
      if (node.closest) {
        const hit = node.closest(selector);
        if (hit) return hit;
      }
      node = parentOf(node);
    }
    return null;
  };

  const ACTION_HOST_SEL = [
    'button', '[role=button]', '[role=menuitem]',
    'li.ant-menu-item',
    '.oio-action-item', '[data-action-name]', '.ant-btn',
  ].join(',');

  const climbToActionable = (el) => {
    let node = el;
    const tabItem = node && closestOf(node, '.el-tabs__item');
    if (tabItem && closestOf(tabItem, STD_DROPDOWN_SEL)) return tabItem;
    // 只把标准 Ant/Element 选项抬到 option 节点。自定义色板/面板要留在内部 DOM。
    const stdOption = node && closestOf(node, STD_OPTION_SEL);
    if (stdOption) return stdOption;
    if (isIcon(node) || (node && ICON_TAGS.has(node.tagName))) {
      node = closestOf(node, [
        'a', ACTION_HOST_SEL,
        '.oio-action-content',
        '.ant-menu-submenu-title',
        '.el-select__wrapper', '.el-select',
        '.ant-select-selector', '.ant-select',
      ].join(',')) || parentOf(node) || node;
    } else if (node && !['INPUT', 'TEXTAREA', 'SELECT'].includes(node.tagName)) {
      // 点到按钮内部文字时抬到按钮本身，避免 cssPath 只剩 DialogWidget 弹窗壳
      const action = closestOf(node, ACTION_HOST_SEL);
      if (action) node = action;
    }
    return node;
  };

  const innerLocators = (el) => {
    const found = [];
    const seen = new Set();
    let node = el;
    for (let depth = 0; node && node.tagName && depth < 6; depth++) {
      for (const attr of INNER_ATTRS) {
        const raw = node.getAttribute && node.getAttribute(attr);
        const v = (raw || '').trim();
        if (!v || v.length > 60) continue;
        const key = attr + '=' + v;
        if (seen.has(key)) continue;
        seen.add(key);
        found.push({ kind: 'css', value: `[${attr}="${CSS.escape(v)}"]` });
        if (attr === 'title' || attr === 'aria-label' || attr === 'data-value') {
          found.push({ kind: 'text', value: v });
        }
      }
      if (closestOf(node, PORTAL_SEL) && depth >= 2) break;
      node = parentOf(node);
    }
    return found;
  };

  const visibleText = (el) => {
    if (!el) return '';
    const titled = el.querySelector && el.querySelector('.ant-menu-title-content, .oio-action-content, span:not(.oio-icon)');
    const raw = ((titled && titled.innerText) || el.innerText || '').trim().split('\n')[0].trim();
    if (!raw || raw.length > 30 || ICON_TEXT.test(raw)) return '';
    return raw;
  };

  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName;
    if (tag === 'BUTTON') return 'button';
    if (tag === 'A' && el.getAttribute('href')) return 'link';
    if (tag === 'SELECT') return 'combobox';
    if (tag === 'TEXTAREA') return 'textbox';
    if (tag === 'INPUT') {
      const map = {
        text: 'textbox', email: 'textbox', tel: 'textbox', search: 'searchbox',
        checkbox: 'checkbox', radio: 'radio', submit: 'button', button: 'button',
      };
      // 密码框没有 textbox 角色，故意不给
      return map[(el.type || '').toLowerCase()] || null;
    }
    return null;
  };

  const labelOf = (el) => {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return (lab.innerText || '').trim();
    }
    const wrapper = el.closest('label');
    if (wrapper) return (wrapper.innerText || '').trim();
    return null;
  };

  const isEphemeralId = (id) => {
    if (!id) return true;
    return /^(el-id-|rc_select_|rc-menu|form_item_\d)/i.test(id) || /^el-id-\d/.test(id);
  };
  const cssPath = (el) => {
    const parts = [];
    let node = el;
    for (let depth = 0; node && depth < 4; depth++) {
      if (node.id && !isEphemeralId(node.id)) {
        parts.unshift(`${node.tagName.toLowerCase()}#${CSS.escape(node.id)}`);
        break;
      }
      let part = node.tagName.toLowerCase();
      const cls = Array.from(node.classList || [])
        .filter((c) => c.length < 25 && !/[0-9a-f]{6,}/i.test(c) && !/iconfont|icon/i.test(c))
        .slice(0, 2);
      if (cls.length) part += '.' + cls.map((c) => CSS.escape(c)).join('.');
      parts.unshift(part);
      node = parentOf(node);
    }
    return parts.join(' > ');
  };

  // 返回一组候选，按稳定性排序由调用方（Python）负责
  window.__atpDescribe = (el, roleOverride) => {
    if (!el || !el.tagName) return null;
    const raw = el;
    el = climbToActionable(el);
    if (!el || !el.tagName) return null;
    if (ICON_TAGS.has(el.tagName)) return null;
    const candidates = [];
    const inPortal = !!closestOf(raw, PORTAL_SEL) || !!closestOf(el, PORTAL_SEL);
    const stdOption = closestOf(el, STD_OPTION_SEL) || closestOf(raw, STD_OPTION_SEL);

    const menuId = el.getAttribute('data-menu-id');
    if (menuId) candidates.push({ kind: 'css', value: `[data-menu-id="${CSS.escape(menuId)}"]` });

    // 浮层里点的是某一项，不能用外层表单字段当定位——那会点到触发器而不是内部色块。
    if (!inPortal) {
      const fieldHost = el.closest('[data-name]') || closestOf(el, '[data-name]');
      if (fieldHost) {
        const dn = (fieldHost.getAttribute('data-name') || '').trim();
        if (dn) candidates.push({ kind: 'field', value: dn });
      }
    }
    const actionEl = el.closest('[data-action-name]') || closestOf(el, '[data-action-name]');
    if (actionEl) {
      const an = actionEl.getAttribute('data-action-name');
      if (an) candidates.push({ kind: 'css', value: `[data-action-name="${CSS.escape(an)}"]` });
    }

    for (const item of innerLocators(raw)) candidates.push(item);

    if (stdOption) {
      const title = (stdOption.getAttribute('title') || stdOption.getAttribute('aria-label') || visibleText(stdOption) || '').trim();
      if (title && title.length < 40) {
        candidates.push({ kind: 'css', value: `.ant-select-item-option[title="${CSS.escape(title)}"]` });
        candidates.push({ kind: 'text', value: title });
      }
    }

    for (const attr of TESTID_ATTRS) {
      const v = el.getAttribute(attr);
      if (v) candidates.push({ kind: 'testid', value: v });
    }

    const role = roleOverride === undefined ? roleOf(el) : roleOverride;
    const text = visibleText(el);
    if (role) {
      const accName = (el.getAttribute('aria-label') || text || el.value || '').trim();
      if (accName && !ICON_TEXT.test(accName)) {
        candidates.push({ kind: 'role', value: role, name: accName });
      } else {
        candidates.push({ kind: 'role', value: role, name: null });
      }
    }

    const label = labelOf(el);
    if (label && label.length < 40 && !ICON_TEXT.test(label)) candidates.push({ kind: 'label', value: label });
    if (el.placeholder && !/^(请输入|请选择|请填写|搜索)/.test(el.placeholder.trim()) && !/搜索|添加/.test(el.placeholder)) {
      candidates.push({ kind: 'placeholder', value: el.placeholder });
    }

    if (text) candidates.push({ kind: 'text', value: text });

    const tabId = el.matches && el.matches('.el-tabs__item') && el.id && !isEphemeralId(el.id);
    if (tabId) candidates.unshift({ kind: 'css', value: `#${CSS.escape(el.id)}` });
    else if (el.id && !isEphemeralId(el.id)) candidates.push({ kind: 'css', value: `#${CSS.escape(el.id)}` });
    const nameAttr = el.getAttribute('name');
    if (nameAttr) {
      candidates.push({ kind: 'css', value: `${el.tagName.toLowerCase()}[name="${nameAttr}"]` });
    }
    const path = cssPath(el);
    if (path && !/svg|iconfont|oio-icon|ant-select-item/i.test(path)) {
      candidates.push({ kind: 'css', value: path });
    }

    const widget = widgetInfoOf(raw);
    if (widget && widget.name && !inPortal) {
      if (!candidates.some((c) => c.kind === 'field' && c.value === widget.name)) {
        candidates.unshift({ kind: 'field', value: widget.name });
      }
      if (widget.trigger_css && !candidates.some((c) => c.value === widget.trigger_css)) {
        candidates.unshift({ kind: 'css', value: widget.trigger_css });
      }
    }

    if (!candidates.length) return null;
    const crawl = crawlDom(el);
    const panel = inPortal ? panelInfoOf(raw) : null;
    return {
      candidates,
      scope: crawl.scope,
      widget: widget ? widget.kind : null,
      panel: panel ? `${panel.kind}:${panel.attach}` : null,
      trigger_css: widget && widget.trigger_css ? widget.trigger_css : null,
    };
  };

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
    '.el-overlay-dialog',
    '.oio-modal',
    '.oio-dialog',
  ].join(',');

  const isShown = (node) => {
    if (!node || !node.getBoundingClientRect) return false;
    const st = getComputedStyle(node);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
    const box = node.getBoundingClientRect();
    return box.width >= 2 && box.height >= 2;
  };

  const overlayTitle = (root) => {
    if (!root) return '';
    const title = root.querySelector(
      '.ant-modal-title, .ant-drawer-title, .el-dialog__title, [class*="modal-title"], h1, h2, h3'
    );
    return ((title && title.innerText) || root.getAttribute('aria-label') || '').trim().split('\n')[0].slice(0, 40);
  };

  const scopeCss = (root) => {
    if (!root || root === document.body) return null;
    if (root.classList && root.classList.contains('oio-modal-wrapper')) return '.oio-modal-wrapper';
    if (root.getAttribute('role') === 'dialog') return '[role=dialog]';
    if (root.id && !/[0-9a-f]{8}/i.test(root.id)) return `#${CSS.escape(root.id)}`;
    const cls = Array.from(root.classList || [])
      .filter((c) => c.length < 30 && !/[0-9a-f]{6,}/i.test(c))
      .slice(0, 2);
    if (cls.length) return `${root.tagName.toLowerCase()}.${cls.map((c) => CSS.escape(c)).join('.')}`;
    return root.tagName.toLowerCase();
  };

  const nodeSketch = (node) => {
    const attrs = {};
    for (const a of Array.from(node.attributes || [])) {
      if (!/^(id|role|name|title|placeholder|aria-label|data-)/.test(a.name)) continue;
      if (a.value && a.value.length < 80) attrs[a.name] = a.value;
    }
    const cls = Array.from(node.classList || [])
      .filter((c) => c.length < 28 && !/[0-9a-f]{6,}/i.test(c) && !/iconfont/i.test(c))
      .slice(0, 3);
    const text = ((node.innerText || '').trim().split('\n')[0] || '').slice(0, 24);
    return {
      tag: node.tagName.toLowerCase(),
      cls,
      attrs,
      text: text || undefined,
    };
  };

  const COMBO_HOST_SEL = '.ant-select:not(.ant-select-dropdown), .el-select, .el-select__wrapper';
  const COMBO_OPTION_SEL = STD_OPTION_SEL;

  const clipHtml = (el, max) => {
    if (!el) return '';
    const html = el.outerHTML || '';
    return html.length > max ? html.slice(0, max) + '…' : html;
  };

  const widgetItemOf = (el) => (
    closestOf(el, '[data-name]')
    || closestOf(el, '.oio-form-item, .ant-form-item, .el-form-item, [class*="form-item"]')
  );

  const widgetInfoOf = (el) => {
    if (!el) return null;
    const item = widgetItemOf(el);
    const native = closestOf(el, 'select') || (item && item.querySelector('select'));
    const elWrap = closestOf(el, '.el-select__wrapper')
      || closestOf(el, '.el-select')
      || (item && item.querySelector('.el-select__wrapper, .el-select'));
    const ant = closestOf(el, '.ant-select:not(.ant-select-dropdown)')
      || (item && item.querySelector('.ant-select:not(.ant-select-dropdown)'));
    const combo = closestOf(el, '[role=combobox]')
      || (item && item.querySelector('[role=combobox]'));
    const handle = ((item && item.getAttribute('data-handle')) || '').trim();
    const name = ((item && item.getAttribute('data-name')) || '').trim();
    let kind = 'control';
    let trigger = el;
    if (elWrap && (!native || closestOf(native, '.el-select'))) {
      kind = 'el-select';
      trigger = (elWrap.classList && elWrap.classList.contains('el-select__wrapper'))
        ? elWrap
        : (elWrap.querySelector && elWrap.querySelector('.el-select__wrapper')) || elWrap;
    } else if (ant) {
      kind = 'ant-select';
      trigger = ant.querySelector('.ant-select-selector') || ant;
    } else if (native && !closestOf(native, '.el-select, .ant-select')) {
      kind = 'native-select';
      trigger = native;
    } else if (combo) {
      kind = 'combobox';
      trigger = closestOf(combo, '.el-select__wrapper, .ant-select-selector') || combo;
    }
    let triggerCss = null;
    if (name && kind === 'el-select') triggerCss = `[data-name="${CSS.escape(name)}"] .el-select__wrapper`;
    else if (name && kind === 'ant-select') triggerCss = `[data-name="${CSS.escape(name)}"] .ant-select-selector`;
    else if (name && kind === 'native-select') triggerCss = `[data-name="${CSS.escape(name)}"] select`;
    else if (name) triggerCss = `[data-name="${CSS.escape(name)}"]`;
    return {
      kind,
      trigger,
      item,
      name: name || null,
      handle: handle || null,
      trigger_css: triggerCss,
      html: clipHtml(item || trigger, 5000),
    };
  };

  const panelInfoOf = (el) => {
    if (!el) return null;
    const root = closestOf(el, STD_DROPDOWN_SEL)
      || closestOf(el, PORTAL_SEL)
      || closestOf(el, '.el-dropdown-menu, [role=listbox], .ant-dropdown');
    if (!root) return null;
    const cls = classStr(root);
    const insideHost = !!(
      closestOf(root, '.el-select, .ant-select:not(.ant-select-dropdown), .el-dropdown, .ant-select-selector')
    );
    const attach = insideHost ? 'inline' : 'teleport';
    let kind = 'custom-overlay';
    if (/el-select__popper|el-select-dropdown/.test(cls) || closestOf(root, '.el-select__popper, .el-select-dropdown')) {
      kind = 'el-select-dropdown';
    } else if (/ant-select-dropdown/.test(cls)) {
      kind = 'ant-select-dropdown';
    } else if (/ant-dropdown/.test(cls) && !/ant-select-dropdown/.test(cls)) {
      kind = 'ant-dropdown';
    } else if (/el-dropdown/.test(cls) || closestOf(root, '.el-dropdown-menu')) {
      kind = 'el-dropdown';
    } else if (root.getAttribute && root.getAttribute('role') === 'listbox') {
      kind = 'listbox';
    } else if (/el-popper|el-picker|ant-picker/.test(cls)) {
      kind = 'picker-overlay';
    }
    return { kind, attach, root, html: clipHtml(root, 6000) };
  };

  const scrollContainerOf = (el) => {
    let node = el;
    if (node === document || node === document.documentElement || node === document.body) {
      node = document.scrollingElement || document.documentElement;
    }
    for (let i = 0; node && i < 12; i++) {
      if (node.nodeType === 1) {
        const st = getComputedStyle(node);
        const oy = st.overflowY || st.overflow;
        const scrollable = (oy === 'auto' || oy === 'scroll' || oy === 'overlay')
          && node.scrollHeight > node.clientHeight + 16;
        if (scrollable) {
          const inLayer = closestOf(
            node,
            OVERLAY_SEL + ',' + STD_DROPDOWN_SEL + ', .el-scrollbar, .ant-modal-body, .el-dialog__body, .oio-modal'
          );
          if (inLayer) return node;
        }
      }
      node = parentOf(node);
    }
    return null;
  };

  const comboTriggerEl = (host) => {
    if (!host) return null;
    const info = widgetInfoOf(host);
    return (info && info.trigger) || host.querySelector('.el-select__wrapper, .ant-select-selector') || host;
  };

  const comboHostOf = (el) => {
    if (!el) return null;
    if (closestOf(el, STD_DROPDOWN_SEL)) {
      const opened = document.querySelector(
        '.ant-select-open, .ant-select-focused, .el-select.is-focus, .el-select.is-focused, '
        + '.el-select__wrapper.is-focused, [role=combobox][aria-expanded="true"]'
      ) || document.querySelector('.el-select:has(.is-focus), .el-select:has(.is-focused)');
      if (opened) return comboTriggerEl(opened);
      return null;
    }
    const host = closestOf(el, COMBO_HOST_SEL);
    if (host) return comboTriggerEl(host);
    if (el.getAttribute && el.getAttribute('role') === 'combobox') return el;
    return null;
  };

  const fieldSelectHostOf = (el) => {
    if (!el) return null;
    if (closestOf(el, STD_DROPDOWN_SEL + ', .select-options, .sizeTag')) return null;
    const item = closestOf(el, '.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"]');
    if (!item) return null;
    const trigger = item.querySelector(
      '.ant-select, .el-select, .el-select__wrapper, [role=combobox], [placeholder*="请选择"], [class*="select"]'
    );
    return trigger ? (comboTriggerEl(closestOf(trigger, COMBO_HOST_SEL) || trigger) || trigger) : null;
  };

  const isComboSearch = (el) => {
    if (!el || (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA')) return false;
    const ph = (el.placeholder || '').trim();
    if (/搜索|添加|请搜索|请选择/.test(ph)) return true;
    if (el.classList && el.classList.contains('ant-select-selection-search-input')) return true;
    if (closestOf(el, '.ant-select-selection-search, .el-select__input-wrapper, .el-select-dropdown__wrap')) return true;
    if (closestOf(el, STD_DROPDOWN_SEL)) return true;
    if (el.getAttribute && el.getAttribute('role') === 'combobox') return true;
    if (closestOf(el, COMBO_HOST_SEL) && (el.type || '').toLowerCase() === 'search') return true;
    return false;
  };

  const inDropdownOf = (el) => !!(
    closestOf(el, STD_DROPDOWN_SEL)
    || closestOf(el, PORTAL_SEL)
    || panelInfoOf(el)
  );

  const paneShown = (node) => {
    const pane = closestOf(node, '.el-tab-pane');
    if (!pane) return true;
    if (pane.getAttribute('aria-hidden') === 'true') return false;
    return isShown(pane);
  };

  const selectTabOf = (el) => {
    if (!el || !closestOf(el, STD_DROPDOWN_SEL)) return null;
    if (closestOf(el, '.sizeTag, .select-options, .el-tag')) return null;
    const tab = closestOf(el, '.el-tabs__item');
    if (tab && isShown(tab)) return tab;
    return null;
  };

  const selectTagOf = (el) => {
    if (!el) return null;
    if (closestOf(el, '.el-tag__close')) return null;
    if (closestOf(el, '.el-tabs__item, .el-tabs__header, .select-header, .title-tag')) return null;
    const tag = closestOf(el, '.el-tag');
    if (!tag || !isShown(tag) || !paneShown(tag)) return null;
    if (!closestOf(tag, '.sizeTag, .select-options')) return null;
    return tag;
  };

  const selectOptionOf = (el) => {
    if (!el) return null;
    if (!closestOf(el, STD_DROPDOWN_SEL)) return null;
    if (selectTabOf(el) || selectTagOf(el) || closestOf(el, '.select-body, .select-options, .el-tabs')) return null;
    const option = closestOf(el, STD_OPTION_SEL + ', [role=option]');
    if (!option || !isShown(option)) return null;
    return option;
  };

  const selectedChoiceOf = (el) => {
    if (!el) return '';
    if (el.tagName === 'SELECT') {
      const opt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
      return ((opt && (opt.label || opt.text)) || '').trim();
    }
    const root = closestOf(el, '.ant-select:not(.ant-select-dropdown), .el-select, .el-select__wrapper, [role=combobox]') || el;
    const item = root.querySelector && root.querySelector('.ant-select-selection-item, .el-select__selected-item');
    if (!item) return '';
    if (item.classList && (item.classList.contains('ant-select-selection-placeholder') || item.classList.contains('el-select__placeholder'))) {
      return '';
    }
    return ((item.getAttribute('title') || item.innerText || '').trim().split('\n')[0] || '');
  };

  const optionTitle = (option) => {
    if (!option) return '';
    const pre = option.querySelector && option.querySelector('pre, .el-tag__content');
    return (
      (pre && (pre.innerText || '').trim())
      || option.getAttribute('title')
      || option.getAttribute('aria-label')
      || visibleText(option)
      || (option.innerText || '').trim().split('\n')[0]
      || ''
    ).trim().slice(0, 40);
  };

  const pathNode = (e) => {
    const path = e && e.composedPath ? e.composedPath() : [];
    for (const node of path) {
      if (!node || !node.tagName) continue;
      if (node.id === '__atp_recorder_badge') break;
      if (ICON_TAGS.has(node.tagName)) continue;
      return node;
    }
    return (e && e.target) || null;
  };

  const hitNode = (e) => {
    const x = e && e.clientX;
    const y = e && e.clientY;
    if (typeof x === 'number' && document.elementsFromPoint) {
      const stack = (document.elementsFromPoint(x, y) || []).filter((node) => {
        if (!node || !node.tagName) return false;
        if (node.id === '__atp_recorder_badge') return false;
        if (node.closest && node.closest('#__atp_recorder_badge')) return false;
        return !ICON_TAGS.has(node.tagName);
      });
      const top = stack[0];
      if (top) {
        const inTabChrome = closestOf(top, '.el-tabs__item, .el-tabs__header, .el-tabs__nav, .el-tabs__active-bar');
        if (inTabChrome) {
          for (const node of stack) {
            const tab = closestOf(node, '.el-tabs__item');
            if (tab && isShown(tab)) return tab;
          }
        }
        const topTab = selectTabOf(top);
        if (topTab) return topTab;
        const topTag = selectTagOf(top);
        if (topTag) return topTag;
        const topOption = selectOptionOf(top);
        if (topOption) return topOption;
        if (closestOf(top, '.el-tabs__header, .select-header, .title-tag')) return top;
        if (closestOf(top, STD_DROPDOWN_SEL)) {
          for (const node of stack) {
            const tab = selectTabOf(node);
            if (tab) return tab;
            const tag = selectTagOf(node);
            if (tag) return tag;
            const option = selectOptionOf(node);
            if (option) return option;
          }
        }
        return top;
      }
    }
    return pathNode(e);
  };

  window.__atpComboHost = comboHostOf;
  window.__atpSelectedChoice = selectedChoiceOf;
  window.__atpFieldSelectHost = fieldSelectHostOf;
  window.__atpIsComboSearch = isComboSearch;
  window.__atpInDropdown = inDropdownOf;
  window.__atpOptionTitle = optionTitle;
  window.__atpSelectOption = selectOptionOf;
  window.__atpSelectTag = selectTagOf;
  window.__atpSelectTab = selectTabOf;
  window.__atpDeepNode = hitNode;
  window.__atpComboDescribeEl = comboTriggerEl;
  window.__atpWidgetInfo = widgetInfoOf;
  window.__atpPanelInfo = panelInfoOf;
  window.__atpScrollContainer = scrollContainerOf;

  const formItemLabel = (el) => {
    const item = widgetItemOf(el)
      || closestOf(el, '.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"]');
    if (!item) return null;
    const lab = item.querySelector(
      'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
    );
    let raw = ((lab && lab.innerText) || '').trim().split('\n')[0];
    if (!raw) {
      const prev = item.previousElementSibling;
      if (prev && (/label/i.test(String(prev.className || '')) || prev.tagName === 'LABEL')) {
        raw = ((prev && prev.innerText) || '').trim().split('\n')[0];
      }
    }
    if (!raw) {
      const named = item.getAttribute && item.getAttribute('data-name');
      if (named === 'brand') raw = '品牌';
      else if (named === 'basicProductType') raw = '品类';
      else if (named === 'productColors') raw = '颜色';
      else if (named === 'productSizes') raw = '尺码';
      else if (named === 'productSpecials') raw = '特殊工艺';
      else if (named === 'productCost') raw = '成本';
      else if (named === 'name') raw = '名称';
    }
    return raw ? raw.replace(/\*+/g, '').trim() : null;
  };

  const fieldRequiredOf = (el) => {
    if (!el) return null;
    const item = widgetItemOf(el)
      || closestOf(el, '.ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"]');
    if (!item) return null;
    if (item.querySelector('[aria-required="true"], [required]')) return true;
    const label = item.querySelector(
      'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, [class*="form-item-label"]'
    );
    const nodes = [item, label].filter(Boolean);
    for (const node of nodes) {
      const cls = String((node && node.className) || '');
      if (/\b(ant-form-item-required|el-form-item-required|is-required)\b/.test(cls)) return true;
    }
    if (label) {
      try {
        const star = `${getComputedStyle(label, '::before').content || ''}${getComputedStyle(label, '::after').content || ''}`;
        if (star.includes('*')) return true;
      } catch (err) { /* ignore */ }
      if (/\*/.test(label.innerText || '')) return true;
    }
    return false;
  };

  window.__atpFieldRequired = fieldRequiredOf;

  const stackingRoot = (el) => {
    let node = parentOf(el);
    let best = null;
    while (node && node !== document.body) {
      if (!node.getBoundingClientRect) {
        node = parentOf(node);
        continue;
      }
      const st = getComputedStyle(node);
      const z = parseInt(st.zIndex, 10);
      const pos = st.position;
      if ((pos === 'fixed' || pos === 'absolute') && z > 100 && isShown(node)) {
        const box = node.getBoundingClientRect();
        if (box.width > 200 && box.height > 120) best = node;
      }
      node = parentOf(node);
    }
    return best;
  };

  // 每次点击当场爬当前 DOM，不缓存上一次录制的结构。
  const crawlDom = (el) => {
    const portal = closestOf(el, PORTAL_SEL);
    const nested = closestOf(el, OVERLAY_SEL);
    const stacked = stackingRoot(el);
    const liveModals = Array.from(document.querySelectorAll(OVERLAY_SEL)).filter(isShown);
    let kind = 'page';
    let root = null;
    // 只认真正包住这个节点的层。页面上另有弹窗开着，不等于这次点的是弹窗。
    if (portal) {
      kind = 'dropdown';
      root = portal;
    } else if (nested) {
      kind = /drawer/i.test(classStr(nested)) ? 'drawer' : 'modal';
      root = nested;
    } else if (stacked) {
      kind = /drawer/i.test(classStr(stacked)) ? 'drawer' : 'modal';
      root = stacked;
    }

    const chain = [];
    let node = el;
    for (let i = 0; node && node !== document.body && i < 10; i++) {
      if (node.tagName) chain.push(nodeSketch(node));
      if (root && node === root) break;
      node = parentOf(node);
    }
    chain.reverse();
    const field = formItemLabel(el) || labelOf(el);
    const modalRoot = nested || liveModals[liveModals.length - 1] || null;
    let name = overlayTitle(root);
    if (kind === 'dropdown') {
      name = overlayTitle(modalRoot) || name || '下拉';
    }
    const pathParts = [];
    if (kind !== 'page') pathParts.push(`${kind}${name ? `「${name}」` : ''}`);
    if (field) pathParts.push(`字段「${field}」`);
    pathParts.push(chain.map((n) => n.tag + (n.text ? `:${n.text}` : '')).slice(-4).join('>'));

    return {
      scope: {
        kind,
        css: scopeCss(root),
        name: name || null,
        path: pathParts.join(' / '),
      },
      overlay_name: kind === 'page' ? null : (name || kind),
      label: field,
    };
  };

  window.__atpCrawlDom = crawlDom;

  // 元素所处的语境。录制出来的步骤要能读懂：
  // 「在『新增款式』弹窗里填写款式编码」比「填写第 3 个输入框」有用得多。
  window.__atpContext = (el) => {
    const crawl = crawlDom(el);
    const row = el.closest('tr');
    const info = widgetInfoOf(el);
    const panel = panelInfoOf(el);
    let widget = (info && info.kind) || null;
    if (!widget && el.tagName === 'SELECT') widget = 'native-select';
    return {
      dialog: crawl.overlay_name,
      label: crawl.label || (info && info.item && formItemLabel(el)) || labelOf(el),
      in_table_row: !!row,
      page_title: document.title,
      url: location.href,
      scope: crawl.scope,
      widget,
      panel: panel ? `${panel.kind}:${panel.attach}` : null,
      trigger_css: (info && info.trigger_css) || null,
      required: fieldRequiredOf(el),
    };
  };
})();
