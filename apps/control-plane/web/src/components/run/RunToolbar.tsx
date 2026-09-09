type Props = {
  title: string;
  color: string;
  badge: string;
};

export function RunToolbar({ title, color, badge }: Props) {
  return (
    <div className="editor-toolbar run-toolbar">
      <span style={{ color }}>{title}</span>
      <span className="muted run-badge">{badge}</span>
    </div>
  );
}
