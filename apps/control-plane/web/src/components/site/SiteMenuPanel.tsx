import type { Credential, Site } from "../../types";
import { CreateSiteForm } from "./CreateSiteForm";
import { CredentialForm } from "./CredentialForm";
import { SiteList } from "./SiteList";

type Props = {
  sites: Site[];
  selectedSiteId: string | null;
  credentials: Credential[];
  credsLoading: boolean;
  onSelect: (siteId: string) => void;
  onDeleteSite: (site: Site) => void;
  onDeleteCredential: (credentialId: string) => void;
  onCreateSite: (name: string, baseUrl: string) => Promise<unknown>;
  onSaveLogin: (path: string, username: string, password: string) => Promise<void>;
  onLog: (message: string, level?: "info" | "warn" | "error") => void;
};

export function SiteMenuPanel({
  sites,
  selectedSiteId,
  credentials,
  credsLoading,
  onSelect,
  onDeleteSite,
  onDeleteCredential,
  onCreateSite,
  onSaveLogin,
  onLog,
}: Props) {
  return (
    <div className="sitemenu open">
      <div className="sitemenu-head">工作站点</div>
      <div className="sitemenu-list">
        <SiteList
          sites={sites}
          selectedSiteId={selectedSiteId}
          onSelect={onSelect}
          onDelete={onDeleteSite}
        />
      </div>
      <CredentialForm
        selectedSiteId={selectedSiteId}
        credentials={credentials}
        credsLoading={credsLoading}
        onDeleteCredential={onDeleteCredential}
        onSaveLogin={onSaveLogin}
        onLog={onLog}
      />
      <CreateSiteForm onCreateSite={onCreateSite} onLog={onLog} />
    </div>
  );
}
