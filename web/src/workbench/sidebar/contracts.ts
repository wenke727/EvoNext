import type { ReactNode } from "react";
import type { Task } from "./model";

export interface SidebarPorts {
  request(path: string, init?: RequestInit): Promise<Task>;
  taskUrl(taskId: string, step?: number | null): string;
  contextUrl(taskId: string): string;
  plannerUrl(taskId: string): string;
  copy(value: string): Promise<void>;
  jump(position: number): void;
}
export interface SidebarPreferences {
  showTime?: boolean;
  showEvaluation?: boolean;
  comments: boolean;
  qa: boolean;
  operations: boolean;
  planner: boolean;
  audit: boolean;
  auditOptions: {
    taskStatusOptions: string[];
    primaryErrorCauses: string[];
    secondaryErrorCauses: string[];
  };
}
export interface SidebarProps {
  task: Task;
  disabled: boolean;
  preferences: SidebarPreferences;
  ports: SidebarPorts;
  evaluation: ReactNode;
  onField(
    field: "instruction" | "operation_suggestion" | "qa_review",
    value: unknown,
  ): void;
  onTags(tags: string[]): void;
  onAudit(value: Task): void;
}
