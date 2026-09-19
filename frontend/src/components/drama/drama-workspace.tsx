"use client";

import Link from "next/link";
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Clapperboard,
  FileText,
  Film,
  LockKeyhole,
  MapPin,
  RefreshCcw,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";

import { api } from "@/lib/api-client";
import { DramaProductionPanel } from "@/components/drama/drama-production-panel";
import type {
  DramaApprovalStatus,
  DramaDetail,
  DramaEpisode,
  DramaShot,
  DramaStage,
  Project,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader, SectionHeader } from "@/components/ui/page-shell";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";

const STAGES: Array<{ key: DramaStage; label: string; description: string }> = [
  { key: "story", label: "故事", description: "想法或已有剧本" },
  { key: "bible", label: "Bible", description: "叙事和视觉规则" },
  { key: "assets", label: "角色 / 场景", description: "稳定身份资产" },
  { key: "episode", label: "单集", description: "剧本与场次" },
  { key: "storyboard", label: "Storyboard", description: "逐 Shot 计划" },
  { key: "approval", label: "Approved", description: "进入后续制作" },
];

const approvalLabel: Record<DramaApprovalStatus, string> = {
  draft: "草稿",
  in_review: "待确认",
  approved: "已确认",
  changes_requested: "需重新确认",
};

const approvalTone: Record<DramaApprovalStatus, StatusTone> = {
  draft: "neutral",
  in_review: "warning",
  approved: "success",
  changes_requested: "destructive",
};

function ApprovalBadge({ status }: { status: DramaApprovalStatus }) {
  return <StatusBadge label={approvalLabel[status]} tone={approvalTone[status]} />;
}

