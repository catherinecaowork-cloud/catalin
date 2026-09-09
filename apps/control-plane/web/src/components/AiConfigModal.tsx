import type { useAiConfig } from "../hooks/useAiConfig";
import { Alert, Button, Checkbox, Field, Input, Modal } from "./ui";

type AiState = ReturnType<typeof useAiConfig>;

export function AiConfigModal({ ai }: { ai: AiState }) {
  return (
    <Modal
      open={ai.open}
      onClose={ai.closeModal}
      title="AI 配置"
      titleId="aiConfigTitle"
      actions={
        <>
          <Button variant="ghost" onClick={ai.closeModal}>
            取消
          </Button>
          <Button variant="ghost" disabled={ai.loading} onClick={() => void ai.test()}>
            测试连通
          </Button>
          <Button variant="primary" disabled={ai.loading} onClick={() => void ai.save()}>
            保存
          </Button>
        </>
      }
    >
      <p className="muted">模型网关用于录制编译与定位自愈。配置保存在 var/ai.json。</p>
      {ai.envHint ? <p className="muted">{ai.envHint}</p> : null}
      <Field label="Base URL">
        <Input
          type="text"
          value={ai.baseUrl}
          placeholder="https://api.example.com/v1/messages"
          onChange={(event) => ai.setBaseUrl(event.target.value)}
        />
      </Field>
      <Field label="Model">
        <Input
          type="text"
          value={ai.model}
          placeholder="claude-sonnet-4-20250514"
          onChange={(event) => ai.setModel(event.target.value)}
        />
      </Field>
      <Field label="Auth Token">
        <Input
          type="password"
          value={ai.authToken}
          placeholder={ai.tokenPlaceholder}
          autoComplete="off"
          onChange={(event) => ai.setAuthToken(event.target.value)}
        />
      </Field>
      <Checkbox
        label="启用视觉（截图理解）"
        checked={ai.visionEnabled}
        onChange={(event) => ai.setVisionEnabled(event.target.checked)}
      />
      {ai.error ? <Alert variant="error">{ai.error}</Alert> : null}
      {ai.success ? <Alert>{ai.success}</Alert> : null}
    </Modal>
  );
}
