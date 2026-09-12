"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2,
  Share2,
  Trash2,
  Users,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { SearchInput } from "@/components/ui/input";
import { PageContainer, PageHeader, SectionHeader } from "@/components/ui/page-shell";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { VerificationModal } from "@/components/verification-modal";
import { useToast } from "@/components/ui/toast";
import {
  getPublishStatusTone,
  PUBLISH_STATUS_LABELS,
} from "@/lib/ui-constants";

type PublishingTab = "jobs" | "history" | "accounts";

function publishStatusLabel(status: string) {
  return PUBLISH_STATUS_LABELS[status] || "待确认";
}

function platformLabel(platform: string) {
  return platform === "douyin" ? "抖音" : platform || "抖音";
}

export default function PublishingPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = React.useState<PublishingTab>("jobs");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [jobToCancel, setJobToCancel] = React.useState<{ id: string; title: string } | null>(null);
  const [jobToDelete, setJobToDelete] = React.useState<{ id: string; title: string } | null>(null);

  const [checkingAccountId, setCheckingAccountId] = React.useState<string | null>(null);
  const [accountCheckResults, setAccountCheckResults] = React.useState<
    Record<string, { isValid: boolean; message: string }>
  >({});

  const { data: accounts = [], isLoading: isLoadingAccounts } = useQuery({
    queryKey: ["publishing-accounts"],
    queryFn: () => api.listAccounts("douyin"),
  });

  const { data: jobs = [] } = useQuery({
    queryKey: ["publishing-jobs"],
    queryFn: () => api.listPublishingJobs(),
    refetchInterval: 4000,
  });

  const executeJobMutation = useMutation({
    mutationFn: (jobId: string) => api.executePublishingJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("发布作业已开始执行。", "success");
    },
    onError: (error: any) => toast(`执行发布失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const retryJobMutation = useMutation({
    mutationFn: (jobId: string) => api.retryPublishingJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("发布作业已重新加入队列。", "success");
    },
    onError: (error: any) => toast(`重试发布失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const confirmMissedMutation = useMutation({
    mutationFn: (jobId: string) => api.confirmMissedPublishingJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("已确认并重新执行错过的发布作业。", "success");
    },
    onError: (error: any) => toast(`确认发布失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const cancelJobMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelPublishingJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("发布作业已取消。", "success");
    },
    onError: (error: any) => toast(`取消发布失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const deleteJobMutation = useMutation({
    mutationFn: (jobId: string) => api.deletePublishingJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("发布记录已删除，视频任务和成片已保留。", "success");
    },
    onError: (error: any) => toast(`删除失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const resolveUncertainMutation = useMutation({
    mutationFn: ({ jobId, action }: { jobId: string; action: "retry" | "acknowledge" }) =>
      api.resolveUncertainPublishingJob(jobId, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      toast("不确定状态已处理。", "success");
    },
    onError: (error: any) => toast(`处理不确定发布失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const handleCheckAccount = async (accountId: string) => {
    setCheckingAccountId(accountId);
    try {
      const res = await api.checkAccountStatus(accountId);
      setAccountCheckResults((prev) => ({
        ...prev,
        [accountId]: {
          isValid: res.is_valid,
          message: res.is_valid ? "登录凭据有效" : res.error_message || "登录凭据已失效",
        },
      }));
      toast(
        res.is_valid ? "账号凭证有效。" : res.error_message || "账号凭证已失效。",
        res.is_valid ? "success" : "warning"
      );
    } catch (e: any) {
      setAccountCheckResults((prev) => ({
        ...prev,
        [accountId]: { isValid: false, message: e.message || "检查失败" },
      }));
      toast(e.message || "账号检查失败。", "error");
    } finally {
      setCheckingAccountId(null);
    }
  };

  const activeJobs = jobs.filter((job) => job.status !== "published");
  const historyJobs = jobs.filter((job) => job.status === "published");

  const filteredActiveJobs = React.useMemo(() => {
    return activeJobs.filter((job) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        job.title?.toLowerCase().includes(q) ||
        job.description?.toLowerCase().includes(q) ||
        (job.tags || []).some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [activeJobs, searchQuery]);

  const filteredHistoryJobs = React.useMemo(() => {
    return historyJobs.filter((job) => {
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      return (
        job.title?.toLowerCase().includes(q) ||
        job.description?.toLowerCase().includes(q) ||
        (job.tags || []).some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [historyJobs, searchQuery]);

  return (
    <PageContainer width="wide" className="space-y-5">
      <PageHeader
        title="发布中心"
        description="管理抖音账号授权与视频发布排期队列。"
        actions={(
          <Link href="/settings">
            <Button size="sm" variant="outline" className="gap-1.5 h-9 px-3.5 text-sm">
              <Settings2 className="h-4 w-4" />
              <span>发布配置</span>
            </Button>
          </Link>
        )}
      />

      {/* Publishing Stats Pulse Strip */}
      <div className="grid grid-cols-2 gap-3.5 sm:grid-cols-4">
        <div className="glass-card rounded-xl p-4 sm:p-5 hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">待发布排期</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Clock3 className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {activeJobs.length}
            </span>
            <span className="text-xs text-muted-foreground">条排期</span>
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 sm:p-5 hover:border-success/40 hover:shadow-glass-hover transition-all duration-200 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">已发布成功</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-success/10 text-success">
              <CheckCircle2 className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {historyJobs.length}
            </span>
            <span className="text-xs text-muted-foreground">条已发布</span>
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 sm:p-5 hover:border-destructive/40 hover:shadow-glass-hover transition-all duration-200 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">异常需关注</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
              <AlertCircle className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {jobs.filter((j) => j.status === "failed" || j.status === "missed" || j.status === "uncertain").length}
            </span>
            <span className="text-xs text-muted-foreground">条需处理</span>
          </div>
        </div>

        <div className="glass-card rounded-xl p-4 sm:p-5 hover:border-primary/30 hover:shadow-glass-hover transition-all duration-200 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="font-medium">授权账号</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-secondary text-foreground">
              <Users className="h-4 w-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-foreground tabular-nums">
              {accounts.length}
            </span>
            <span className="text-xs text-muted-foreground">个可用账号</span>
          </div>
        </div>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as PublishingTab)}
        className="space-y-4"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <TabsList aria-label="发布内容分类" className="h-10 w-full sm:w-auto sm:min-w-[560px] lg:min-w-[620px] grid grid-cols-3 p-1 rounded-xl glass-pill shadow-xs">
            <TabsTrigger value="jobs" className="gap-2 text-xs sm:text-sm h-8 px-3 sm:px-4 font-medium justify-center">
              <span>待发布排期</span>
              <span className="rounded-full bg-secondary/80 border border-border/80 px-2 py-0.5 font-mono text-xs text-muted-foreground tabular-nums">
                {activeJobs.length}
              </span>
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2 text-xs sm:text-sm h-8 px-3 sm:px-4 font-medium justify-center">
              <span>发布归档历史</span>
              <span className="rounded-full bg-secondary/80 border border-border/80 px-2 py-0.5 font-mono text-xs text-muted-foreground tabular-nums">
                {historyJobs.length}
              </span>
            </TabsTrigger>
            <TabsTrigger value="accounts" className="gap-2 text-xs sm:text-sm h-8 px-3 sm:px-4 font-medium justify-center">
              <span>授权账号</span>
              <span className="rounded-full bg-secondary/80 border border-border/80 px-2 py-0.5 font-mono text-xs text-muted-foreground tabular-nums">
                {accounts.length}
              </span>
            </TabsTrigger>
          </TabsList>

          <SearchInput
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onClear={() => setSearchQuery("")}
            placeholder="搜索发布记录或标签…"
            className="w-full sm:w-72 lg:w-80"
          />
        </div>

        <TabsContent value="jobs" className="space-y-4">
          <SectionHeader title="发布排期" description="查看待发布作业、执行状态与定时队列。" />
          {activeJobs.length === 0 ? (
            <EmptyState
              icon={Clock3}
              title="暂无待发布作业"
              description="在任务故事板中完成视频后，可从“发布到抖音”加入队列。"
            />
          ) : filteredActiveJobs.length === 0 ? (
            <EmptyState
              icon={Clock3}
              title="未找到匹配的发布作业"
              description="尝试调整搜索关键词。"
              action={(
                <Button variant="outline" size="sm" onClick={() => setSearchQuery("")} className="h-7 text-xs">
                  清除搜索
                </Button>
              )}
            />
          ) : (
            <div className="grid gap-3">
              {filteredActiveJobs.map((job) => {
                const isMutating =
                  executeJobMutation.isPending ||
                  retryJobMutation.isPending ||
                  confirmMissedMutation.isPending ||
                  cancelJobMutation.isPending ||
                  deleteJobMutation.isPending ||
                  resolveUncertainMutation.isPending;

                return (
                  <Card key={job.id} className="glass-card rounded-xl hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200">
                    <CardContent className="flex flex-col gap-4 p-4 sm:p-5 md:flex-row md:items-center md:justify-between">
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-medium text-muted-foreground">{platformLabel(job.platform)}</span>
                          <StatusBadge
                            tone={getPublishStatusTone(job.status)}
                            label={
                              <span className="inline-flex items-center gap-1">
                                {job.status === "publishing" && <Loader2 aria-hidden="true" className="h-3 w-3 animate-spin" />}
                                {publishStatusLabel(job.status)}
                              </span>
                            }
                          />
                          {job.custom_params?.auto_scheduled && (
                            <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
                              生成完成后自动发布
                            </span>
                          )}
                          {job.scheduled_at && (
                            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                              <Calendar aria-hidden="true" className="h-3.5 w-3.5" />
                              {new Date(job.scheduled_at).toLocaleString("zh-CN", {
                                timeZone: job.custom_params?.scheduled_timezone || undefined,
                              })}
                              {job.custom_params?.scheduled_timezone && ` · ${job.custom_params.scheduled_timezone}`}
                            </span>
                          )}
                        </div>

                        <div>
                          <h3 className="truncate text-base font-semibold text-foreground">
                            {job.task_id ? <Link className="hover:underline hover:text-primary transition-colors" href={`/projects/${job.project_id}/tasks/${job.task_id}`}>{job.title}</Link> : job.title}
                          </h3>
                          <p className="mt-1 line-clamp-1 text-sm text-muted-foreground leading-relaxed">{job.description}</p>
                        </div>

                        {(job.tags || []).length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {(job.tags || []).map((tag, index) => (
                              <span key={`${tag}-${index}`} className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                                #{tag.replace(/^#/, "")}
                              </span>
                            ))}
                          </div>
                        )}

                        {job.error_message && (
                          <p className="flex items-start gap-1.5 text-xs text-destructive">
                            <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                            <span>{job.error_message}</span>
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          尝试 {job.attempt_count}/{job.max_attempts}
                          {job.published_at && ` · 实际发布时间 ${new Date(job.published_at).toLocaleString()}`}
                        </p>
                      </div>

                      <div className="flex shrink-0 flex-wrap items-center gap-2 md:justify-end">
                        {(job.status === "queued" || job.status === "draft") && (
                          <Button size="sm" onClick={() => executeJobMutation.mutate(job.id)} disabled={isMutating} className="gap-1.5 h-9 px-3.5 text-sm">
                            <Play aria-hidden="true" className="h-4 w-4" />
                            立即执行发布
                          </Button>
                        )}

                        {job.status === "failed" && (
                          <Button size="sm" onClick={() => retryJobMutation.mutate(job.id)} disabled={isMutating} className="gap-1.5 h-9 px-3.5 text-sm">
                            <RotateCcw aria-hidden="true" className="h-4 w-4" />
                            重试发布
                          </Button>
                        )}

                        {job.status === "missed" && (
                          <Button size="sm" onClick={() => confirmMissedMutation.mutate(job.id)} disabled={isMutating} className="gap-1.5 h-9 px-3.5 text-sm">
                            <Play aria-hidden="true" className="h-4 w-4" />
                            确认并发布
                          </Button>
                        )}

                        {job.status === "uncertain" && (
                          <>
                            <Button size="sm" onClick={() => resolveUncertainMutation.mutate({ jobId: job.id, action: "retry" })} disabled={isMutating} className="gap-1.5 h-9 px-3.5 text-sm">
                              <RotateCcw aria-hidden="true" className="h-4 w-4" />
                              确认重新发布
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => resolveUncertainMutation.mutate({ jobId: job.id, action: "acknowledge" })} disabled={isMutating} className="h-9 px-3.5 text-sm">
                              已在抖音发布
                            </Button>
                          </>
                        )}

                        {(["draft", "scheduled", "queued", "publishing", "missed"].includes(job.status)) && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setJobToCancel({ id: job.id, title: job.title })}
                            disabled={isMutating}
                            className="gap-1.5 text-muted-foreground h-9 px-3 text-sm"
                          >
                            <Trash2 aria-hidden="true" className="h-4 w-4" />
                            取消
                          </Button>
                        )}
                        {!["publishing", "published", "uncertain"].includes(job.status) && (
                          <Button size="sm" variant="outline" disabled={isMutating} onClick={() => setJobToDelete({ id: job.id, title: job.title })} className="gap-1.5 text-destructive h-9 px-3 text-sm">
                            <Trash2 aria-hidden="true" className="h-4 w-4" />删除
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <SectionHeader title="发布记录" description="已发布作品归档及平台线上回执。" />
          {historyJobs.length === 0 ? (
            <EmptyState icon={CheckCircle2} title="暂无发布记录" description="完成一次发布后，作品回执会显示在这里。" />
          ) : filteredHistoryJobs.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="未找到匹配的历史记录"
              description="尝试调整搜索关键词。"
              action={(
                <Button variant="outline" size="sm" onClick={() => setSearchQuery("")} className="h-7 text-xs">
                  清除搜索
                </Button>
              )}
            />
          ) : (
            <div className="grid gap-3">
              {filteredHistoryJobs.map((job) => (
                <Card key={job.id} className="glass-card rounded-xl hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200">
                  <CardContent className="space-y-3 p-4 sm:p-5">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge tone="success" label="已发布" />
                        <span className="text-xs text-muted-foreground">{platformLabel(job.platform)}</span>
                        <span className="text-xs text-muted-foreground">{job.published_at ? new Date(job.published_at).toLocaleString() : ""}</span>
                      </div>
                      {job.platform_post_id && (
                        <a
                          href={job.platform_post_id.startsWith("dy_") ? "https://creator.douyin.com/creator-micro/content/manage" : `https://www.douyin.com/video/${job.platform_post_id}`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                        >
                          查看作品回执
                          <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-foreground">
                        {job.task_id ? <Link className="hover:underline hover:text-primary transition-colors" href={`/projects/${job.project_id}/tasks/${job.task_id}`}>{job.title}</Link> : job.title}
                      </h3>
                      <p className="mt-1 text-sm text-muted-foreground leading-relaxed">{job.description}</p>
                    </div>
                    {(job.tags || []).length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {(job.tags || []).map((tag, index) => (
                          <span key={`${tag}-${index}`} className="rounded-md bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                            #{tag.replace(/^#/, "")}
                          </span>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="accounts" className="space-y-4">
          <SectionHeader
            title="授权账号"
            description="查看抖音创作者账号绑定状态与登录凭证有效性。"
            actions={accounts.length > 0 ? (
              <Link href="/settings">
                <Button variant="outline" size="sm" className="gap-1.5 h-9 px-3.5 text-sm">
                  <Settings2 aria-hidden="true" className="h-4 w-4" />
                  打开系统设置
                </Button>
              </Link>
            ) : undefined}
          />

          {isLoadingAccounts ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" />
              正在加载账号
            </div>
          ) : accounts.length === 0 ? (
            <EmptyState
              icon={Share2}
              title="尚未绑定抖音账号"
              description="前往系统配置，通过手机抖音扫码绑定账号。登录凭据会由系统安全托管。"
              action={
                <Link href="/settings">
                  <Button className="gap-1.5 h-9 px-4 text-sm">前往系统配置</Button>
                </Link>
              }
            />
          ) : (
            <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
              {accounts.map((account) => {
                const checkState = accountCheckResults[account.id];
                const isChecking = checkingAccountId === account.id;
                return (
                  <Card key={account.id} className="glass-card rounded-xl hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200">
                    <CardContent className="flex h-full flex-col justify-between gap-4 p-4 sm:p-5">
                      <div className="space-y-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-muted-foreground">抖音创作者账号</span>
                          <StatusBadge
                            tone={checkState ? (checkState.isValid ? "success" : "destructive") : account.status === "error" ? "destructive" : "neutral"}
                            label={checkState ? (checkState.isValid ? "凭证有效" : "凭证失效") : account.status === "error" ? "凭证失效" : "待检查"}
                          />
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 font-bold text-primary text-sm shadow-xs">
                            {account.account_name.slice(0, 1)}
                          </div>
                          <div className="min-w-0">
                            <h3 className="truncate text-base font-semibold text-foreground">{account.account_name}</h3>
                            <p className="truncate text-xs text-muted-foreground">{account.username ? `@${account.username}` : `账号 ID ${account.id.slice(0, 10)}`}</p>
                          </div>
                        </div>
                        {checkState && !checkState.isValid && <p className="rounded-md border border-destructive/20 bg-destructive/5 px-2.5 py-2 text-xs text-destructive">{checkState.message}</p>}
                      </div>
                      <div className="border-t border-border/60 pt-3">
                        <Button variant="ghost" size="sm" disabled={isChecking} onClick={() => handleCheckAccount(account.id)} className="gap-1.5 px-0 text-xs sm:text-sm text-muted-foreground hover:bg-transparent hover:text-foreground">
                          <RefreshCw aria-hidden="true" className={`h-3.5 w-3.5 ${isChecking ? "animate-spin" : ""}`} />
                          {isChecking ? "检查中…" : "检查凭证"}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={Boolean(jobToCancel)}
        onOpenChange={(open) => {
          if (!open) setJobToCancel(null);
        }}
        title="取消发布作业？"
        description={jobToCancel ? `“${jobToCancel.title}”将从当前发布队列中取消。` : undefined}
        confirmLabel="确认取消"
        variant="destructive"
        onConfirm={async () => {
          if (jobToCancel) await cancelJobMutation.mutateAsync(jobToCancel.id);
        }}
      />

      <VerificationModal />
      <ConfirmDialog
        open={Boolean(jobToDelete)}
        onOpenChange={(open) => { if (!open) setJobToDelete(null); }}
        title="删除发布记录？"
        description={jobToDelete ? `将取消并删除“${jobToDelete.title}”的发布记录，保留对应视频任务和成片。` : undefined}
        confirmLabel="删除记录"
        variant="destructive"
        onConfirm={async () => { if (jobToDelete) await deleteJobMutation.mutateAsync(jobToDelete.id); }}
      />
    </PageContainer>
  );
}
