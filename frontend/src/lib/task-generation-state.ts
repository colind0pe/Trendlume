export function generationStatus(task: {
  status?: string;
  active_job?: { status?: string; job_type?: string } | null;
}, liveStatus: string | null = null): string {
  const job = task.active_job;
  if (job && job.job_type !== "publish" && job.status) {
    if (job.status === "queued" || job.status === "pending") return "pending";
    if (job.status === "retrying") return "running";
    return job.status;
  }
  if (["completed", "failed", "cancelled"].includes(task.status || "")) return task.status!;
  return liveStatus || task.status || "draft";
}

export function isGenerationLifecycleEvent(event: string): boolean {
  return /^(task[._](queued|started|completed|failed|cancelled)|job\.(started|retrying|completed|failed|cancelled|uncertain))$/.test(event);
}

export type SceneAssetRefreshAction = "online_material" | "workflow_unit" | "none";

export function resolveSceneAssetRefreshAction(
  contentMode: string | undefined,
  hasOnlineMaterialHandler: boolean,
  hasRetryUnit: boolean,
  hasSceneId: boolean,
): SceneAssetRefreshAction {
  if (contentMode === "online_asset" && hasOnlineMaterialHandler) return "online_material";
  if (hasRetryUnit && hasSceneId) return "workflow_unit";
  return "none";
}
