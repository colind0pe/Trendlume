"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock3, Loader2, ShieldAlert, Smartphone } from "lucide-react";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";

interface VerificationModalProps {
  filterJobId?: string;
}

export function VerificationModal({ filterJobId }: VerificationModalProps) {
  const queryClient = useQueryClient();
  const [code, setCode] = React.useState("");
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);
  const [dismissedRequestId, setDismissedRequestId] = React.useState<string | null>(null);

  const { data: pendingList = [] } = useQuery({
    queryKey: ["pending-verifications"],
    queryFn: () => api.getPendingVerifications(),
    refetchInterval: (query) => {
      const pending = query.state.data;
      return Array.isArray(pending) && pending.length > 0 ? 2000 : false;
    },
  });

  const activeRequest = React.useMemo(() => {
    const candidate = filterJobId
      ? pendingList.find((request) => request.job_id === filterJobId)
      : pendingList[0];
    if (!candidate || candidate.request_id === dismissedRequestId) return null;
    return candidate;
  }, [pendingList, filterJobId, dismissedRequestId]);

  React.useEffect(() => {
    if (dismissedRequestId && !pendingList.some((request) => request.request_id === dismissedRequestId)) {
      setDismissedRequestId(null);
    }
  }, [dismissedRequestId, pendingList]);

  const [countdown, setCountdown] = React.useState(120);

  React.useEffect(() => {
    if (activeRequest) {
      setCountdown(activeRequest.remaining_seconds);
      setCode("");
      setErrorMsg(null);
    }
  }, [activeRequest?.request_id]);

  React.useEffect(() => {
    if (!activeRequest) return;
    const timer = setInterval(() => {
      setCountdown((previous) => {
        if (previous <= 1) {
          clearInterval(timer);
          queryClient.invalidateQueries({ queryKey: ["pending-verifications"] });
          return 0;
        }
        return previous - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [activeRequest, queryClient]);

  const submitMutation = useMutation({
    mutationFn: ({ requestId, codeVal }: { requestId: string; codeVal: string }) =>
      api.submitVerificationCode(requestId, codeVal),
    onSuccess: () => {
      if (activeRequest) setDismissedRequestId(activeRequest.request_id);
      queryClient.invalidateQueries({ queryKey: ["pending-verifications"] });
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
      setCode("");
      setErrorMsg(null);
    },
    onError: (error: any) => {
      setErrorMsg(error.message || "提交验证码失败，请重试");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (requestId: string) => api.cancelVerification(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-verifications"] });
      queryClient.invalidateQueries({ queryKey: ["publishing-jobs"] });
    },
  });

  const handleCancel = () => {
    if (!activeRequest || cancelMutation.isPending || submitMutation.isPending) return;
    setDismissedRequestId(activeRequest.request_id);
    cancelMutation.mutate(activeRequest.request_id);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!code.trim()) {
      setErrorMsg("请输入手机短信验证码");
      return;
    }
    if (!activeRequest) return;
    submitMutation.mutate({ requestId: activeRequest.request_id, codeVal: code.trim() });
  };

  if (!activeRequest) return null;

  return (
    <Dialog open={true} onOpenChange={(open) => !open && handleCancel()} className="max-w-md">
      <DialogHeader>
        <DialogTitle className="flex items-start gap-3 pr-6">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-warning-soft/80 backdrop-blur-sm text-warning shadow-xs border border-warning/25">
            <Smartphone aria-hidden="true" className="h-5 w-5" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <span>抖音发布验证</span>
              <StatusBadge
                tone={countdown > 0 ? "warning" : "destructive"}
                label={
                  <span className="inline-flex items-center gap-1" aria-live="polite">
                    <Clock3 aria-hidden="true" className="h-3.5 w-3.5" />
                    {countdown > 0 ? `剩余 ${countdown} 秒` : "已过期"}
                  </span>
                }
              />
            </span>
            <span className="mt-1 block text-xs font-normal text-muted-foreground">
              账号：{activeRequest.account_name || "抖音创作者"}
            </span>
          </span>
        </DialogTitle>
        <DialogDescription>
          请输入抖音向绑定手机发送的 6 位短信验证码以继续发布。
        </DialogDescription>
      </DialogHeader>

      <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-info/25 bg-info-soft/60 backdrop-blur-sm px-3.5 py-2.5 text-sm text-info shadow-xs">
        <ShieldAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
        <span className="leading-relaxed">这是抖音发布过程中的安全验证，不会保存短信验证码。</span>
      </div>

      {errorMsg && (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-destructive/30 bg-destructive-soft/70 backdrop-blur-sm px-3.5 py-2.5 text-sm text-destructive shadow-xs" role="alert">
          <ShieldAlert aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="leading-relaxed">{errorMsg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="短信验证码" htmlFor="verification-code" error={errorMsg || undefined}>
          <Input
            id="verification-code"
            type="text"
            autoFocus
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="请输入 6 位验证码"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className="h-12 text-center font-mono text-xl tracking-[0.4em] font-semibold"
            maxLength={10}
            disabled={submitMutation.isPending || cancelMutation.isPending}
            aria-invalid={Boolean(errorMsg)}
            aria-describedby={errorMsg ? "verification-code-error" : undefined}
          />
        </Field>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={cancelMutation.isPending || submitMutation.isPending}
          >
            取消
          </Button>
          <Button type="submit" disabled={submitMutation.isPending || cancelMutation.isPending || countdown <= 0} className="gap-1.5">
            {submitMutation.isPending ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <CheckCircle2 aria-hidden="true" className="h-4 w-4" />}
            {submitMutation.isPending ? "提交中…" : "确认提交验证"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
