"use client";

import Link from "next/link";
import { Clapperboard } from "lucide-react";
import { Button } from "@/components/ui/button";

export function DramaTaskLauncher({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  return (
    <section className="flex min-h-72 flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <span className="rounded-2xl border border-primary/20 bg-primary/10 p-4 text-primary">
        <Clapperboard className="h-6 w-6" aria-hidden="true" />
      </span>
      <div className="max-w-lg">
        <h2 className="text-base font-semibold text-foreground">进入 Drama creation workspace</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Drama 从故事或已有剧本开始，经过 Bible、角色与场景、Episode、逐 Shot Storyboard 和批准门槛后，才创建 Production Task。
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" onClick={onClose}>取消</Button>
        <Link href={`/projects/${projectId}/drama`} onClick={onClose}>
          <Button type="button">打开 Drama workspace</Button>
        </Link>
      </div>
    </section>
  );
}
