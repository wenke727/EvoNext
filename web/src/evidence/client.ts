import type { CorrectionDraft, SavedDraft, FrozenReview, UsePreview } from "./correction";
import { MediaCache } from "./media";

export type Summary = {
  snapshot_id: string;
  task_id: string;
  instruction: string;
  step_count: number;
  source_version: number | null;
  media_count: number;
};
export type Step = {
  index?: unknown;
  source_index?: unknown;
  step_id?: unknown;
  image?: string | null;
  value?: Record<string, unknown>;
  runtime?: unknown;
  [key: string]: unknown;
};
export type Detail = Summary & {
  trajectory: { traj: Step[]; [key: string]: unknown };
  metadata: Record<string, unknown>;
  missing_media: string[];
  manifest?: { media: Record<string, string>; [key: string]: unknown };
};
export type SourceTask = Omit<Summary, "snapshot_id" | "media_count">;
export type SourcePage = { items: SourceTask[]; next_cursor: string | null };
export type Page = { items: Summary[]; next_cursor: string | null };

export type IssueKind = "task_outcome" | "step_action" | "tool_execution" |
  "environment" | "safety" | "data_or_label" | "unknown";
export type CaseDecision = "confirmed" | "rejected" | "needs_evidence";
export type CaseProposal = {
  case_id: string;
  snapshot_id: string;
  position: number;
  source_step_id: string | null;
  issue_kind: IssueKind;
  summary: string;
  evidence_refs: string[];
  analysis_refs: {kind: "outcome" | "diagnosis"; producer: string; record_id: string; snapshot_id: string}[];
};
export type CaseView = CaseProposal & {
  source_version: number | null;
  review_status: "pending" | "operator_confirmed" | "rejected" | "needs_evidence";
  review_revision: number;
  created_at: string;
  created_by: string;
  authority: "none" | "configured_operator";
  history: {revision: number; decision: CaseDecision; reason: string; actor: string; created_at: string}[];
};

// A client belongs to one in-memory credential session. Never persist credentials or evidence.
export class EvidenceClient {
  readonly media: MediaCache;

  constructor(private readonly token: string) {
    this.media = new MediaCache(async (snapshot, path, signal) => {
      const response = await this.request(
        `/api/v1/snapshots/${snapshot}/media?path=${encodeURIComponent(path)}`,
        { signal },
      );
      return response.blob();
    });
  }

