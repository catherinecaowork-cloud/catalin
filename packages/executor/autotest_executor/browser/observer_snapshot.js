// 观察者字段库存快照。依赖 locator_candidates.js 注入的 __atp* 辅助函数。
(() => {
  if (window.__atpCollectObservation) return;

  const BADGE_ID = '__atp_recorder_badge';
  const FORM_ITEM_SEL = '.ant-form-item, .el-form-item, .oio-form-item, [data-name]';
  const CONTROL_SEL = 'input, textarea, select, .el-select, .ant-select, [role=combobox], [role=switch], button[type=button]';
  const OVERLAY_SEL = [
    '[role=dialog]',
    '.ant-modal-wrap',
    '.ant-modal',
    '.el-dialog',
    '.el-overlay-dialog',
    '.oio-modal-wrapper',
    '.oio-modal',
    '.ant-drawer-content',
  ].join(',');
  // 与 locator_candidates 共用 __atpUiSelectors；未注入时退回最小子集（仅观察者自测）。
  const _S = globalThis.__atpUiSelectors || {};
  const PORTAL_SEL = _S.PORTAL_SEL || [
    '.ant-select-dropdown:not(.ant-select-dropdown-hidden)',
    '.el-select-dropdown',
    '.el-popper.el-select__popper',
  ].join(',');
  const OPTION_SEL = _S.STD_OPTION_SEL
    || '.ant-select-item-option, .el-select-dropdown__item, [role=option]';
  const MAX_FIELDS = 80;
  const MAX_OPTIONS = 20;
  const TRANSIENT_LABEL = /^\d{1,4}$/;

  const isShown = (node) => {
    if (!node || !node.getBoundingClientRect) return false;
    if (node.id === BADGE_ID || (node.closest && node.closest('#' + BADGE_ID))) return false;
    const st = getComputedStyle(node);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
    const box = node.getBoundingClientRect();
    return box.width >= 2 && box.height >= 2;
  };

  const overlayTitle = (root) => {
    if (!root || root === document.body) return null;
    const title = root.querySelector(
      '.ant-modal-title, .ant-drawer-title, .el-dialog__title, [class*="modal-title"], h1, h2, h3'
    );
    const text = ((title && title.innerText) || root.getAttribute('aria-label') || '').trim().split('\n')[0];
    return text ? text.slice(0, 80) : null;
  };

  const activeLayerRoot = () => {
    const overlays = Array.from(document.querySelectorAll(OVERLAY_SEL)).filter(isShown);
    if (overlays.length) return overlays[overlays.length - 1];
    return document.body;
  };

  const layerInfo = (root) => {
    if (!root || root === document.body) {
      return { kind: 'page', name: null, path: 'page' };
    }
    const cls = String((root.className || '')).toLowerCase();
    const kind = /drawer/.test(cls) ? 'drawer' : 'modal';
    const name = overlayTitle(root);
    return { kind, name, path: `${kind}${name ? `「${name}」` : ''}` };
  };

  const mapWidgetKind = (info, control) => {
    const raw = info && info.kind;
    if (raw === 'el-select' || raw === 'ant-select' || raw === 'combobox') return 'searchable_dropdown';
    if (raw === 'native-select') return 'dropdown';
    if (!control || !control.tagName) return 'unknown';
    const tag = control.tagName;
    if (tag === 'TEXTAREA') return 'textarea';
    if (tag === 'SELECT') return 'dropdown';
    if (tag === 'INPUT') {
      const t = (control.type || '').toLowerCase();
      if (t === 'password') return 'password';
      if (t === 'number') return 'number';
      if (t === 'checkbox') return 'checkbox';
      if (t === 'radio') return 'radio';
      if (t === 'file') return 'upload';
      return 'text';
    }
    if (control.matches && control.matches('[role=switch]')) return 'switch';
    return 'unknown';
  };

  const pickLocator = (target) => {
    if (!target || !target.candidates || !target.candidates.length) return null;
    const order = ['testid', 'field', 'matrix', 'role', 'label', 'placeholder', 'text', 'css'];
    const sorted = [...target.candidates].sort(
      (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind)
    );
    const cand = sorted[0];
    if (!cand || !cand.kind || cand.value == null) return null;
    const out = { kind: cand.kind, value: String(cand.value).slice(0, 120) };
    if (cand.name) out.name = String(cand.name).slice(0, 80);
    return out;
  };

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

  const fieldLabelOf = (item, control) => {
    const ctx = window.__atpContext ? window.__atpContext(control || item) : {};
    const label = (ctx && ctx.label) || null;
    if (label) return label.replace(/\*+/g, '').trim();
    const named = item.getAttribute && item.getAttribute('data-name');
    if (named) return FIELD_LABEL_MAP[named] || named;
    return null;
  };

  const controlOf = (item) => {
    if (!item) return null;
    if (item.matches && item.matches(CONTROL_SEL)) return item;
    const direct = item.querySelector && item.querySelector(CONTROL_SEL);
    if (direct) return direct;
    return item.querySelector && item.querySelector('.el-select__wrapper, .ant-select-selector, .el-select, .ant-select');
  };

  const controlShown = (control) => {
    if (!control) return false;
    if (isShown(control)) return true;
    const inner = control.querySelector && control.querySelector('.el-select__wrapper, .ant-select-selector, input, select, textarea');
    return !!(inner && isShown(inner));
  };

  const visibleOptions = () => {
    const portal = Array.from(document.querySelectorAll(PORTAL_SEL)).filter(isShown).pop();
    if (!portal) return { kind: null, options: [] };
    const options = Array.from(portal.querySelectorAll(OPTION_SEL))
      .filter(isShown)
      .map((node) => (window.__atpOptionTitle ? window.__atpOptionTitle(node) : ((node.innerText || '').trim().split('\n')[0])))
      .filter(Boolean)
      .slice(0, MAX_OPTIONS);
    const kind = /tab|size|尺码/i.test(options.join(' ')) ? 'tab_panel' : 'dropdown';
    return { kind, options };
  };

  const collectFields = (root) => {
    const seen = new Set();
    const fields = [];
    const items = Array.from(root.querySelectorAll(FORM_ITEM_SEL)).filter(isShown);
    for (const item of items) {
      if (fields.length >= MAX_FIELDS) break;
      const control = controlOf(item);
      if (!control || !controlShown(control)) continue;
      const label = fieldLabelOf(item, control);
      if (!label || TRANSIENT_LABEL.test(label)) continue;
      const key = label.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      const info = window.__atpWidgetInfo ? window.__atpWidgetInfo(control) : null;
      const widgetKind = mapWidgetKind(info, control);
      const target = window.__atpDescribe ? window.__atpDescribe(control) : null;
      const required = !!(window.__atpFieldRequired && window.__atpFieldRequired(control));
      fields.push({
        label: label.slice(0, 80),
        widget_kind: widgetKind,
        required,
        locator: pickLocator(target),
        sample_options: [],
      });
    }
    return fields;
  };

  window.__atpCollectObservation = (trigger) => {
    try {
      const root = activeLayerRoot();
      const layer = layerInfo(root);
      const fields = collectFields(root);
      const panel = visibleOptions();
      if (panel.options.length && fields.length) {
        const last = fields[fields.length - 1];
        if (last.widget_kind === 'searchable_dropdown' || last.widget_kind === 'dropdown') {
          last.sample_options = panel.options;
        }
      }
      return {
        trigger: trigger || 'form_visible',
        url: location.href,
        title: (document.title || '').slice(0, 120),
        layer,
        fields,
        open_panel_kind: panel.kind,
      };
    } catch (_) {
      return { trigger: trigger || 'form_visible', url: location.href, layer: { kind: 'page' }, fields: [] };
    }
  };
})();
