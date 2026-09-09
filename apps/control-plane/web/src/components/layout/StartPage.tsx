import type { ModuleKind } from "../../types";
import { MODULES } from "../../types";

import { MODULE_ICONS } from "./moduleIcons";

const QUICK_LINKS: ModuleKind[] = ["site", "record", "run", "history"];

type Props = {
  onOpenModule: (kind: ModuleKind) => void;
};

export function StartPage({ onOpenModule }: Props) {
  return (
    <div className="editor-empty start-page">
      <div className="start-page-hero">
        <h2>自动化测试平台</h2>
        <p className="muted">Playwright 回放 · AI 观察者 · 套件运行</p>
      </div>

      <section className="quick-links">
        <h4 className="quick-links-title">Quick Links</h4>
        <div className="quick-links-grid">
          {QUICK_LINKS.map((kind) => {
            const Icon = MODULE_ICONS[kind];
            const meta = MODULES[kind];
            return (
              <button
                key={kind}
                type="button"
                className="quick-link-card"
                style={{ borderLeftColor: meta.color }}
                onClick={() => onOpenModule(kind)}
              >
                <Icon size={18} strokeWidth={2} aria-hidden style={{ color: meta.color }} />
                <span className="quick-link-name">{meta.title}</span>
                <span className="quick-link-desc">{meta.description}</span>
              </button>
            );
          })}
        </div>
      </section>

      <p className="start-page-hint">先在顶栏选择站点，再从左侧图标栏或上方快捷入口打开模块。</p>
    </div>
  );
}
