"use client";

import Link from "next/link";
import { ArrowRight, Clapperboard, FolderKanban } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";

export default function DramaIndexPage() {
  const projectsQuery = useQuery({ queryKey: ["projects"], queryFn: () => api.listProjects() });

  return (
    <PageContainer width="wide" className="space-y-6">
      <PageHeader
        title="Drama 工作室"
        description="从故事想法或已有剧本，完成 Bible、角色与场景锁定、单集剧本和逐 Shot Storyboard。"
        actions={(
          <div className="inline-flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/[0.06] px-3 py-2 text-xs text-primary">
            <Clapperboard className="h-4 w-4" aria-hidden="true" />
            <span>前期制片 · 不生成视频</span>
          </div>
        )}
      />

      {projectsQuery.isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((item) => <div key={item} className="h-44 animate-pulse rounded-2xl border border-border/60 bg-card/40" />)}
        </div>
      ) : projectsQuery.data?.length ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projectsQuery.data.map((project) => (
            <Card key={project.id} className="group rounded-2xl transition-colors hover:border-primary/35">
              <CardHeader>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <FolderKanban className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="truncate text-base">{project.name}</CardTitle>
                      <CardDescription className="mt-1">{project.aspect_ratio} · Drama workspace</CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="min-h-10 line-clamp-2 text-sm leading-5 text-muted-foreground">
                  {project.description || "进入项目，创建或继续一个 Drama Bible。"}
                </p>
                <Link
                  href={`/projects/${project.id}/drama`}
                  className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-border/80 bg-card/50 px-3.5 text-sm font-medium leading-none text-foreground transition-all duration-150 hover:border-foreground/20 hover:bg-secondary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-[0.98]"
                >
                  打开 Drama workspace
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={FolderKanban}
          title="还没有项目"
          description="先创建一个项目，再进入 Drama workspace 开始前期制片。"
          action={<Link href="/projects" className="inline-flex h-9 items-center justify-center rounded-lg bg-primary px-3.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">前往项目库</Link>}
        />
      )}
    </PageContainer>
  );
}
