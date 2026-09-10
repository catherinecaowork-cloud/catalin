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
    '.oio-action-item', '[data-action-name]', '.ant-btn', '.el-button',
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
    if (/^(el-id-|rc_select_|rc-menu|form_item_\d)/i.test(id)) return true;
    if (/^el-id-\d/.test(id)) return true;
    // vxe-table 单元格包装 div：315ac707-e508-4e63-810d-01f6c53d1df1-0-0
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(-\d+-\d+)?$/i.test(id)) {
      return true;
    }
    if (/^\d+[0-9a-f-]{20,}(-\d+-\d+)?$/i.test(id)) return true;
    return false;
  };
  const isEphemeralClass = (cls) => (
    /^(is-focused|is-focus|is-active|is-hover|is-selected|is-disabled|is-checked|ant-select-open|ant-select-focused|ant-picker-focused)$/i.test(cls)
  );
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
        .filter((c) => c.length < 25 && !/[0-9a-f]{6,}/i.test(c) && !/iconfont|icon/i.test(c) && !isEphemeralClass(c))
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
    // get_by_label 只认 <label for> / 包裹的 label / aria-label(ledby)。
    // Oinone 的 <div class="label"> 不在其列，拿它当 label 候选必然空等再漂移。
    const ariaLabel = ((el.getAttribute && el.getAttribute('aria-label')) || '').trim();
    const nativeLabel = (ariaLabel || labelOf(el) || '').trim();
    if (role) {
      // 输入框不要用 value/段落序号当 accessible name：role=textbox name="1"
      // 会子串命中「2026-09-09 13:56:43」里的 1，误点到只读日期框。
      let accName = nativeLabel;
      if (!accName && el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA') {
        accName = (text || '').trim();
      }
      if (accName && !ICON_TEXT.test(accName) && !/^\d{1,4}$/.test(accName)) {
        candidates.push({ kind: 'role', value: role, name: accName });
      } else {
        candidates.push({ kind: 'role', value: role, name: null });
      }
    }

    if (nativeLabel && nativeLabel.length < 40 && !ICON_TEXT.test(nativeLabel)) {
      candidates.push({ kind: 'label', value: nativeLabel });
    }
    if (el.placeholder && !/^(请输入|请选择|请填写|搜索)/.test(el.placeholder.trim()) && !/搜索|添加/.test(el.placeholder)) {
      candidates.push({ kind: 'placeholder', value: el.placeholder });
    }

    const selectLike = !!(closestOf(raw, '.el-select, .ant-select:not(.ant-select-dropdown), [role=combobox]'));
    const placeholderText = /^(请选择|请输入|请填写|搜索)/.test((text || '').trim());
    if (text && !(selectLike && placeholderText)) candidates.push({ kind: 'text', value: text });

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

    // 同格标签锚定：弹窗里有好几个日期框时，只有这个能分清交货日期和下单日期。
    const scoped = inPortal ? null : oinoneScopedSelectors(raw);
    if (scoped) {
      for (let i = scoped.selectors.length - 1; i >= 0; i--) {
        const sel = scoped.selectors[i];
        if (!candidates.some((c) => c.value === sel)) candidates.unshift({ kind: 'css', value: sel });
      }
    }

    const matrix = inPortal ? null : matrixCellOf(raw);
    if (matrix) {
      candidates.unshift({ kind: 'matrix', value: matrix.value, name: matrix.table });
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

    const placeholderLabel = placeholderClickLabelOf(raw);
    if (placeholderLabel && !inPortal) {
      if (!candidates.some((c) => c.kind === 'text' && c.value === placeholderLabel)) {
        candidates.unshift({ kind: 'text', value: placeholderLabel });
      }
      if (!candidates.some((c) => c.kind === 'label' && c.value === placeholderLabel)) {
        candidates.unshift({ kind: 'label', value: placeholderLabel });
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
    '.el-dialog__wrapper',
    '.el-overlay',
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

  const isFieldHost = (node) => {
    if (!node || !node.getAttribute) return false;
    const dn = (node.getAttribute('data-name') || '').trim();
    if (!dn) return false;
    return !!node.querySelector(
      '.ant-picker:not(.ant-picker-dropdown), .el-date-editor:not(.el-picker-panel), '
      + '.ant-select:not(.ant-select-dropdown), .el-select, input, textarea, select, [role=combobox]'
    );
  };

  const widgetItemOf = (el) => {
    const formItem = closestOf(el, '.oio-form-item, .ant-form-item, .el-form-item, [class*="form-item"]');
    // 最内层的 [data-name] 才是这个控件；再往外是整块表单，认错就会张冠李戴。
    let best = null;
    let node = el;
    for (let i = 0; node && node !== document.body && i < 14; i++) {
      if (isFieldHost(node)) { best = node; break; }
      node = parentOf(node);
    }
    if (best) return best;
    if (formItem) return formItem;
    return closestOf(el, '[data-name]')
      || closestOf(el, '.oio-form-item, .ant-form-item, .el-form-item, [class*="form-item"]');
  };

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
    } else {
      const antPicker = closestOf(el, '.ant-picker:not(.ant-picker-dropdown)')
        || (item && item.querySelector('.ant-picker:not(.ant-picker-dropdown)'));
      const elDate = closestOf(el, '.el-date-editor:not(.el-picker-panel)')
        || (item && item.querySelector('.el-date-editor:not(.el-picker-panel)'));
      if (antPicker) {
        kind = 'ant-date-picker';
        trigger = antPicker.querySelector('.ant-picker-input') || antPicker;
      } else if (elDate) {
        kind = 'el-date-picker';
        trigger = elDate.querySelector('input') || elDate;
      }
    }
    let triggerCss = null;
    if (name && kind === 'el-select') triggerCss = `[data-name="${CSS.escape(name)}"] .el-select__wrapper`;
    else if (name && kind === 'ant-select') triggerCss = `[data-name="${CSS.escape(name)}"] .ant-select-selector`;
    else if (name && kind === 'native-select') triggerCss = `[data-name="${CSS.escape(name)}"] select`;
    else if (name && kind === 'ant-date-picker') triggerCss = `[data-name="${CSS.escape(name)}"] .ant-picker-input input`;
    else if (name && kind === 'el-date-picker') triggerCss = `[data-name="${CSS.escape(name)}"] .el-date-editor input`;
    else if (name) triggerCss = `[data-name="${CSS.escape(name)}"]`;
    if (!triggerCss) {
      // 没有 data-name 的表单（Oinone form-container）改用同格标签当锚点。
      const scoped = oinoneScopedSelectors(el);
      if (scoped) triggerCss = scoped.selectors[0];
    }
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
        if (window.__atpLookupTableAction) {
          for (const node of stack) {
            const act = window.__atpLookupTableAction(node);
            if (act) return act;
          }
        }
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

  const pickerDateOf = (el) => {
    if (!el) return null;
    const cell = closestOf(el, 'td.ant-picker-cell, .ant-picker-cell, .el-date-table td.available');
    if (!cell || !isShown(cell)) return null;
    let date = (cell.getAttribute('title') || '').trim();
    if (!date) {
      const inner = cell.querySelector('.ant-picker-cell-inner');
      date = ((inner && inner.getAttribute('title')) || '').trim();
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
    return { cell, date };
  };

  const pickerHostOf = (el) => {
    const panelRoot = closestOf(el, '.ant-picker-dropdown, .el-picker-panel, .el-popper.is-pure');
    if (!panelRoot) return null;
    const expandedInputs = Array.from(document.querySelectorAll(
      '.ant-picker-input input[aria-expanded="true"], .el-date-editor input[aria-expanded="true"]'
    ));
    for (const input of expandedInputs) {
      const controls = input.getAttribute('aria-controls');
      if (!controls) continue;
      const linked = document.getElementById(controls);
      if (linked && (linked === panelRoot || linked.contains(el) || panelRoot.contains(linked))) {
        return closestOf(input, '.ant-picker:not(.ant-picker-dropdown), .el-date-editor:not(.el-picker-panel)');
      }
    }
    if (expandedInputs.length === 1) {
      return closestOf(
        expandedInputs[0],
        '.ant-picker:not(.ant-picker-dropdown), .el-date-editor:not(.el-picker-panel)'
      );
    }
    const modal = closestOf(el, '.ant-modal-wrap, .oio-modal-wrapper, .el-dialog, .ant-modal-content');
    if (modal) {
      const pickers = modal.querySelectorAll(
        '.ant-picker:not(.ant-picker-dropdown), .el-date-editor:not(.el-picker-panel)'
      );
      if (pickers.length === 1) return pickers[0];
      for (const picker of pickers) {
        const input = picker.querySelector('input[aria-expanded="true"]');
        if (input) return picker;
      }
    }
    return null;
  };

  window.__atpComboHost = comboHostOf;
  window.__atpPickDate = pickerDateOf;
  window.__atpPickerHost = pickerHostOf;
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

  const FIELD_LABEL_MAP = {
    brand: '品牌',
    basicProductType: '品类',
    productColors: '颜色',
    productSizes: '尺码',
    productSpecials: '特殊工艺',
    productCost: '成本',
    name: '名称',
    poNo: 'PO号',
    poNumber: 'PO号',
    customerOrderNo: '客户单号',
    orderDate: '下单日期',
    deliveryDate: '交货日期',
    productionOrderNo: '生产单号',
    launchDate: '上市日期',
    factoryId: '生产工厂',
    sewingLineId: '缝制线组',
    customerId: '客户',
  };

  const BAD_FIELD_LABEL = /^(—|--|-|–|一|请选择日期|请选择|请输入|请填写)$/;

  const cleanFieldLabel = (raw) => {
    const text = (raw || '').replace(/\*+/g, '').trim().split('\n')[0].trim();
    if (!text || BAD_FIELD_LABEL.test(text)) return '';
    return text;
  };

  // Oinone form-container：必填字段标签常写成「*交货日期」，在控件左侧/前一个兄弟节点。
  const oinoneStarLabelOf = (el) => {
    const host = closestOf(
      el,
      '.ant-picker, .el-date-editor, .el-select, .ant-select, .ant-input-affix-wrapper, '
      + '.oio-input, [class*="form-item"], .form-container > div'
    ) || el;
    let node = host;
    for (let i = 0; node && i < 8; i++) {
      let prev = node.previousElementSibling;
      while (prev) {
        const raw = (prev.innerText || '').trim().split('\n')[0].trim();
        if (/^\*[\u4e00-\u9fffA-Za-z0-9/（）()-]{1,16}$/.test(raw)) {
          return cleanFieldLabel(raw);
        }
        const plain = cleanFieldLabel(raw);
        if (plain && plain.length >= 2 && plain.length <= 12 && /^[\u4e00-\u9fff]/.test(plain)) {
          return plain;
        }
        if (prev.querySelector('input, textarea, select, .ant-picker, .el-date-editor, .el-select, .ant-select')) {
          break;
        }
        prev = prev.previousElementSibling;
      }
      node = parentOf(node);
    }
    return null;
  };

  const nearestRowLabelOf = (el) => {
    const row = closestOf(el, '.form-row, .oio-row, .ant-row, tr, [class*="form-item"]');
    if (!row) return null;
    const cells = Array.from(row.children);
    if (!cells.length) return null;
    let host = el;
    while (host && host !== row && !cells.includes(host)) host = parentOf(host);
    const idx = host && host !== row ? cells.indexOf(host) : -1;
    const start = idx >= 0 ? idx - 1 : cells.length - 1;
    for (let i = start; i >= 0; i--) {
      const cell = cells[i];
      if (cell.contains(el)) continue;
      if (cell.querySelector(
        'input, textarea, select, .el-select, .ant-select, .ant-picker, .el-date-editor, [role=combobox]'
      )) continue;
      const t = cleanFieldLabel(cell.innerText);
      if (!t || t.length > 24) continue;
      return t;
    }
    return null;
  };

  const nearbyLabelOf = (el) => {
    if (!el) return null;
    const item = widgetItemOf(el)
      || closestOf(el, '.form-container, .form-row, .oio-row, .ant-row, tr, .ant-form-item, .el-form-item, .oio-form-item, [class*="form-item"]');
    if (!item) return null;
    const lab = item.querySelector(
      'label, .ant-form-item-label, .el-form-item__label, .oio-form-item-label, '
      + '[class*="form-item-label"], [class*="field-label"], .field-name, .form-label, th'
    );
    let raw = cleanFieldLabel(lab && lab.innerText);
    if (!raw) {
      const prev = item.previousElementSibling;
      if (prev && (/label/i.test(String(prev.className || '')) || prev.tagName === 'LABEL')) {
        raw = cleanFieldLabel(prev.innerText);
      }
    }
    if (!raw) raw = nearestRowLabelOf(el) || '';
    if (!raw && el.getAttribute) {
      const labelledBy = el.getAttribute('aria-labelledby');
      if (labelledBy) {
        const ref = document.getElementById(labelledBy);
        raw = cleanFieldLabel(ref && ref.innerText);
      }
    }
    if (!raw && el.placeholder) {
      const ph = el.placeholder.trim();
      if (ph && !/^(请输入|请选择|请填写)$/.test(ph)) raw = ph;
    }
    return raw || null;
  };

  const formItemLabel = (el) => {
    const item = widgetItemOf(el);
    const named = item && item.getAttribute && item.getAttribute('data-name');
    if (named) {
      const mapped = FIELD_LABEL_MAP[named] || named;
      if (mapped && !BAD_FIELD_LABEL.test(mapped)) return cleanFieldLabel(mapped);
    }
    const wrap = oinoneFieldWrapOf(el);
    if (wrap && wrap.label) return wrap.label;
    const oinone = oinoneStarLabelOf(el);
    if (oinone) return oinone;
    const raw = nearbyLabelOf(el);
    return raw ? cleanFieldLabel(raw) : null;
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

  // Oinone form-container 一格长这样，标签和控件是亲兄弟：
  //   <div style="width:25%"><div class="label">*交货日期</div><div class="ant-picker">…</div></div>
  // 只认这一层的 .label。顺着 DOM 往外捞会捡到隔壁字段，回放就点到「下单日期」。
  const OINONE_LABEL_SEL = '.label, .field-label, [class*="form-label"]';

  const oinoneFieldWrapOf = (el) => {
    let node = el;
    for (let i = 0; node && node !== document.body && i < 10; i++) {
      const parent = parentOf(node);
      if (!parent || !parent.children) { node = parent; continue; }
      for (const child of Array.from(parent.children)) {
        if (child === node || !child.matches) continue;
        if (child.contains(el) || !child.matches(OINONE_LABEL_SEL)) continue;
        const text = cleanFieldLabel(child.innerText);
        if (!text || text.length > 24) continue;
        const labelSel = child.classList && child.classList.contains('label')
          ? '.label'
          : '[class*="label"]';
        return { wrap: parent, label: text, labelSel };
      }
      node = parent;
    }
    return null;
  };

  // 控件尾缀：锚到标签之后还要指到真正能点的那个节点。
  const CONTROL_TAIL = [
    ['.ant-picker:not(.ant-picker-dropdown)', '.ant-picker-input input'],
    ['.el-date-editor:not(.el-picker-panel)', '.el-date-editor input'],
    ['.ant-select:not(.ant-select-dropdown)', '.ant-select-selector'],
    ['.el-select', '.el-select__wrapper'],
    ['textarea', 'textarea'],
    ['input', 'input'],
  ];

  const oinoneScopedSelectors = (el) => {
    const hit = oinoneFieldWrapOf(el);
    if (!hit) return null;
    const name = hit.label.replace(/["\\]/g, '').trim();
    if (!name) return null;
    let tail = '';
    for (const [probe, sel] of CONTROL_TAIL) {
      if (hit.wrap.querySelector(probe)) { tail = ' ' + sel; break; }
    }
    return {
      label: hit.label,
      selectors: [
        `div:has(> ${hit.labelSel}:text-is("${name}"))${tail}`,
        `div:has(> ${hit.labelSel}:has-text("${name}"))${tail}`,
      ],
    };
  };

  window.__atpOinoneScoped = oinoneScopedSelectors;

  // 颜色×尺码矩阵：列头是动态尺码、单元格 id 是 vxe 随机 uuid，只能记「行×列」。
  const matrixCellOf = (el) => {
    const input = closestOf(el, 'input.vxe-input--inner, textarea, input') || el;
    if (!input || !input.tagName || (input.tagName !== 'INPUT' && input.tagName !== 'TEXTAREA')) {
      return null;
    }
    const cell = closestOf(input, 'td, th');
    if (!cell) return null;
    const row = closestOf(cell, 'tr');
    let table = closestOf(row, 'table');
    if (!table && row && row.closest) {
      const wrap = row.closest('.vxe-table--body-wrapper, .vxe-table, .el-table__body');
      if (wrap && wrap.querySelector) table = wrap.querySelector('table');
    }
    if (!row || !table) return null;

    const headerRow = table.querySelector('thead tr') || table.querySelector('tr');
    if (!headerRow) return null;
    const headerCells = Array.from(headerRow.querySelectorAll('th, td'));
    if (headerCells.length < 3) return null;

    const tableTitle = cleanFieldLabel(headerCells[0].innerText) || '颜色尺码';
    const sizeHeaders = headerCells.slice(1).filter((node) => /^\d{1,4}$/.test(cleanFieldLabel(node.innerText)));
    if (sizeHeaders.length < 2 && !/颜色|尺码/.test(tableTitle)) return null;

    const rowCells = Array.from(row.querySelectorAll('td, th'));
    const cellIdx = rowCells.indexOf(cell);
    if (cellIdx <= 0) return null;

    const rowLabel = cleanFieldLabel(rowCells[0].innerText);
    if (!rowLabel || rowLabel === '合计' || rowLabel === tableTitle) return null;

    const colLabel = cleanFieldLabel((headerCells[cellIdx] && headerCells[cellIdx].innerText) || '');
    if (!colLabel || colLabel === '合计') return null;

    return {
      table: tableTitle,
      row: rowLabel,
      col: colLabel,
      value: `${rowLabel}|${colLabel}`,
    };
  };

  window.__atpMatrixCell = matrixCellOf;

  const sectionTitleOf = (section) => {
    if (!section) return null;
    const heading = section.querySelector(
      'h1, h2, h3, h4, legend, .section-title, [class*="section-title"], [class*="form-section-title"]'
    );
    let raw = cleanFieldLabel((heading && heading.innerText) || '');
    if (!raw) {
      const first = (section.innerText || '').trim().split('\n')[0].trim();
      raw = cleanFieldLabel(first.replace(/^\d+\.\s*/, ''));
    }
    if (!raw) return null;
    raw = raw.replace(/信息$/, '').trim();
    if (!raw) return null;
    if (/加号/.test(raw)) return raw;
    return `${raw}加号`;
  };

  const placeholderClickLabelOf = (el) => {
    if (!el) return null;
    const placeholder = closestOf(el, '.empty-placeholder, [class*="empty-placeholder"]');
    const infoWrap = closestOf(el, '.info-wrap, [class*="info-wrap"]');
    if (!placeholder && !infoWrap) return null;
    const host = placeholder || infoWrap;
    const section = closestOf(host, 'section.form-section, .form-section, [class*="form-section"]');
    const titled = sectionTitleOf(section);
    if (titled) return titled;
    const hasPlus = host.querySelector(
      '.anticon-plus, .el-icon-plus, [class*="icon-plus"], [aria-label="plus"], [aria-label="Plus"]'
    );
    if (placeholder || hasPlus) return '加号';
    return null;
  };

  window.__atpPlaceholderLabel = placeholderClickLabelOf;

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
    const field = placeholderClickLabelOf(el) || formItemLabel(el) || labelOf(el);
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
    const matrix = matrixCellOf(el);
    let widget = (info && info.kind) || null;
    if (!widget && el.tagName === 'SELECT') widget = 'native-select';
    return {
      dialog: crawl.overlay_name,
      label: (matrix && `${matrix.table} ${matrix.row}×${matrix.col}`)
        || placeholderClickLabelOf(el) || crawl.label || (info && info.item && formItemLabel(el)) || labelOf(el),
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
