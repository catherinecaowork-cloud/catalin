import { CircleDot, Clock, Play } from "lucide-react";

type Props = {
  onOpenRecord: () => void;
  onOpenRun: () => void;
  onOpenHistory: () => void;
};

const ACTIONS = [
  {
    id: "record",
    title: "录制",
    desc: "顶栏录制开窗，保存后出现在左侧「测试用例」",
    color: "var(--c-record)",
    Icon: CircleDot,
    on: "onOpenRecord" as const,
  },
  {
    id: "run",
    title: "运行",
    desc: "在左侧选中用例或套件，底部操作区启动回放",
    color: "var(--c-run)",
    Icon: Play,
    on: "onOpenRun" as const,
  },
  {
    id: "history",
    title: "运行记录",
    desc: "展开左侧「运行记录」查看历史步骤与截图",
    color: "var(--c-history)",
    Icon: Clock,
    on: "onOpenHistory" as const,
  },
] as const;

export function StartPage({ onOpenRecord, onOpenRun, onOpenHistory }: Props) {
  const handlers = {
    onOpenRecord,
    onOpenRun,
    onOpenHistory,
  };

  return (
    <div className="editor-empty start-page">
      <div className="start-page-hero">
        <h2>自动化测试平台</h2>
        <p className="muted">先选环境，再录制或回放。左侧资源树是主入口。</p>
      </div>

      <section className="quick-links" aria-label="常用操作">
        <h4 className="quick-links-title">开始</h4>
        <div className="quick-links-list">
          {ACTIONS.map(({ id, title, desc, color, Icon, on }) => (
            <button key={id} type="button" className="quick-link-row" onClick={handlers[on]}>
              <span className="quick-link-icon" style={{ color }} aria-hidden>
                <Icon size={16} strokeWidth={2} />
              </span>
              <span className="quick-link-copy">
                <span className="quick-link-name">{title}</span>
                <span className="quick-link-desc">{desc}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <p className="start-page-hint">环境切换在顶栏左侧；Worker / 模型配置在右上角。</p>
    </div>
  );
}
