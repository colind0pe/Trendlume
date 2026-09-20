"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Download, Play, RotateCcw, Save, StopCircle } from "lucide-react";
import { api } from "@/lib/api-client";
import type { WorkflowArtifact, WorkflowJob } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";
import { useToast } from "@/components/ui/toast";
import { TaskDetailFields } from "@/components/projects/task-detail-fields";

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

  const taskQuery = useQuery({ queryKey: ["task-detail", taskId], queryFn: () => api.getTask(taskId) });
  const jobsQuery = useQuery({
    queryKey: ["task-jobs", taskId], queryFn: () => api.listTaskJobs(taskId),
    refetchInterval: (query) => (query.state.data || []).some((job) => ACTIVE.has(job.status)) ? 2000 : false,
  });
  const selectedJob = selectedJobId || jobsQuery.data?.[0]?.id || null;
  const jobQuery = useQuery({
    queryKey: ["workflow-job", selectedJob], queryFn: () => api.getWorkflowJob(selectedJob!), enabled: Boolean(selectedJob),
    refetchInterval: (query) => ACTIVE.has(query.state.data?.status || "") ? 2000 : false,
  });
  const accountsQuery = useQuery({ queryKey: ["publishing-accounts", "douyin"], queryFn: () => api.listAccounts("douyin") });

  React.useEffect(() => {
    if (!taskQuery.data) return;
    setTitle(taskQuery.data.title); setDescription(taskQuery.data.description);
    setDetail(taskQuery.data.detail);
  }, [taskQuery.data]);

  const refresh = async () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["task-detail", taskId] }),
    queryClient.invalidateQueries({ queryKey: ["task-jobs", taskId] }),
    queryClient.invalidateQueries({ queryKey: ["workflow-job"] }),
    queryClient.invalidateQueries({ queryKey: ["all-tasks"] }),
  ]);
  const fail = (titleText: string) => (error: Error) => toast(`${titleText}：${error.message}`, "error");
  const saveMutation = useMutation({
    mutationFn: () => api.updateTask(taskId, { title, description, detail }),
    onSuccess: async () => { await refresh(); toast("Task 已保存", "success"); }, onError: fail("保存失败"),
  });
  const approveMutation = useMutation({ mutationFn: () => api.approveTask(taskId), onSuccess: async () => { await refresh(); toast("Task 已审批", "success"); }, onError: fail("审批失败") });
  const produceMutation = useMutation({ mutationFn: () => api.createWorkflowJob(taskId), onSuccess: async (job) => { setSelectedJobId(job.id); await refresh(); toast("生产 Job 已创建", "success"); }, onError: fail("无法开始生产") });
  const retryMutation = useMutation({ mutationFn: (jobId: string) => api.retryWorkflowJob(jobId), onSuccess: async (job) => { setSelectedJobId(job.id); await refresh(); toast("已使用原 Snapshot 创建重试 Job", "success"); }, onError: fail("重试失败") });
  const cancelMutation = useMutation({ mutationFn: (jobId: string) => api.cancelWorkflowJob(jobId), onSuccess: refresh, onError: fail("取消失败") });
  const publishMutation = useMutation({
    mutationFn: ({ job, artifact }: { job: WorkflowJob; artifact: WorkflowArtifact }) => api.createPublishingJob({ project_id: projectId, workflow_job_id: job.id, artifact_id: artifact.id, account_id: accountId, platform: "douyin", title: title || "未命名视频", description, scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null }),
    onSuccess: () => toast(`${scheduledAt ? "定时发布任务已创建" : "发布任务已创建"}，可在发布中心继续查看。`, "success"), onError: fail("创建发布任务失败"),
  });

  const task = taskQuery.data; const job = jobQuery.data;
  const finalVideo = job?.artifacts?.find((artifact) => artifact.kind === "final_video");
  if (taskQuery.isLoading) return <PageContainer>正在加载 Task…</PageContainer>;
  if (!task) return <PageContainer>Task 不存在。</PageContainer>;

  return <PageContainer>
    <PageHeader title={task.title} description="编辑内容、审批并通过 WorkflowJob 完成生产与发布。" actions={<Link className="inline-flex h-10 items-center rounded-md border px-4 text-sm" href={`/projects/${projectId}`}><ArrowLeft className="mr-2 h-4 w-4" />返回 Project</Link>} />
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <Card><CardHeader><CardTitle>Task 内容</CardTitle><CardDescription>模式：{task.detail.type}。修改后下一次生产会生成新 Snapshot 和 Job。</CardDescription></CardHeader><CardContent className="space-y-3">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="标题" />
          <Textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="描述" />
          <TaskDetailFields detail={detail} onChange={setDetail} />
          <div className="flex flex-wrap gap-2"><Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}><Save className="mr-2 h-4 w-4" />保存</Button><Button variant="outline" onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending || task.editorial_status === "approved"}><Check className="mr-2 h-4 w-4" />审批 Task</Button><Button onClick={() => produceMutation.mutate()} disabled={produceMutation.isPending || task.editorial_status !== "approved" || (jobsQuery.data || []).some((item) => ACTIVE.has(item.status))}><Play className="mr-2 h-4 w-4" />开始生产</Button></div>
        </CardContent></Card>
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
  </PageContainer>;
}
