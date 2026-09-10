import { CircleDot, Clock, Play } from "lucide-react";

type Props = {
  onOpenRecord: () => void;
  onOpenRun: () => void;
  onOpenHistory: () => void;
};

export function StartPage({ onOpenRecord, onOpenRun, onOpenHistory }: Props) {
  return (
    <div className="editor-empty start-page">
      <div className="start-page-hero">
        <h2>自动化测试平台</h2>
        <p className="muted">Playwright 回放 · AI 观察者 · 套件运行</p>
      </div>

      <section className="quick-links">
        <h4 className="quick-links-title">Quick Links</h4>
        <div className="quick-links-grid">
          <button type="button" className="quick-link-card" style={{ borderLeftColor: "var(--c-record)" }} onClick={onOpenRecord}>
            <CircleDot size={18} strokeWidth={2} aria-hidden style={{ color: "var(--c-record)" }} />
            <span className="quick-link-name">录制</span>
            <span className="quick-link-desc">顶栏「录制」开窗，保存后出现在左侧测试用例</span>
          </button>
          <button type="button" className="quick-link-card" style={{ borderLeftColor: "var(--c-run)" }} onClick={onOpenRun}>
            <Play size={18} strokeWidth={2} aria-hidden style={{ color: "var(--c-run)" }} />
            <span className="quick-link-name">运行</span>
            <span className="quick-link-desc">在左侧展开测试用例或套件，选中后回放</span>
          </button>
          <button type="button" className="quick-link-card" style={{ borderLeftColor: "var(--c-history)" }} onClick={onOpenHistory}>
            <Clock size={18} strokeWidth={2} aria-hidden style={{ color: "var(--c-history)" }} />
            <span className="quick-link-name">运行记录</span>
            <span className="quick-link-desc">左侧「运行记录」文件夹可打开历史回放</span>
          </button>
        </div>
      </section>

      <p className="start-page-hint">先在顶栏选择站点。录制在横向工具栏；用例、套件、记录在左侧资源树展开或收起。</p>
    </div>
  );
}
