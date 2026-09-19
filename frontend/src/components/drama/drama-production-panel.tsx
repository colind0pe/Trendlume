"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AudioLines,
  Check,
  CheckCircle2,
  CircleAlert,
  Film,
  Image,
  Loader2,
  Play,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
  Video,
} from "lucide-react";

import { api } from "@/lib/api-client";
import type {
  DramaDetail,
  DramaProductionFinding,
  DramaProductionStage,
  DramaProductionStatus,
  DramaShot,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/field";
import { SectionHeader } from "@/components/ui/page-shell";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";

const ACTIVE_STATUSES = new Set(["queued", "pending", "running", "retrying", "in_progress"]);

const STATUS_LABELS: Record<string, string> = {
  draft: "未开始",
  queued: "排队中",
  pending: "等待执行",
  running: "生成中",
  retrying: "重试中",
  in_progress: "进行中",
  completed: "已完成",
  completed_with_warning: "完成·有提示",
  reused: "已复用",
  skipped: "已跳过",
  failed: "失败",
};

function statusTone(status: string): StatusTone {
  if (["completed", "completed_with_warning", "reused", "skipped"].includes(status)) return "success";
  if (["failed", "cancelled"].includes(status)) return "destructive";
  if (["running", "retrying", "queued", "pending", "in_progress"].includes(status)) return "primary";
  return "neutral";
}

function StatusPill({ status }: { status: string }) {
  return <StatusBadge label={STATUS_LABELS[status] || status} tone={statusTone(status)} />;
}

function FindingList({ findings, title }: { findings: DramaProductionFinding[]; title: string }) {
  const visible = findings.filter((finding) => !finding.passed || finding.severity !== "info");
  if (!visible.length) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-success/25 bg-success/[0.04] px-3 py-2.5 text-xs text-foreground">
        <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
        <span>{title}：已通过</span>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      <div className="grid gap-2 md:grid-cols-2">
        {visible.map((finding, index) => (
          <div
            key={`${finding.key}-${finding.shot_id || "episode"}-${index}`}
            role={finding.severity === "blocking" && !finding.passed ? "alert" : undefined}
            className={`flex gap-2 rounded-xl border px-3 py-2.5 text-xs ${
              !finding.passed
                ? finding.severity === "blocking"
                  ? "border-destructive/30 bg-destructive/[0.04]"
                  : "border-warning/30 bg-warning/[0.04]"
                : "border-border/60 bg-secondary/20"
            }`}
          >
            {!finding.passed ? (
              <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden="true" />
            ) : (
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" aria-hidden="true" />
            )}
            <span className="min-w-0 leading-5">
              <span className="font-medium text-foreground">{finding.label}</span>
              <span className="block text-muted-foreground">{finding.message}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function stageForShot(shot: { media_status: string; audio_status: string; composition_status: string }): DramaProductionStage {
  if (shot.media_status === "failed") return "media";
  if (shot.audio_status === "failed") return "audio";
  return "composition";
}

function ShotProductionCard({
  shot,
  productionShot,
  onRetry,
  retrying,
}: {
  shot: DramaShot | undefined;
  productionShot: DramaProductionStatus["shots"][number];
  onRetry: (shotId: string, stage: DramaProductionStage) => void;
  retrying: boolean;
}) {
  const timeline = productionShot.dialogue_timeline || [];
  const retryStage = stageForShot(productionShot);
  const isFailed = productionShot.status === "failed" || Boolean(productionShot.error_message);

  return (
    <Card className={`rounded-2xl ${isFailed ? "border-destructive/30" : productionShot.status === "completed" ? "border-success/25" : ""}`}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-primary">
              <Film className="h-3 w-3" aria-hidden="true" />
              Shot {String(productionShot.sequence_index).padStart(2, "0")}
              {shot?.approval_status === "approved" && <Badge variant="outline" className="font-sans normal-case tracking-normal">Approved</Badge>}
            </div>
            <CardTitle className="text-sm">{shot?.action || productionShot.source_shot_id}</CardTitle>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusPill status={productionShot.status} />
            {isFailed && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={retrying}
                onClick={() => onRetry(productionShot.source_shot_id, retryStage)}
              >
                {retrying ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />}
                {retrying ? "重试中…" : `重试${retryStage === "media" ? "画面" : retryStage === "audio" ? "音频" : "合成"}`}
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="rounded-xl bg-secondary/30 p-3"><p className="text-[11px] text-muted-foreground">Media</p><div className="mt-1 flex items-center gap-1.5"><Image className="h-3.5 w-3.5 text-primary" aria-hidden="true" /><StatusPill status={productionShot.media_status} /></div></div>
          <div className="rounded-xl bg-secondary/30 p-3"><p className="text-[11px] text-muted-foreground">Audio</p><div className="mt-1 flex items-center gap-1.5"><AudioLines className="h-3.5 w-3.5 text-primary" aria-hidden="true" /><StatusPill status={productionShot.audio_status} /></div></div>
          <div className="rounded-xl bg-secondary/30 p-3"><p className="text-[11px] text-muted-foreground">Segment</p><div className="mt-1 flex items-center gap-1.5"><Video className="h-3.5 w-3.5 text-primary" aria-hidden="true" /><StatusPill status={productionShot.composition_status} /></div></div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{productionShot.dialogue_line_count} 条 DialogueLine</span>
          {productionShot.duration_seconds != null && <span>{productionShot.duration_seconds.toFixed(1)}s 实际时长</span>}
          {productionShot.media_asset_id && <span className="font-mono">media: {productionShot.media_asset_id}</span>}
          {productionShot.audio_asset_id && <span className="font-mono">audio: {productionShot.audio_asset_id}</span>}
        </div>
        {productionShot.error_message && <p role="alert" className="rounded-lg border border-destructive/25 bg-destructive/[0.04] px-3 py-2 text-xs leading-5 text-destructive">{productionShot.error_message}</p>}
        {timeline.length > 0 && (
          <div className="rounded-xl border border-border/60 bg-card/40 p-3">
            <div className="mb-2 flex items-center justify-between gap-3"><p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">真实对白 timing</p><span className="text-[11px] text-muted-foreground">{timeline.length} 段</span></div>
            <div className="space-y-1.5">
              {timeline.map((line) => <div key={String(line.id)} className="flex gap-2 text-xs leading-5"><span className="shrink-0 font-mono text-muted-foreground">{Number(line.start || 0).toFixed(1)}–{Number(line.end || 0).toFixed(1)}s</span><span className="font-medium text-foreground">{String(line.speaker_name || "旁白")}</span><span className="min-w-0 text-muted-foreground">{String(line.text || "")}</span></div>)}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function DramaProductionPanel({ detail }: { detail: DramaDetail }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const approvedEpisodes = detail.episodes.filter((episode) => episode.approval_status === "approved");
  const [episodeId, setEpisodeId] = React.useState(approvedEpisodes[0]?.id || detail.episodes[0]?.id || "");
  const [visualMode, setVisualMode] = React.useState<"image" | "video">("image");
  const [retryingShot, setRetryingShot] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!episodeId || !detail.episodes.some((episode) => episode.id === episodeId)) {
      setEpisodeId(approvedEpisodes[0]?.id || detail.episodes[0]?.id || "");
    }
  }, [approvedEpisodes, detail.episodes, episodeId]);

  const productionQuery = useQuery({
    queryKey: ["drama-production", detail.id, episodeId],
    queryFn: () => api.getDramaProduction(detail.id, episodeId),
    enabled: detail.approval_status === "approved" && Boolean(episodeId),
    refetchInterval: (query) => (ACTIVE_STATUSES.has(query.state.data?.status || "") ? 2500 : false),
  });

  const updateStatus = React.useCallback((next: DramaProductionStatus) => {
    queryClient.setQueryData(["drama-production", detail.id, next.episode_id], next);
  }, [detail.id, queryClient]);

  const startMutation = useMutation({
    mutationFn: () => api.startDramaProduction(detail.id, { episode_id: episodeId, visual_mode: visualMode }),
    onSuccess: (next) => { updateStatus(next); toast("Episode production 已启动，状态会按 Shot 更新。", "success"); },
    onError: (error: Error) => toast(`启动制作失败：${error.message}`, "error"),
  });
  const resumeMutation = useMutation({
    mutationFn: () => api.resumeDramaProduction(detail.id),
    onSuccess: (next) => { updateStatus(next); toast("已恢复 Episode production。", "success"); },
    onError: (error: Error) => toast(`恢复制作失败：${error.message}`, "error"),
  });
  const retryMutation = useMutation({
    mutationFn: ({ shotId, stage }: { shotId: string; stage: DramaProductionStage }) => api.retryDramaShot(detail.id, shotId, stage),
    onSuccess: (next) => { setRetryingShot(null); updateStatus(next); toast("已提交单 Shot retry，成功的 Shot 不会重做。", "success"); },
    onError: (error: Error) => { setRetryingShot(null); toast(`Shot retry 失败：${error.message}`, "error"); },
  });

  const status = productionQuery.data;
  const selectedEpisode = detail.episodes.find((episode) => episode.id === episodeId);
  const sourceShots = selectedEpisode?.scenes.flatMap((scene) => scene.shots) || [];
  const sourceById = new Map(sourceShots.map((shot) => [shot.id, shot]));
  const busy = ACTIVE_STATUSES.has(status?.status || "") || startMutation.isPending || resumeMutation.isPending;
  const canStart = detail.approval_status === "approved" && approvedEpisodes.some((episode) => episode.id === episodeId);

  if (detail.approval_status !== "approved") {
    return (
      <Card className="rounded-2xl border-warning/25 bg-warning/[0.035]">
        <CardContent className="flex gap-3 p-5">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
          <div><h2 className="text-base font-semibold text-foreground">Production 尚未解锁</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">请先完成并批准 Storyboard。只有 approved Shot 会进入 Media → Audio → Episode Video。</p></div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="rounded-2xl border-primary/25 bg-primary/[0.035]">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2"><Film className="h-5 w-5 text-primary" aria-hidden="true" /><CardTitle>Episode production</CardTitle></div>
              <CardDescription className="mt-1 max-w-2xl">Approved Storyboard 进入现有 Render Scene；每个 Shot 独立生成媒体、对白音频和 segment，最后再合成 Episode。</CardDescription>
            </div>
            {status && <StatusPill status={status.status} />}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_180px]">
            <Field label="Episode" htmlFor="drama-production-episode" description={approvedEpisodes.length ? "只显示已批准的 Episode。" : "没有已批准 Episode。"}>
              <Select id="drama-production-episode" value={episodeId} onChange={(event) => setEpisodeId(event.target.value)} disabled={busy || !approvedEpisodes.length}>
                {approvedEpisodes.map((episode) => <option key={episode.id} value={episode.id}>EP {String(episode.episode_number).padStart(2, "0")} · {episode.title}</option>)}
              </Select>
            </Field>
            <Field label="画面来源" htmlFor="drama-production-visual-mode" description="复用当前 Image / Video Provider。">
              <Select id="drama-production-visual-mode" value={visualMode} onChange={(event) => setVisualMode(event.target.value as "image" | "video")} disabled={busy}>
                <option value="image">Image → clip</option>
                <option value="video">Video Provider</option>
              </Select>
            </Field>
            <div className="flex items-end">
              {status?.status === "failed" && status.task_id ? (
                <Button type="button" variant="outline" className="w-full gap-2" disabled={resumeMutation.isPending} onClick={() => resumeMutation.mutate()}>{resumeMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCcw className="h-4 w-4" aria-hidden="true" />}恢复 Episode</Button>
              ) : (
                <Button type="button" className="w-full gap-2" disabled={!canStart || busy} onClick={() => startMutation.mutate()}>{startMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}{status?.task_id ? "重新运行未完成部分" : "开始 Episode production"}</Button>
              )}
            </div>
          </div>
          {productionQuery.isError && <p role="alert" className="rounded-lg border border-destructive/25 bg-destructive/[0.04] px-3 py-2 text-xs text-destructive">无法读取 production 状态：{(productionQuery.error as Error).message}。可以稍后刷新或重新启动 Episode。</p>}
          {status && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span>Pipeline stage：<span className="font-medium text-foreground">{status.current_stage || "等待开始"}</span></span><span>{status.progress}% · {status.shots.filter((shot) => shot.status === "completed").length}/{status.shots.length} Shot 完成</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-label="Episode production progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={status.progress}><div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${Math.max(0, Math.min(100, status.progress))}%` }} /></div>
              <FindingList findings={status.qa_before} title="生成前 QA" />
              {status.qa_after.length > 0 && <FindingList findings={status.qa_after} title="生成后 QA" />}
            </div>
          )}
        </CardContent>
      </Card>

      {status?.final_video_url && (
        <Card className="rounded-2xl border-success/25">
          <CardHeader className="pb-3"><div className="flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-success" aria-hidden="true" /><CardTitle>Episode final preview</CardTitle></div><CardDescription>{status.total_duration_seconds ? `${status.total_duration_seconds.toFixed(1)}s · ` : ""}逐 Shot compose 后 concatenate 的最终视频。</CardDescription></CardHeader>
          <CardContent><video controls preload="metadata" className="aspect-video w-full rounded-xl bg-black" src={status.final_video_url} aria-label="Episode final preview" /></CardContent>
        </Card>
      )}

      <div className="space-y-3">
        <SectionHeader title="逐 Shot production" description="失败 Shot 可单独 retry；已完成的 Shot 会通过 durable fingerprint/cache 复用。" actions={<Badge variant="outline">{status?.shots.length || sourceShots.length} shots</Badge>} />
        {!status && productionQuery.isLoading && <div className="flex items-center gap-2 rounded-xl border border-border/60 px-4 py-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />正在读取 Shot 状态…</div>}
        {!status && !productionQuery.isLoading && <Card className="rounded-2xl"><CardContent className="p-5 text-sm text-muted-foreground">选择一个已批准 Episode，点击“开始 Episode production”后这里会显示每个 Shot 的 Media、Audio、segment 和 QA。</CardContent></Card>}
        {status?.shots.map((productionShot) => <ShotProductionCard key={productionShot.shot_id} shot={sourceById.get(productionShot.source_shot_id)} productionShot={productionShot} retrying={retryingShot === productionShot.source_shot_id || retryMutation.isPending} onRetry={(shotId, stage) => { setRetryingShot(shotId); retryMutation.mutate({ shotId, stage }); }} />)}
      </div>
    </div>
  );
}