function StageRail({ detail }: { detail?: DramaDetail }) {
  return (
    <Card className="h-fit overflow-hidden rounded-2xl">
      <CardHeader className="border-b border-border/60 bg-secondary/20 pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm">制作检查点</CardTitle>
          <Badge variant="outline" className="font-mono text-[10px]">PRE-PROD</Badge>
        </div>
        <CardDescription>每一步都可暂停，确认后才会解锁下一步。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-1.5 p-3">
        {STAGES.map((stage, index) => {
          const state = detail?.stage_state?.[stage.key];
          const isCurrent = detail?.current_stage === stage.key;
          const isComplete = state?.status === "completed";
          return (
            <div
              key={stage.key}
              aria-current={isCurrent ? "step" : undefined}
              className={`relative flex gap-3 rounded-xl px-3 py-3 transition-colors ${
                isCurrent ? "border border-primary/30 bg-primary/[0.08]" : "border border-transparent"
              }`}
            >
              {index < STAGES.length - 1 && (
                <span
                  aria-hidden="true"
                  className={`absolute left-[20px] top-[35px] h-[calc(100%-18px)] w-px ${
                    isComplete ? "bg-success/50" : "bg-border/80"
                  }`}
                />
              )}
              <span
                className={`relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-bold ${
                  isComplete
                    ? "border-success/50 bg-success/15 text-success"
                    : isCurrent
                      ? "border-primary/50 bg-primary text-primary-foreground"
                      : "border-border bg-card text-muted-foreground"
                }`}
              >
                {isComplete ? <Check className="h-3 w-3" aria-hidden="true" /> : index + 1}
              </span>
              <span className="min-w-0">
                <span className={`block text-xs font-semibold ${isCurrent ? "text-primary" : "text-foreground"}`}>
                  {stage.label}
                </span>
                <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground">
                  {state?.message || stage.description}
                </span>
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function IntakePanel({
  project,
  onCreated,
}: {
  project: Project;
  onCreated: (detail: DramaDetail) => void;
}) {
  const { toast } = useToast();
  const [sourceType, setSourceType] = React.useState<"idea" | "script">("idea");
  const [title, setTitle] = React.useState("");
  const [sourceText, setSourceText] = React.useState("");
  const [genre, setGenre] = React.useState("都市情感");
  const [tone, setTone] = React.useState("克制、温暖、有悬念");
  const [visualStyle, setVisualStyle] = React.useState("电影写实摄影；稳定光线、自然材质、低饱和色彩");

  const createMutation = useMutation({
    mutationFn: async () => {
      const draft = await api.createDrama(project.id, {
        source_type: sourceType,
        title: title.trim() || (sourceType === "idea" ? sourceText.trim().slice(0, 30) : "未命名短剧"),
        source_text: sourceText.trim(),
        genre,
        tone,
        visual_style: visualStyle,
      });
      return api.planDrama(draft.id);
    },
    onSuccess: (detail) => {
      onCreated(detail);
      toast("已生成可审阅的前期规划；当前不会生成任何媒体。", "success");
    },
    onError: (error: Error) => toast(`创建失败：${error.message}`, "error"),
  });

  const canSubmit = Boolean(sourceText.trim()) && !createMutation.isPending;

  return (
    <Card className="overflow-hidden rounded-2xl">
      <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="border-b border-border/60 bg-[linear-gradient(145deg,hsl(var(--primary)/0.13),transparent_55%)] p-6 lg:border-b-0 lg:border-r">
          <Badge variant="default" className="mb-4 gap-1.5"><Sparkles className="h-3 w-3" aria-hidden="true" /> 前期制片台</Badge>
          <h2 className="max-w-md text-2xl font-bold leading-tight tracking-tight text-foreground sm:text-3xl">
            先把故事拍摄清楚，<span className="text-primary">再谈生成。</span>
          </h2>
          <p className="mt-4 max-w-md text-sm leading-7 text-muted-foreground">
            从一句想法或已有剧本，整理出 Drama Bible、角色锁、场景锁、单集剧本和逐 Shot Storyboard。每一层都可以停下来人工确认。
          </p>
          <div className="mt-8 grid gap-2 text-xs text-muted-foreground">
            {[
              ["01", "双入口", "idea 或 screenplay"],
              ["02", "一致性", "appearance / wardrobe / visual lock"],
              ["03", "审批闸门", "Approved Storyboard 之前不进媒体生成"],
            ].map(([index, label, text]) => (
              <div key={index} className="flex items-center gap-3 rounded-lg border border-border/60 bg-card/50 px-3 py-2.5">
                <span className="font-mono text-[10px] text-primary">{index}</span>
                <span className="font-semibold text-foreground">{label}</span>
                <span className="truncate">{text}</span>
              </div>
            ))}
          </div>
        </div>
        <form
          className="space-y-5 p-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit) createMutation.mutate();
          }}
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-foreground">开始一个 Drama Bible</h3>
              <p className="mt-1 text-xs text-muted-foreground">当前项目：{project.name}</p>
            </div>
            <Badge variant="outline" className="font-mono text-[10px]">{project.aspect_ratio}</Badge>
          </div>

          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="故事输入类型">
            {[
              { value: "idea" as const, label: "故事想法", hint: "生成一集可编辑草案" },
              { value: "script" as const, label: "已有剧本", hint: "按字段解析为分镜" },
            ].map((item) => (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={sourceType === item.value}
                onClick={() => setSourceType(item.value)}
                className={`rounded-xl border px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  sourceType === item.value ? "border-primary/60 bg-primary/10" : "border-border/70 bg-card/40 hover:bg-secondary/50"
                }`}
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  {item.value === "idea" ? <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" /> : <FileText className="h-4 w-4 text-primary" aria-hidden="true" />}
                  {item.label}
                </span>
                <span className="mt-1 block text-[11px] text-muted-foreground">{item.hint}</span>
              </button>
            ))}
          </div>

          <Field label="项目标题" htmlFor="drama-title" description="可在生成后继续修改。">
            <Input id="drama-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：夜班之后" />
          </Field>
          <Field
            label={sourceType === "idea" ? "故事想法" : "剧本原文"}
            htmlFor="drama-source"
            required
            description={sourceType === "script" ? "支持标题、角色、分镜、场景、台词、景别和运镜等 key: value 字段。" : "先用一句话写清楚人物、冲突和想要的情绪落点。"}
          >
            <Textarea
              id="drama-source"
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
              placeholder={sourceType === "idea" ? "一个夜班程序员在关灯前决定重新拿起画笔……" : "# 标题：\n## 角色\n- 林夏 | ……\n## 分镜\n### 镜头一\n场景：……"}
              className="min-h-36"
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="题材" htmlFor="drama-genre"><Input id="drama-genre" value={genre} onChange={(event) => setGenre(event.target.value)} /></Field>
            <Field label="基调" htmlFor="drama-tone"><Input id="drama-tone" value={tone} onChange={(event) => setTone(event.target.value)} /></Field>
          </div>
          <Field label="视觉语言" htmlFor="drama-style" description="会进入所有角色、场景和 Shot 的 deterministic anchor。">
            <Textarea id="drama-style" value={visualStyle} onChange={(event) => setVisualStyle(event.target.value)} className="min-h-20" />
          </Field>
          <div className="flex flex-col gap-3 border-t border-border/60 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="max-w-md text-xs leading-5 text-muted-foreground">文本规划不调用图像、视频、TTS 或渲染 Provider。</p>
            <Button type="submit" disabled={!canSubmit} className="gap-2">
              <Clapperboard className="h-4 w-4" aria-hidden="true" />
              {createMutation.isPending ? "正在整理…" : "生成前期规划"}
            </Button>
          </div>
        </form>
      </div>
    </Card>
  );
}

function ApprovalAction({
  status,
  pending,
  onApprove,
  label = "确认",
  disabled = false,
}: {
  status: DramaApprovalStatus;
  pending: boolean;
  onApprove: () => void;
  label?: string;
  disabled?: boolean;
}) {
  if (status === "approved") return <ApprovalBadge status={status} />;
  return (
    <Button type="button" size="sm" variant="outline" className="gap-1.5" disabled={disabled || pending} onClick={onApprove}>
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
      {pending ? "保存中…" : label}
    </Button>
  );
}

function BiblePanel({ detail }: { detail: DramaDetail }) {
  return (
    <div className="space-y-4">
      <Card className="rounded-2xl border-primary/20 bg-primary/[0.035]">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-primary">
                <LockKeyhole className="h-3.5 w-3.5" aria-hidden="true" /> Drama Bible
              </div>
              <CardTitle className="text-xl">{detail.title}</CardTitle>
              <CardDescription className="mt-1">{detail.logline}</CardDescription>
            </div>
            <div className="flex items-center gap-2"><Badge variant="outline">{detail.source_type === "idea" ? "故事想法" : "已有剧本"}</Badge><ApprovalBadge status={detail.approval_status} /></div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 border-t border-border/50 pt-4 md:grid-cols-3">
          <div><p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">题材 / 基调</p><p className="mt-1 text-sm text-foreground">{detail.genre || "未设定"} · {detail.tone || "未设定"}</p></div>
          <div><p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">视觉语言</p><p className="mt-1 text-sm leading-5 text-foreground">{detail.visual_style || "未设定"}</p></div>
          <div><p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">断点</p><p className="mt-1 font-mono text-xs text-foreground">{detail.checkpoint?.resume_stage || "等待规划"} · revision {detail.revision}</p></div>
        </CardContent>
      </Card>
      <Card className="rounded-2xl">
        <CardHeader className="pb-3"><CardTitle className="text-sm">输入原文</CardTitle><CardDescription>保留原始素材，结构化结果始终可以回溯。</CardDescription></CardHeader>
        <CardContent><pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-border/60 bg-secondary/25 p-4 text-xs leading-6 text-muted-foreground">{detail.source_text}</pre></CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="rounded-2xl"><CardHeader className="pb-3"><CardTitle className="text-sm">连续性规则</CardTitle><CardDescription>时间、空间、视线、服装和道具的稳定约束。</CardDescription></CardHeader><CardContent>{detail.continuity_rules.length ? <ul className="space-y-2 text-sm text-foreground">{detail.continuity_rules.map((rule, index) => <li key={index} className="rounded-lg bg-secondary/40 px-3 py-2">{String(rule.rule || rule.text || JSON.stringify(rule))}</li>)}</ul> : <p className="text-sm text-muted-foreground">暂未填写。可在确认前补充本集的硬规则。</p>}</CardContent></Card>
        <Card className="rounded-2xl"><CardHeader className="pb-3"><CardTitle className="text-sm">道具锁</CardTitle><CardDescription>不单独生成 Prop 表，先把稳定道具作为 Bible 级连续性资产。</CardDescription></CardHeader><CardContent>{detail.prop_locks.length ? <ul className="space-y-2 text-sm text-foreground">{detail.prop_locks.map((lock, index) => <li key={index} className="rounded-lg bg-secondary/40 px-3 py-2">{String(lock.name || lock.text || JSON.stringify(lock))}</li>)}</ul> : <p className="text-sm text-muted-foreground">暂无道具锁。镜头中的道具会保存在 Shot continuity metadata。</p>}</CardContent></Card>
      </div>
    </div>
  );
}

function CharactersPanel({ detail, onRefresh }: { detail: DramaDetail; onRefresh: (detail: DramaDetail) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (characterId: string) => api.approveDramaCharacter(detail.id, characterId),
    onSuccess: (next) => { queryClient.setQueryData(["drama", detail.id], next); onRefresh(next); toast("角色锁已确认，相关 Shot anchor 已刷新。", "success"); },
    onError: (error: Error) => toast(`角色确认失败：${error.message}`, "error"),
  });
  return (
    <div className="space-y-4">
      <SectionHeader title="Characters" description="确认外观、服装和声音身份后，角色才可以进入 Shot。" actions={<Badge variant="outline">{detail.characters.length} 个角色</Badge>} />
      <div className="grid gap-4 md:grid-cols-2">
        {detail.characters.map((character) => (
          <Card key={character.id} className={`rounded-2xl ${character.approval_status === "approved" ? "border-success/25" : ""}`}>
            <CardHeader className="pb-3"><div className="flex items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2 text-base"><Users className="h-4 w-4 text-primary" aria-hidden="true" />{character.name}</CardTitle><CardDescription className="mt-1">{character.description}</CardDescription></div><ApprovalBadge status={character.approval_status} /></div></CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid gap-2 rounded-xl bg-secondary/35 p-3"><div><span className="text-xs text-muted-foreground">Appearance lock</span><p className="mt-1 leading-5 text-foreground">{character.appearance_lock}</p></div><div><span className="text-xs text-muted-foreground">Wardrobe</span><p className="mt-1 leading-5 text-foreground">{character.wardrobe}</p></div></div>
              <div className="flex items-center justify-between gap-3 border-t border-border/50 pt-3"><span className="max-w-[65%] truncate font-mono text-[10px] text-muted-foreground" title={character.prompt_anchor}>{character.prompt_anchor}</span><ApprovalAction status={character.approval_status} pending={mutation.isPending && mutation.variables === character.id} onApprove={() => mutation.mutate(character.id)} label="确认角色锁" /></div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function LocationsPanel({ detail, onRefresh }: { detail: DramaDetail; onRefresh: (detail: DramaDetail) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (locationId: string) => api.approveDramaLocation(detail.id, locationId),
    onSuccess: (next) => { queryClient.setQueryData(["drama", detail.id], next); onRefresh(next); toast("场景锁已确认，相关 Shot anchor 已刷新。", "success"); },
    onError: (error: Error) => toast(`场景确认失败：${error.message}`, "error"),
  });
  return (
    <div className="space-y-4">
      <SectionHeader title="Locations" description="稳定视觉描述和参考资产属于场景锁，不与最终 Render Segment 混在一起。" actions={<Badge variant="outline">{detail.locations.length} 个场景</Badge>} />
      <div className="grid gap-4 md:grid-cols-2">
        {detail.locations.map((location) => (
          <Card key={location.id} className={`rounded-2xl ${location.approval_status === "approved" ? "border-success/25" : ""}`}>
            <CardHeader className="pb-3"><div className="flex items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2 text-base"><MapPin className="h-4 w-4 text-primary" aria-hidden="true" />{location.name}</CardTitle><CardDescription className="mt-1">{location.visual_description}</CardDescription></div><ApprovalBadge status={location.approval_status} /></div></CardHeader>
            <CardContent className="space-y-3"><div className="rounded-xl bg-secondary/35 p-3 text-sm leading-6 text-foreground">{location.visual_description}</div><div className="flex items-center justify-between gap-3 border-t border-border/50 pt-3"><span className="font-mono text-[10px] text-muted-foreground">{location.reference_asset_ids.length ? `${location.reference_asset_ids.length} 个参考资产` : "暂无参考资产"}</span><ApprovalAction status={location.approval_status} pending={mutation.isPending && mutation.variables === location.id} onApprove={() => mutation.mutate(location.id)} label="确认场景锁" /></div></CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function EpisodeCard({ detail, episode, onRefresh }: { detail: DramaDetail; episode: DramaEpisode; onRefresh: (detail: DramaDetail) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const episodeMutation = useMutation({
    mutationFn: () => api.approveDramaEpisode(detail.id, episode.id),
    onSuccess: (next) => { queryClient.setQueryData(["drama", detail.id], next); onRefresh(next); toast("单集剧本已确认。", "success"); },
    onError: (error: Error) => toast(`单集确认失败：${error.message}`, "error"),
  });
  const sceneMutation = useMutation({
    mutationFn: (sceneId: string) => api.approveDramaScene(detail.id, sceneId),
    onSuccess: (next) => { queryClient.setQueryData(["drama", detail.id], next); onRefresh(next); toast("场景结构已确认。", "success"); },
    onError: (error: Error) => toast(`场景确认失败：${error.message}`, "error"),
  });
  const assetsApproved = detail.characters.length > 0
    && detail.locations.length > 0
    && [...detail.characters, ...detail.locations].every((entity) => entity.approval_status === "approved");
  return (
    <Card className="rounded-2xl">
      <CardHeader className="pb-3"><div className="flex items-start justify-between gap-3"><div><div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-primary">EP {String(episode.episode_number).padStart(2, "0")}</div><CardTitle className="text-base">{episode.title}</CardTitle><CardDescription className="mt-1">{episode.synopsis}</CardDescription></div><ApprovalAction status={episode.approval_status} pending={episodeMutation.isPending} disabled={!assetsApproved} onApprove={() => episodeMutation.mutate()} label={assetsApproved ? "确认单集剧本" : "先确认角色与场景"} /></div></CardHeader>
      <CardContent className="space-y-4"><div className="rounded-xl border border-border/60 bg-secondary/20 p-3"><p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">单集剧本</p><pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs leading-6 text-foreground">{episode.script_text}</pre></div><div className="space-y-2"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-foreground">Scenes</span><span className="text-xs text-muted-foreground">{episode.scenes.length} 场</span></div>{episode.scenes.map((scene) => { const sceneLocationApproved = Boolean(scene.location_id && detail.locations.some((location) => location.id === scene.location_id && location.approval_status === "approved")); return <div key={scene.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-3 py-2.5"><div className="min-w-0"><p className="truncate text-sm font-medium text-foreground">{scene.sequence_index}. {scene.title}</p><p className="mt-0.5 truncate text-xs text-muted-foreground">{scene.summary}</p></div><div className="flex shrink-0 items-center gap-2"><span className="font-mono text-[10px] text-muted-foreground">{scene.shots.length} shots</span><ApprovalAction status={scene.approval_status} pending={sceneMutation.isPending && sceneMutation.variables === scene.id} disabled={episode.approval_status !== "approved" || !sceneLocationApproved} onApprove={() => sceneMutation.mutate(scene.id)} label={episode.approval_status !== "approved" ? "先确认单集" : sceneLocationApproved ? "确认场景" : "先确认场景锁"} /></div></div>; })}</div></CardContent>
    </Card>
  );
}

function StoryboardShot({ detail, shot, blocked = false, onRefresh }: { detail: DramaDetail; shot: DramaShot; blocked?: boolean; onRefresh: (detail: DramaDetail) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => api.approveDramaShot(detail.id, shot.id),
    onSuccess: (next) => { queryClient.setQueryData(["drama", detail.id], next); onRefresh(next); toast("Shot 已确认。", "success"); },
    onError: (error: Error) => toast(`Shot 确认失败：${error.message}`, "error"),
  });
  return (
    <Card className={`rounded-2xl ${shot.approval_status === "approved" ? "border-success/25" : ""}`}>
      <CardHeader className="pb-3"><div className="flex items-start justify-between gap-3"><div><div className="mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-primary"><Film className="h-3 w-3" aria-hidden="true" /> Shot {String(shot.sequence_index).padStart(2, "0")}</div><CardTitle className="text-sm">{shot.action}</CardTitle></div><ApprovalAction status={shot.approval_status} pending={mutation.isPending} disabled={blocked} onApprove={() => mutation.mutate()} label={blocked ? "先确认场景" : "确认 Shot"} /></div></CardHeader>
      <CardContent className="space-y-3 text-sm"><div className="grid gap-3 md:grid-cols-2"><div className="rounded-xl bg-secondary/35 p-3"><p className="text-[11px] text-muted-foreground">画面提示</p><p className="mt-1 leading-6 text-foreground">{shot.visual_prompt}</p></div><div className="rounded-xl bg-secondary/35 p-3"><p className="text-[11px] text-muted-foreground">镜头语言</p><p className="mt-1 leading-6 text-foreground">{shot.camera} · {shot.framing} · {shot.movement}</p><p className="mt-1 font-mono text-xs text-muted-foreground">约 {shot.duration_hint.toFixed(1)}s</p></div></div>{shot.dialogue && <div className="border-l-2 border-primary/40 pl-3 text-sm leading-6 text-foreground">“{shot.dialogue}”</div>}<div className="flex flex-wrap items-center gap-2 border-t border-border/50 pt-3"><span className="text-[11px] text-muted-foreground">continuity</span>{Object.entries(shot.continuity_metadata || {}).filter(([, value]) => value).map(([key, value]) => <Badge key={key} variant="secondary" className="font-mono text-[10px]">{key}: {String(value)}</Badge>)}<span className="ml-auto max-w-full truncate font-mono text-[10px] text-muted-foreground" title={shot.prompt_anchor}>{shot.prompt_anchor}</span></div></CardContent>
    </Card>
  );
}

function StoryboardPanel({ detail, onRefresh }: { detail: DramaDetail; onRefresh: (detail: DramaDetail) => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const preflightQuery = useQuery({ queryKey: ["drama-preflight", detail.id], queryFn: () => api.getDramaPreflight(detail.id), staleTime: 0 });
  const approvalMutation = useMutation({
    mutationFn: () => api.approveDramaStoryboard(detail.id),
    onSuccess: (result) => { queryClient.setQueryData(["drama", detail.id], result.drama); queryClient.setQueryData(["drama-preflight", detail.id], result.preflight); onRefresh(result.drama); toast("Storyboard 已批准。Production tab 已解锁，开始后会按 Shot 生成媒体和音频。", "success"); },
    onError: (error: Error) => toast(`批准失败：${error.message}`, "error"),
  });
  const preflight = preflightQuery.data;
  const shots = detail.episodes.flatMap((episode) => episode.scenes.flatMap((scene) => scene.shots));
  return (
    <div className="space-y-4">
      <Card className="rounded-2xl border-primary/25 bg-primary/[0.035]"><CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between"><div><div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" /><h2 className="text-base font-semibold text-foreground">Storyboard approval gate</h2></div><p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">只有角色、场景、Shot 字段和逐 Shot 确认都完成，才会写入 Approved Storyboard。批准只解锁后续 Production，不会自动开始媒体生成。</p></div><Button type="button" className="shrink-0 gap-2" disabled={!preflight?.ready || approvalMutation.isPending || detail.approval_status === "approved"} onClick={() => approvalMutation.mutate()}><ShieldCheck className="h-4 w-4" aria-hidden="true" />{detail.approval_status === "approved" ? "已批准" : approvalMutation.isPending ? "检查中…" : "批准 Storyboard"}</Button></CardContent></Card>
      {preflight && !preflight.ready && <Card className="rounded-2xl border-warning/25 bg-warning/[0.035]"><CardContent className="grid gap-2 p-4 sm:grid-cols-3">{preflight.checks.map((check) => <div key={check.key} className="flex gap-2 text-xs"><span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${check.passed ? "bg-success" : "bg-warning"}`} aria-hidden="true" /><span><span className="font-semibold text-foreground">{check.label}</span><span className="mt-0.5 block leading-5 text-muted-foreground">{check.message}</span></span></div>)}</CardContent></Card>}
      <SectionHeader title="逐 Shot review" description={`${shots.filter((shot) => shot.approval_status === "approved").length} / ${shots.length} 已确认 · anchor 是确定性的，不依赖新增 Provider`} actions={<Badge variant="outline">{detail.episodes.length} 集</Badge>} />
      <div className="space-y-4">{detail.episodes.map((episode) => <div key={episode.id} className="space-y-3"><div className="flex items-center gap-2"><span className="font-mono text-xs text-primary">EP {String(episode.episode_number).padStart(2, "0")}</span><span className="text-sm font-semibold text-foreground">{episode.title}</span><ApprovalBadge status={episode.approval_status} /></div>{episode.scenes.map((scene) => <div key={scene.id} className="space-y-2 pl-0 sm:pl-4"><div className="flex items-center gap-2 text-xs text-muted-foreground"><MapPin className="h-3.5 w-3.5" aria-hidden="true" />{scene.title}<span>·</span>{scene.shots.length} shots<ApprovalBadge status={scene.approval_status} /></div>{scene.shots.map((shot) => <StoryboardShot key={shot.id} detail={detail} shot={shot} blocked={episode.approval_status !== "approved" || scene.approval_status !== "approved"} onRefresh={onRefresh} />)}</div>)}</div>)}</div>
    </div>
  );
}

export function DramaWorkspace({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = React.useState("bible");
  const [selectedDramaId, setSelectedDramaId] = React.useState("");
  const [showNew, setShowNew] = React.useState(false);
  const [localDetail, setLocalDetail] = React.useState<DramaDetail | undefined>();
  const projectQuery = useQuery({ queryKey: ["project", projectId], queryFn: () => api.getProject(projectId) });
  const dramasQuery = useQuery({ queryKey: ["project-dramas", projectId], queryFn: () => api.listDramas(projectId) });
  const detailQuery = useQuery({ queryKey: ["drama", selectedDramaId], queryFn: () => api.getDrama(selectedDramaId), enabled: Boolean(selectedDramaId) });

  React.useEffect(() => {
    if (!selectedDramaId && dramasQuery.data?.[0]?.id) setSelectedDramaId(dramasQuery.data[0].id);
  }, [dramasQuery.data, selectedDramaId]);
  React.useEffect(() => {
    if (detailQuery.data) setLocalDetail(detailQuery.data);
  }, [detailQuery.data]);

  const detail = localDetail?.id === selectedDramaId ? localDetail : detailQuery.data;
  const project = projectQuery.data;

  const refresh = React.useCallback((next: DramaDetail) => {
    setLocalDetail(next);
    queryClient.setQueryData(["drama", next.id], next);
    queryClient.invalidateQueries({ queryKey: ["project-dramas", projectId] });
  }, [projectId, queryClient]);

  if (projectQuery.isLoading || dramasQuery.isLoading) {
    return <PageContainer width="wide"><div className="flex min-h-96 items-center justify-center text-sm text-muted-foreground">正在打开 Drama workspace…</div></PageContainer>;
  }
  if (!project) {
    return <PageContainer width="wide"><Card><CardContent className="p-8 text-center text-sm text-muted-foreground">项目不存在或暂时无法打开。</CardContent></Card></PageContainer>;
  }

  return (
    <PageContainer width="wide" className="space-y-5">
      <PageHeader
        eyebrow="Drama production workspace"
        title="Drama workspace"
        description="把故事拆成可审阅的制作事实：Bible、角色、场景、单集和逐 Shot Storyboard。"
        back={<Link href={`/projects/${projectId}`} className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> 返回项目</Link>}
        actions={<div className="flex items-center gap-2"><Select aria-label="选择 Drama Bible" value={selectedDramaId} onChange={(event) => { setSelectedDramaId(event.target.value); setShowNew(false); }} className="h-9 max-w-56 text-xs"><option value="">新建 Drama Bible</option>{(dramasQuery.data || []).map((drama) => <option key={drama.id} value={drama.id}>{drama.title}</option>)}</Select><Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => { setSelectedDramaId(""); setLocalDetail(undefined); setShowNew(true); }}><RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" /> 新建</Button></div>}
      />

      {!detail || showNew ? (
        <div className="grid gap-5 xl:grid-cols-[240px_minmax(0,1fr)]"><StageRail /><IntakePanel project={project} onCreated={(next) => { refresh(next); setShowNew(false); setSelectedDramaId(next.id); setActiveTab("bible"); }} /></div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[240px_minmax(0,1fr)]">
          <StageRail detail={detail} />
          <div className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/60 bg-card/50 px-4 py-3"><div className="flex items-center gap-2 text-xs text-muted-foreground"><LockKeyhole className="h-3.5 w-3.5 text-primary" aria-hidden="true" /><span>所有锁定字段都会写入 deterministic prompt anchor</span></div><span className="font-mono text-[10px] text-muted-foreground">{detail.id}</span></div>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="w-full justify-start"><TabsTrigger value="bible">Bible</TabsTrigger><TabsTrigger value="characters">Characters <span className="ml-1 text-[10px] text-muted-foreground">{detail.characters.length}</span></TabsTrigger><TabsTrigger value="locations">Locations <span className="ml-1 text-[10px] text-muted-foreground">{detail.locations.length}</span></TabsTrigger><TabsTrigger value="episodes">Episodes <span className="ml-1 text-[10px] text-muted-foreground">{detail.episodes.length}</span></TabsTrigger><TabsTrigger value="storyboard">Storyboard</TabsTrigger><TabsTrigger value="production" disabled={detail.approval_status !== "approved"}>Production</TabsTrigger></TabsList>
              <TabsContent value="bible"><BiblePanel detail={detail} /></TabsContent>
              <TabsContent value="characters"><CharactersPanel detail={detail} onRefresh={refresh} /></TabsContent>
              <TabsContent value="locations"><LocationsPanel detail={detail} onRefresh={refresh} /></TabsContent>
              <TabsContent value="episodes"><div className="space-y-4"><SectionHeader title="Episodes" description="先确认单集剧本，再确认场景结构，最后进入逐 Shot review。" actions={<Badge variant="outline">{detail.episodes.length} 集</Badge>} />{detail.episodes.map((episode) => <EpisodeCard key={episode.id} detail={detail} episode={episode} onRefresh={refresh} />)}</div></TabsContent>
              <TabsContent value="storyboard"><StoryboardPanel detail={detail} onRefresh={refresh} /></TabsContent>
              <TabsContent value="production"><DramaProductionPanel detail={detail} /></TabsContent>
            </Tabs>
          </div>
        </div>
      )}
    </PageContainer>
  );
}
