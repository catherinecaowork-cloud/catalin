import type { EditorTab } from "../../types";

import { MODULES } from "../../types";

import { Sidebar, SidebarBody, SidebarFoot } from "../layout/Sidebar";

import { RunProvider } from "../../context/RunContext";

import { HistorySidebar, HistorySidebarFoot } from "../history/HistorySidebar";

import { RecordSidebar, RecordSidebarFoot } from "../record/RecordSidebar";

import { RunSidebar, RunSidebarFootActions } from "../run/RunSidebar";

import { parseRunTabId } from "../../utils/tabs";

import { Button } from "../ui";



type Props = {

  activeTab: EditorTab | null;

  siteId: string | null;

  sites: Parameters<typeof RunProvider>[0]["sites"];

  onLog: (message: string, level?: "info" | "warn" | "error") => void;

  onOpenRun: (runId: string, title: string, headed: boolean) => void;

  onRefreshWorkers: () => void;

  onToggleLog: () => void;

};



export function AppSidebar({

  activeTab,

  siteId,

  sites,

  onLog,

  onOpenRun,

  onRefreshWorkers,

  onToggleLog,

}: Props) {

  const open = !!activeTab;

  const title = activeTab ? MODULES[activeTab.kind].title : "模块";

  const activeRunId = activeTab ? parseRunTabId(activeTab.id) : null;



  if (!activeTab) {

    return (

      <Sidebar

        open={open}

        title={title}

        body={

          <SidebarBody>

            <p className="muted">从左侧活动栏打开一个模块。</p>

          </SidebarBody>

        }

      />

    );

  }



  if (activeTab.kind === "run") {

    return (

      <RunProvider siteId={siteId} sites={sites} onLog={onLog}>

        <Sidebar

          open={open}

          title={title}

          body={

            <SidebarBody>

              <RunSidebar />

            </SidebarBody>

          }

          foot={

            !activeRunId ? (

              <SidebarFoot>

                <RunSidebarFootActions onOpenRun={onOpenRun} />

              </SidebarFoot>

            ) : undefined

          }

        />

      </RunProvider>

    );

  }



  if (activeTab.kind === "record") {

    return (

      <Sidebar

        open={open}

        title={title}

        body={

          <SidebarBody>

            <RecordSidebar />

          </SidebarBody>

        }

        foot={

          <SidebarFoot>

            <RecordSidebarFoot />

          </SidebarFoot>

        }

      />

    );

  }



  if (activeTab.kind === "history") {

    return (

      <Sidebar

        open={open}

        title={title}

        body={

          <SidebarBody>

            <HistorySidebar onOpenRun={(runId, title) => onOpenRun(runId, title, false)} />

          </SidebarBody>

        }

        foot={

          <SidebarFoot>

            <HistorySidebarFoot onRefreshWorkers={onRefreshWorkers} />

          </SidebarFoot>

        }

      />

    );

  }



  if (activeTab.kind === "log") {

    return (

      <Sidebar

        open={open}

        title={title}

        body={

          <SidebarBody>

            <p className="muted">运行/录制日志写入下方底栏。告警与错误会自动展开。</p>

            <Button variant="primary" onClick={onToggleLog}>

              展开 / 收起底栏

            </Button>

          </SidebarBody>

        }

      />

    );

  }



  return (

    <Sidebar

      open={open}

      title={title}

      body={

        <SidebarBody>

          <p className="muted">{MODULES[activeTab.kind].description}</p>

        </SidebarBody>

      }

    />

  );

}


