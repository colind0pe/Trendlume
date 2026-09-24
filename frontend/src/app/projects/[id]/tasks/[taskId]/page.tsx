"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Download, Play, RotateCcw, Save, StopCircle } from "lucide-react";
import { api } from "@/lib/api-client";
import type { SceneCreate, WorkflowArtifact, WorkflowJob } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";
import { useToast } from "@/components/ui/toast";
import { TaskDetailFields } from "@/components/projects/task-detail-fields";
import { KnowledgeStoryboard } from "@/components/projects/knowledge-storyboard";
import { useTaskEvents, TASK_REFRESH_EVENTS } from "@/lib/use-task-events";

const ACTIVE = new Set(["queued", "retrying", "running"]);
const FAILED = new Set(["failed", "cancelled"]);
const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString("zh-CN") : "—";
const jobLabel = (status: string) => ({ queued: "排队中", retrying: "等待重试", running: "生产中", completed: "已成功", succeeded: "已成功", failed: "失败", cancelled: "已取消" } as Record<string, string>)[status] || status;

export default function TaskEditorPage() {
  const params = useParams();
  const projectId = params.id as string;
  const taskId = params.taskId as string;
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [detail, setDetail] = React.useState<Record<string, unknown> & { type: "knowledge" | "commerce" | "drama" }>({ type: "knowledge" });
  const [selectedJobId, setSelectedJobId] = React.useState<string | null>(null);
  const [accountId, setAccountId] = React.useState("");
  const [scheduledAt, setScheduledAt] = React.useState("");
  const [sceneDrafts, setSceneDrafts] = React.useState<SceneCreate[]>([]);
  const [storyboardDirty, setStoryboardDirty] = React.useState(false);
  const [contentDirty, setContentDirty] = React.useState(false);
  const [sceneAction, setSceneAction] = React.useState<{ sceneId: string; kind: "voice" | "visual" } | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["task-jobs", taskId],
    queryFn: () => api.listTaskJobs(taskId),
    refetchInterval: (query) => (query.state.data || []).some((job) => ACTIVE.has(job.status)) ? 2000 : false,
  });
  const hasActiveJob = (jobsQuery.data || []).some((job) => ACTIVE.has(job.status));
  const selectedJob = selectedJobId || jobsQuery.data?.[0]?.id || null;

  const taskQuery = useQuery({
    queryKey: ["task-detail", taskId],
    queryFn: () => api.getTask(taskId),
    refetchInterval: hasActiveJob ? 2000 : false,
  });
  const readinessQuery = useQuery({
    queryKey: ["task-readiness", taskId],
    queryFn: () => api.getTaskReadiness(taskId),
    refetchInterval: hasActiveJob ? 4000 : false,
  });
  const jobQuery = useQuery({
    queryKey: ["workflow-job", selectedJob],
    queryFn: () => api.getWorkflowJob(selectedJob!),
    enabled: Boolean(selectedJob),
    refetchInterval: (query) => ACTIVE.has(query.state.data?.status || "") ? 2000 : false,
  });
  const accountsQuery = useQuery({ queryKey: ["publishing-accounts", "douyin"], queryFn: () => api.listAccounts("douyin") });
  const assetsQuery = useQuery({
    queryKey: ["project-assets", projectId],
    queryFn: () => api.listAssets(projectId),
    refetchInterval: hasActiveJob ? 2000 : false,
  });

  const refresh = React.useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] }),
      queryClient.invalidateQueries({ queryKey: ["task-readiness", taskId] }),
      queryClient.invalidateQueries({ queryKey: ["task-jobs", taskId] }),
      queryClient.invalidateQueries({ queryKey: ["workflow-job"] }),
      queryClient.invalidateQueries({ queryKey: ["project-assets", projectId] }),
      queryClient.invalidateQueries({ queryKey: ["all-tasks"] }),
    ]);
  }, [queryClient, taskId, projectId]);

  useTaskEvents({
    onEvent: (event) => {
      const data = event.data;
      if (!data.task_id || data.task_id === taskId) {
        if (TASK_REFRESH_EVENTS.has(event.event)) {
          refresh();
        }
      }
    },
    onReconnect: refresh,
  });

  React.useEffect(() => {
    if (!taskQuery.data) return;
    if (!contentDirty) {
      setTitle(taskQuery.data.title);
      setDescription(taskQuery.data.description);
      setDetail(taskQuery.data.detail);
    }
    if (!storyboardDirty) {
      setSceneDrafts((taskQuery.data.scenes || []).map((scene) => ({
        sequence_index: scene.sequence_index,
        narration_text: scene.narration_text,
        visual_prompt: scene.visual_prompt,
        duration_seconds: scene.duration_seconds,
        layout_params: scene.layout_params,
        visual_role: scene.visual_role,
        claim_refs: scene.claim_refs,
        source_refs: scene.source_refs,
        production_metadata: scene.production_metadata,
        audio_asset_id: scene.audio_asset_id,
        media_asset_id: scene.media_asset_id,
      })));
    }
  }, [taskQuery.data, storyboardDirty, contentDirty]);

  React.useEffect(() => {
    if (!contentDirty && !storyboardDirty) return;
    const warnBeforeLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeLeave);
    return () => window.removeEventListener("beforeunload", warnBeforeLeave);
  }, [contentDirty, storyboardDirty]);

  const fail = (titleText: string) => (error: Error) => toast(`${titleText}：${error.message}`, "error");

  const saveMutation = useMutation({
    mutationFn: () => api.updateTask(taskId, { title, description, detail }),
    onSuccess: async () => { await refresh(); setContentDirty(false); toast("内容设定已保存", "success"); }, onError: fail("保存失败"),
  });
  const approveMutation = useMutation({ mutationFn: () => api.approveTask(taskId), onSuccess: async () => { await refresh(); toast("Task 已审批", "success"); }, onError: fail("审批失败") });
  const produceMutation = useMutation({ mutationFn: () => api.createWorkflowJob(taskId), onSuccess: async (createdJob) => { setSelectedJobId(createdJob.id); await refresh(); toast("生成任务已启动", "success"); }, onError: fail("无法开始生产") });
  const retryMutation = useMutation({ mutationFn: (jobId: string) => api.retryWorkflowJob(jobId), onSuccess: async (retryJob) => { setSelectedJobId(retryJob.id); await refresh(); toast("已使用原 Snapshot 创建重试 Job", "success"); }, onError: fail("重试失败") });
  const cancelMutation = useMutation({ mutationFn: (jobId: string) => api.cancelWorkflowJob(jobId), onSuccess: refresh, onError: fail("取消失败") });
  const retrySceneMutation = useMutation({ mutationFn: (sceneId: string) => api.retrySceneMedia(taskId, sceneId), onSuccess: async (sceneJob) => { setSelectedJobId(sceneJob.id); await refresh(); toast("已按原 Snapshot 创建单镜重试；完成后仍需重新合成最终视频。", "success"); }, onError: fail("单镜重试失败") });

  const saveKnowledgeChangesMutation = useMutation({
    mutationFn: ({ saveContent, saveStoryboard, scenes }: { saveContent: boolean; saveStoryboard: boolean; scenes: SceneCreate[] }) => Promise.all([
      saveContent ? api.updateTask(taskId, { title, description, detail }) : Promise.resolve(),
      saveStoryboard ? api.batchUpdateTaskScenes(taskId, scenes) : Promise.resolve(),
    ]),
    onSuccess: async () => { await refresh(); setContentDirty(false); setStoryboardDirty(false); toast("故事板已保存", "success"); },
    onError: fail("保存故事板失败"),
  });

  const runSceneAction = async (sceneId: string, kind: "voice" | "visual") => {
    setSceneAction({ sceneId, kind });
    try {
      if (kind === "voice") {
        await api.generateSceneTTS(sceneId, String(taskQuery.data?.generation_settings?.voice_id || "") || undefined, Number(taskQuery.data?.generation_settings?.speed || 1));
        toast("旁白配音已更新。", "success");
      } else {
        const mode = String(taskQuery.data?.generation_settings?.content_mode || "generated_image");
        if (mode === "online_asset") await api.generateSceneOnlineMaterial(sceneId);
        else if (mode === "generated_video") await api.generateSceneVideo(sceneId);
        else await api.generateSceneImage(sceneId);
        toast(`${mode === "online_asset" ? "在线素材" : mode === "generated_video" ? "视频片段" : "分镜画面"}已更新；请重新生成最终视频。`, "success");
      }
      await refresh();
    } catch (error) {
      fail(kind === "voice" ? "生成配音失败" : "生成画面失败")(error as Error);
    } finally {
      setSceneAction(null);
    }
  };

  const publishMutation = useMutation({
    mutationFn: ({
      job: targetJob,
      artifact,
      accountId: accId,
      scheduledAt: schedAt,
      title: pubTitle,
      description: pubDesc,
      tags: pubTags,
      coverAssetId,
    }: {
      job: WorkflowJob;
      artifact: WorkflowArtifact;
      accountId?: string;
      scheduledAt?: string | null;
      title?: string;
      description?: string;
      tags?: string[];
      coverAssetId?: string | null;
    }) =>
      api.createPublishingJob({
        project_id: projectId,
        workflow_job_id: targetJob.id,
        artifact_id: artifact.id,
        account_id: accId || accountId,
        platform: "douyin",
        title: pubTitle || title || "未命名视频",
        description: pubDesc ?? description,
        tags: pubTags,
        cover_asset_id: coverAssetId || null,
        scheduled_at: (schedAt ?? scheduledAt) ? new Date((schedAt ?? scheduledAt)!).toISOString() : null,
      }),
    onSuccess: () => toast("发布任务已创建，可在发布中心继续查看。", "success"),
    onError: fail("创建发布任务失败"),
  });

  const regenerateMetadataMutation = useMutation({
    mutationFn: () => api.regenerateTaskMetadata(taskId),
    onSuccess: async () => {
      await refresh();
      queryClient.invalidateQueries({ queryKey: ["project-tasks", projectId] });
      toast("平台发布文案与话题已重新生成。", "success");
    },
    onError: fail("生成发布信息失败"),
  });

  const handleStartProduction = async () => {
    try {
      if (contentDirty || storyboardDirty) {
        await saveKnowledgeChangesMutation.mutateAsync({
          saveContent: contentDirty,
          saveStoryboard: storyboardDirty,
          scenes: sceneDrafts,
        });
      }
      if (taskQuery.data?.editorial_status !== "approved") {
        await approveMutation.mutateAsync();
      }
      await produceMutation.mutateAsync();
    } catch {
      // Handled in individual mutations
    }
  };

  const task = taskQuery.data;
  const job = jobQuery.data;
  const finalVideo = job?.artifacts?.find((artifact) => artifact.kind === "final_video");

  if (taskQuery.isLoading) return <PageContainer>正在加载 Task…</PageContainer>;
  if (!task) return <PageContainer>Task 不存在。</PageContainer>;

  if (task.detail.type === "knowledge") {
    const projectAssets = (assetsQuery.data || []).filter(
      (asset) => asset.asset_type === "image" || asset.asset_type === "video"
    );

    const updateScene = (index: number, changes: Partial<SceneCreate>) => {
      setSceneDrafts((current) =>
        current.map((scene, sceneIndex) => (sceneIndex === index ? { ...scene, ...changes } : scene))
      );
      setStoryboardDirty(true);
    };

    const moveScene = (index: number, direction: -1 | 1) => {
      const target = index + direction;
      if (target < 0 || target >= sceneDrafts.length) return;
      setSceneDrafts((current) => {
        const next = [...current];
        [next[index], next[target]] = [next[target], next[index]];
        return next.map((scene, sceneIndex) => ({ ...scene, sequence_index: sceneIndex }));
      });
      setStoryboardDirty(true);
    };

    const addScene = () => {
      setSceneDrafts((current) => [
        ...current,
        {
          sequence_index: current.length,
          narration_text: "",
          visual_prompt: "",
          duration_seconds: 4,
          visual_role: "concept",
          layout_params: {},
          claim_refs: [],
          source_refs: [],
          production_metadata: {},
        },
      ]);
      setStoryboardDirty(true);
    };

    const deleteScene = (index: number) => {
      setSceneDrafts((current) =>
        current
          .filter((_, sceneIndex) => sceneIndex !== index)
          .map((scene, sceneIndex) => ({ ...scene, sequence_index: sceneIndex }))
      );
      setStoryboardDirty(true);
    };

    const saveAll = async () => {
      await saveKnowledgeChangesMutation.mutateAsync({
        saveContent: contentDirty,
        saveStoryboard: storyboardDirty,
        scenes: sceneDrafts,
      });
    };

    return (
      <PageContainer width="wide" className="space-y-6">
        <KnowledgeStoryboard
          projectId={projectId}
          task={task}
          job={job || null}
          jobs={jobsQuery.data || []}
          selectedJobId={selectedJob}
          onSelectJobId={(id) => setSelectedJobId(id)}
          sceneDrafts={sceneDrafts}
          onUpdateScene={updateScene}
          onMoveScene={moveScene}
          onAddScene={addScene}
          onDeleteScene={deleteScene}
          title={title}
          onTitleChange={(val) => {
            setTitle(val);
            setContentDirty(true);
          }}
          detail={detail}
          onDetailChange={(val) => {
            setDetail(val);
            setContentDirty(true);
          }}
          description={description}
          onDescriptionChange={(val) => {
            setDescription(val);
            setContentDirty(true);
          }}
          storyboardDirty={storyboardDirty}
          contentDirty={contentDirty}
          onSaveAll={saveAll}
          isSaving={saveKnowledgeChangesMutation.isPending}
          hasActiveJob={hasActiveJob}
          readiness={readinessQuery.data}
          onStartProduction={handleStartProduction}
          isStartingProduction={produceMutation.isPending || approveMutation.isPending}
          onRetryJob={(targetJobId) => retryMutation.mutate(targetJobId)}
          onCancelJob={(targetJobId) => cancelMutation.mutate(targetJobId)}
          onRunSceneAction={runSceneAction}
          sceneAction={sceneAction}
          projectAssets={projectAssets}
          accounts={accountsQuery.data || []}
          onPublish={async (pubJob, artifact, publishData) => {
            await publishMutation.mutateAsync({
              job: pubJob,
              artifact,
              ...publishData,
            });
          }}
          isPublishing={publishMutation.isPending}
          onRegenerateMetadata={() => regenerateMetadataMutation.mutate()}
          isRegeneratingMetadata={regenerateMetadataMutation.isPending}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title={task.title}
        description="编辑内容、审批并通过 WorkflowJob 完成生产与发布。"
        actions={
          <Link
            className="inline-flex h-10 items-center rounded-md border px-4 text-sm"
            href={`/projects/${projectId}`}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回 Project
          </Link>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <Card><CardHeader><CardTitle>Task 内容</CardTitle><CardDescription>模式：{task.detail.type}。修改后下一次生产会生成新 Snapshot 和 Job。</CardDescription></CardHeader><CardContent className="space-y-3">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="标题" />
          <Textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="描述" />
          <TaskDetailFields detail={detail} onChange={setDetail} projectId={projectId} />
          <div className="flex flex-wrap gap-2"><Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}><Save className="mr-2 h-4 w-4" />保存</Button><Button variant="outline" onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending || task.editorial_status === "approved"}><Check className="mr-2 h-4 w-4" />审批 Task</Button><Button onClick={() => produceMutation.mutate()} disabled={produceMutation.isPending || !readinessQuery.data?.ready || (jobsQuery.data || []).some((item) => ACTIVE.has(item.status))}><Play className="mr-2 h-4 w-4" />开始生产</Button></div>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>分镜媒体计划</CardTitle><CardDescription>每镜可使用不同画面方式。单镜刷新只替换该镜素材，最终视频仍需重新合成。</CardDescription></CardHeader><CardContent className="space-y-2">
          {(task.scenes || []).length === 0 ? <p className="text-sm text-muted-foreground">尚无可执行分镜；Drama 会在已审批 Shot 进入生产后建立执行投影。</p> : task.scenes.map((scene) => {
            const plan = scene.production_metadata?.media_plan as { strategy?: string; cost_tier?: string } | undefined;
            return <div key={scene.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3 text-sm"><div><p className="font-medium">镜头 {scene.sequence_index + 1} · {scene.visual_role}</p><p className="mt-1 text-xs text-muted-foreground">{plan?.strategy || "由 Recipe 在 Job Snapshot 中规划"} · {scene.duration_seconds}s{plan?.cost_tier ? ` · ${plan.cost_tier} 成本` : ""}</p></div><Button variant="outline" disabled={!jobsQuery.data?.length || retrySceneMutation.isPending || (jobsQuery.data || []).some((item) => ACTIVE.has(item.status))} onClick={() => retrySceneMutation.mutate(scene.id)}><RotateCcw className="mr-2 h-4 w-4" />重生此镜</Button></div>;
          })}
        </CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2">{readinessQuery.data?.ready ? <CheckCircle2 className="h-5 w-5 text-success" /> : <AlertTriangle className="h-5 w-5 text-warning" />}生产准备</CardTitle><CardDescription>{readinessQuery.data?.ready ? "检查已通过，可以创建 WorkflowJob。" : "请先处理以下阻塞项。"}</CardDescription></CardHeader><CardContent className="grid gap-2 sm:grid-cols-2">{(readinessQuery.data?.checks || []).map((item) => <div key={item.key} className="rounded-md border p-3 text-sm"><div className="flex items-center gap-2 font-medium">{item.status === "pass" ? <CheckCircle2 className="h-4 w-4 text-success" /> : <AlertTriangle className="h-4 w-4 text-warning" />}{item.label}</div><p className="mt-1 text-xs text-muted-foreground">{item.message}</p></div>)}</CardContent></Card>
        <Card><CardHeader><CardTitle>当前 WorkflowJob</CardTitle><CardDescription>执行状态只来自 Job；Task 仅保留内容审核与生产生命周期。</CardDescription></CardHeader><CardContent className="space-y-4">
          {!job ? <p className="text-sm text-muted-foreground">尚未创建生产 Job。</p> : <>
            <div className="flex flex-wrap items-center gap-2"><Badge>{jobLabel(job.status)}</Badge><span className="text-sm">当前阶段：{job.current_stage || "—"}</span></div><Progress value={job.progress} />
            <dl className="grid grid-cols-2 gap-2 text-sm"><div><dt className="text-muted-foreground">开始</dt><dd>{formatDate(job.started_at)}</dd></div><div><dt className="text-muted-foreground">完成</dt><dd>{formatDate(job.completed_at)}</dd></div></dl>
            {job.error_message && <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{job.error_message}</p>}
            <div className="flex gap-2">{FAILED.has(job.status) && <Button variant="outline" onClick={() => retryMutation.mutate(job.id)}><RotateCcw className="mr-2 h-4 w-4" />重试整个 Job</Button>}{ACTIVE.has(job.status) && <Button variant="outline" onClick={() => cancelMutation.mutate(job.id)}><StopCircle className="mr-2 h-4 w-4" />取消 Job</Button>}</div>
            <div className="space-y-2"><h3 className="font-medium">阶段运行</h3>{(job.stages || []).map((stage) => <div key={stage.id} className="rounded-md border p-3 text-sm"><div className="flex justify-between"><span>{stage.step_key}{stage.unit_key ? ` / ${stage.unit_key}` : ""}</span><Badge variant="outline">{stage.status}</Badge></div>{stage.error_message && <p className="mt-2 text-destructive">{stage.error_message}</p>}</div>)}</div>
            <div className="space-y-2"><h3 className="font-medium">Artifacts</h3>{(job.artifacts || []).map((artifact) => <a key={artifact.id} className="flex items-center justify-between rounded-md border p-3 text-sm hover:bg-muted" href={api.workflowArtifactUrl(job.id, artifact.id)}><span>{artifact.kind}</span><Download className="h-4 w-4" /></a>)}</div>
          </>}
        </CardContent></Card>
        {job && finalVideo && ["completed", "succeeded"].includes(job.status) && <Card><CardHeader><CardTitle>发布最终视频</CardTitle><CardDescription>来源锁定为当前成功 Job 的 final_video Artifact。</CardDescription></CardHeader><CardContent className="space-y-3"><select className="h-10 w-full rounded-md border bg-background px-3" value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">选择有效发布账号</option>{(accountsQuery.data || []).filter((account) => account.status === "active").map((account) => <option key={account.id} value={account.id}>{account.account_name}</option>)}</select><Input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} /><Button disabled={!accountId || publishMutation.isPending} onClick={() => publishMutation.mutate({ job, artifact: finalVideo })}>{scheduledAt ? "创建定时发布" : "创建发布任务"}</Button></CardContent></Card>}
        </div>
        <Card className="h-fit"><CardHeader><CardTitle>状态与历史</CardTitle></CardHeader><CardContent className="space-y-4"><div className="space-y-2 text-sm"><div className="flex justify-between"><span>内容审核</span><Badge variant="outline">{task.editorial_status}</Badge></div><div className="flex justify-between"><span>Task 生产生命周期</span><Badge variant="outline">{task.production_status}</Badge></div><div className="flex justify-between"><span>当前 Job</span><Badge variant="outline">{job ? jobLabel(job.status) : "无"}</Badge></div></div><div className="space-y-2">{(jobsQuery.data || []).map((item) => <button key={item.id} className={`w-full rounded-md border p-3 text-left text-sm ${selectedJob === item.id ? "border-primary" : ""}`} onClick={() => setSelectedJobId(item.id)}><div className="flex justify-between"><span>{jobLabel(item.status)}</span><span>{item.progress}%</span></div><p className="mt-1 text-xs text-muted-foreground">{formatDate(item.created_at)}</p></button>)}</div></CardContent></Card>
      </div>
    </PageContainer>
  );
}
