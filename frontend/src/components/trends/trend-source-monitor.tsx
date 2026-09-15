"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Loader2, RefreshCw, WifiOff } from "lucide-react";
import type { TrendRun, TrendSourceCatalog } from "@/lib/types";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { cn, formatDate } from "@/lib/utils";

export interface PlatformMeta {
  value: string;
  label: string;
  badgeClass: string;
  dotClass: string;
}

export const PLATFORMS_CONFIG: Record<string, PlatformMeta> = {
  all: { value: "all", label: "全部平台", badgeClass: "bg-secondary text-foreground", dotClass: "bg-primary" },
  weibo: { value: "weibo", label: "微博", badgeClass: "bg-rose-500/10 text-rose-500 border-rose-500/20", dotClass: "bg-rose-500" },
  douyin: { value: "douyin", label: "抖音", badgeClass: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20", dotClass: "bg-cyan-400" },
  xiaohongshu: { value: "xiaohongshu", label: "小红书", badgeClass: "bg-red-500/10 text-red-500 border-red-500/20", dotClass: "bg-red-500" },
  zhihu: { value: "zhihu", label: "知乎", badgeClass: "bg-blue-500/10 text-blue-500 border-blue-500/20", dotClass: "bg-blue-500" },
  bilibili: { value: "bilibili", label: "B 站", badgeClass: "bg-pink-500/10 text-pink-400 border-pink-500/20", dotClass: "bg-pink-400" },
  toutiao: { value: "toutiao", label: "头条", badgeClass: "bg-orange-500/10 text-orange-500 border-orange-500/20", dotClass: "bg-orange-500" },
  baidu: { value: "baidu", label: "百度", badgeClass: "bg-indigo-500/10 text-indigo-400 border-indigo-400/20", dotClass: "bg-indigo-400" },
};

export const PLATFORM_OPTIONS = Object.values(PLATFORMS_CONFIG);

function runStatusLabel(status?: string) {
  if (status === "fresh" || status === "completed") return "正常";
  if (status === "stale" || status === "partial") return "部分过期";
  if (status === "failed") return "失败";
  if (status === "unavailable") return "不可用";
  if (status === "running") return "采集中";
  return "未采集";
}

function runStatusTone(status?: string): StatusTone {
  if (status === "fresh" || status === "completed") return "success";
  if (status === "stale" || status === "partial") return "warning";
  if (status === "failed" || status === "unavailable") return "destructive";
  if (status === "running") return "primary";
  return "neutral";
}

function sourceConfigurationLabel(source: TrendSourceCatalog) {
  if (source.primary_available && source.fallback_available) return "主源 + 备用源";
  if (source.primary_available) return "仅主源";
  if (source.fallback_available) return "仅备用源";
  return "未配置";
}

// 来源监控
export interface TrendSourceMonitorCardProps {
  onRefresh: () => void;
  isRefreshing: boolean;
}

export function TrendSourceMonitorCard({
  onRefresh,
  isRefreshing,
}: TrendSourceMonitorCardProps) {

  const sourcesQuery = useQuery<TrendSourceCatalog[]>({
    queryKey: ["trend-sources"],
    queryFn: () => api.listTrendSources(),
  });
  const runsQuery = useQuery<TrendRun[]>({
    queryKey: ["trend-runs", 5],
    queryFn: () => api.listTrendRuns(5),
  });

  const catalog = sourcesQuery.data || [];
  const latestRun = runsQuery.data?.[0];
  const latestSources = new Map((latestRun?.sources || []).map((source) => [source.source_key, source]));
  const isLoading = sourcesQuery.isLoading || runsQuery.isLoading;

  return (
    <Card className="glass-card">
      <CardHeader className="border-b border-border/60 pb-3.5">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              来源状态
            </CardTitle>
            <CardDescription>
              监测公开热榜各平台的连通性与新鲜度。
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {latestRun && (
              <StatusBadge
                label={runStatusLabel(latestRun.status)}
                tone={runStatusTone(latestRun.status)}
                showDot={false}
              />
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={onRefresh}
              disabled={isRefreshing || isLoading}
              className="gap-1.5"
            >
              {isRefreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              检查来源
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3.5 p-4 sm:p-5">
        {isLoading ? (
          <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground justify-center">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span>读取数据源状态…</span>
          </div>
        ) : catalog.length === 0 ? (
          <EmptyState icon={WifiOff} title="暂无数据源" description="请检查后端数据源配置" />
        ) : (
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {catalog.map((source) => {
              const health = latestSources.get(source.source_key);
              const config = PLATFORMS_CONFIG[source.platform] || {
                badgeClass: "bg-secondary text-foreground",
                dotClass: "bg-primary",
              };
              return (
                <div
                  key={source.source_key}
                  className="flex flex-col justify-between rounded-xl border border-border/70 bg-secondary/25 p-3 hover:border-primary/40 transition-colors"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className={cn("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold border", config.badgeClass)}>
                        <span className={cn("h-1.5 w-1.5 rounded-full", config.dotClass)} />
                        {source.platform_label}
                      </span>
                      <StatusBadge
                        label={health ? runStatusLabel(health.status) : "未执行"}
                        tone={runStatusTone(health?.status)}
                        showDot={false}
                        className="text-[11px]"
                      />
                    </div>
                    <div className="mt-2 font-mono text-sm font-semibold tabular-nums text-foreground">
                      {health ? `${health.item_count} 条` : "—"}
                    </div>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {sourceConfigurationLabel(source)}
                    </p>
                  </div>
                  {health?.error_message && (
                    <div className="mt-1.5 rounded bg-destructive/10 border border-destructive/20 p-1 text-[11px] text-destructive leading-tight line-clamp-2">
                      {health.error_message}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {latestRun?.fetched_at && (
          <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t border-border/50">
            <span>
              最近采集：
              <strong className="font-mono text-foreground ml-1">{formatDate(latestRun.fetched_at)}</strong>
            </span>
            <span className="font-mono text-[11px]">
              成功: {latestRun.success_count} / 过期: {latestRun.stale_count} / 失败: {latestRun.error_count}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
