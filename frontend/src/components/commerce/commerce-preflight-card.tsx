"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api-client";
import type { CommercePreflightResponse } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function CommercePreflightCard({ taskId, busy }: { taskId: string; busy: boolean }) {
  const query = useQuery<CommercePreflightResponse>({
    queryKey: ["commerce-preflight", taskId],
    queryFn: () => api.getCommercePreflight(taskId),
    enabled: !busy,
    refetchOnWindowFocus: false,
  });

  return (
    <Card className="border-primary/20 bg-primary/[0.02]">
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm">
              <ShieldCheck className="h-4 w-4 text-primary" />Commerce Preflight QA
            </CardTitle>
            <CardDescription className="mt-1">发布前检查商品展示、主张来源、动态事实、CTA、Scene 重复和媒体质量。</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {query.data && (
              <Badge variant={query.data.status === "fail" ? "destructive" : query.data.status === "warning" ? "warning" : "success"}>
                {query.data.status === "fail" ? "需修复" : query.data.status === "warning" ? "有提醒" : "通过"}
              </Badge>
            )}
            <Button type="button" size="sm" variant="outline" onClick={() => query.refetch()} disabled={busy || query.isFetching} className="gap-1.5">
              {query.isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}重新检查
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <div className="h-12 animate-pulse rounded-lg bg-secondary/50" />
        ) : query.data?.findings.length ? (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {query.data.findings.filter((finding) => finding.severity !== "pass").slice(0, 8).map((finding) => (
              <div key={`${finding.code}-${finding.message}`} className={`rounded-lg border px-3 py-2 text-xs ${finding.severity === "error" ? "border-destructive/30 bg-destructive/5" : "border-warning/30 bg-warning/5"}`}>
                <div className="flex items-center gap-2 font-semibold text-foreground"><span className={`h-1.5 w-1.5 rounded-full ${finding.severity === "error" ? "bg-destructive" : "bg-warning"}`} />{finding.code}</div>
                <p className="mt-1 leading-relaxed text-muted-foreground">{finding.message}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">暂无 QA 结果，点击“重新检查”开始。</p>
        )}
      </CardContent>
    </Card>
  );
}