  async request(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers);
    headers.set("X-API-Key", this.token);
    const response = await fetch(path, { ...init, headers });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const reason = body.error ?? body.detail;
      throw new Error(
        typeof reason === "string"
          ? reason
          : Array.isArray(reason) ? reason.map(item => `${item.loc?.join(".")}: ${item.msg}`).join("\n")
          : `请求失败（HTTP ${response.status}）`,
      );
    }
    return response;
  }

  async ready(signal?: AbortSignal): Promise<{ demo: boolean; source_mode?: "legacy_mongo" | "snapshots" }> {
    return (await this.request("/health/ready", { signal })).json();
  }

  async listSource(after: string | null, signal?: AbortSignal): Promise<SourcePage> {
    return (await this.request(`/api/v1/source/tasks?limit=30${after ? `&after=${encodeURIComponent(after)}` : ""}`, {signal})).json();
  }

  async openSource(task: string, version: string): Promise<Summary> {
    if (!task.trim() || (version && !/^\d+$/.test(version))) throw new Error("请填写 Task ID；版本留空读取当前版本，0 有效");
    return (await this.request(`/api/v1/source/open/${encodeURIComponent(task.trim())}${version ? `?version=${encodeURIComponent(version)}` : ""}`, {method:"POST"})).json();
  }

  async list(after: string | null, signal?: AbortSignal): Promise<Page> {
    return (
      await this.request(
        `/api/v1/snapshots?limit=50${after ? `&after=${encodeURIComponent(after)}` : ""}`,
        { signal },
      )
    ).json();
  }

  async detail(id: string, signal: AbortSignal): Promise<Detail> {
    return (await this.request(`/api/v1/snapshots/${id}`, { signal })).json();
  }

  async casesForSnapshot(id: string, signal?: AbortSignal): Promise<{items: CaseView[]}> {
    return (await this.request(`/api/v1/snapshots/${id}/cases`, {signal})).json();
  }

  async createCase(proposal: CaseProposal): Promise<CaseView> {
    return (await this.request("/api/v1/cases", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(proposal),
    })).json();
  }

  async decideCase(id: string, revision: number,
                   body: {decision: CaseDecision; reason: string}): Promise<CaseView> {
    return (await this.request(`/api/v1/cases/${id}/review`, {
      method: "POST",
      headers: {"Content-Type": "application/json", "If-Match": `"${revision}"`},
      body: JSON.stringify(body),
    })).json();
  }

  async correctionDraft(id: string, signal?: AbortSignal): Promise<SavedDraft> {
    return (await this.request(`/api/v1/cases/${id}/draft`, {signal})).json();
  }

  async saveCorrections(id: string, command: {
    command_id: string; expected_draft_revision: number; draft: CorrectionDraft;
  }): Promise<SavedDraft> {
    return (await this.request(`/api/v1/cases/${id}/draft`, {
      method: "PUT",
      headers: {"Content-Type": "application/json", "If-Match": `"${command.expected_draft_revision}"`},
      body: JSON.stringify(command),
    })).json();
  }

  async reviewCorrections(id: string, command: {
    command_id: string; expected_review_revision: number; draft_revision: number;
    draft_hash: string; decision: CaseDecision; reason: string;
  }): Promise<CaseView> {
    return (await this.request(`/api/v1/cases/${id}/review`, {
      method: "POST",
      headers: {"Content-Type": "application/json", "If-Match": `"${command.expected_review_revision}"`},
      body: JSON.stringify(command),
    })).json();
  }

  async frozenReview(id: string, revision: number): Promise<FrozenReview> {
    return (await this.request(`/api/v1/cases/${id}/reviews/${revision}`)).json();
  }

  async correctionPreview(id: string, revision: number, purpose: string): Promise<UsePreview> {
    return (await this.request(`/api/v1/cases/${id}/reviews/${revision}/previews/${purpose}`)).json();
  }

  async importFile(file: File): Promise<Summary> {
    const zip = file.name.toLowerCase().endsWith(".zip");
    if (file.size > (zip ? 64 : 8) * 1024 * 1024)
      throw new Error("文件超过默认上传上限");
    const body = zip
      ? file
      : JSON.stringify({ trajectory: JSON.parse(await file.text()) });
    return (
      await this.request(zip ? "/api/v1/bundles" : "/api/v1/snapshots", {
        method: "POST",
        body,
        headers: {
          "Content-Type": zip ? "application/zip" : "application/json",
        },
      })
    ).json();
  }

  async importLegacy(task: string, version: string): Promise<Summary> {
    if (!task || !/^\d+$/.test(version))
      throw new Error("请填写 Task ID 和固定版本号（0 有效）");
    return (
      await this.request(
        `/api/v1/bridge/import/${encodeURIComponent(task)}?version=${encodeURIComponent(version)}`,
        { method: "POST" },
      )
    ).json();
  }

  async viewJson(id: string) {
    const tab = window.open("about:blank", "_blank");
    if (!tab) throw new Error("浏览器阻止了 JSON 视图，请允许此页面打开新标签");
    tab.opener = null;
    tab.document.title = "轨迹 JSON";
    tab.document.body.textContent = "正在读取固定快照…";
    try {
      const response = await this.request(`/api/v1/snapshots/${id}/trajectory`);
      const blob = new Blob([await response.arrayBuffer()], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      if (!tab.closed) tab.location.replace(url);
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      tab.close();
      throw error;
    }
  }

  async download(id: string, kind: "trajectory" | "bundle") {
    const blob = await (
      await this.request(`/api/v1/snapshots/${id}/${kind}`)
    ).blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download =
      kind === "bundle" ? "opencua-bundle.zip" : "trajectory.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
