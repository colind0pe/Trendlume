"use client";

import * as React from "react";
import { FileText, Search, Sparkles } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GENRE_OPTIONS } from "@/lib/ui-constants";

type CreationMode = "generate" | "fixed";
type SplitMode = "paragraph" | "line" | "sentence";

export interface KnowledgeTaskFormProps {
  creationMode: CreationMode;
  onCreationModeChange: (mode: CreationMode) => void;
  taskTitle: string;
  onTaskTitleChange: (value: string) => void;
  rawScript: string;
  onRawScriptChange: (value: string) => void;
  splitMode: SplitMode;
  onSplitModeChange: (mode: SplitMode) => void;
  taskGenre: string;
  onTaskGenreChange: (value: string) => void;
  audience: string;
  onAudienceChange: (value: string) => void;
  thesis: string;
  onThesisChange: (value: string) => void;
  viewerTakeaway: string;
  onViewerTakeawayChange: (value: string) => void;
  enableResearch: boolean;
  onEnableResearchChange: (value: boolean) => void;
}

export function KnowledgeTaskForm({
  creationMode,
  onCreationModeChange,
  taskTitle,
  onTaskTitleChange,
  rawScript,
  onRawScriptChange,
  splitMode,
  onSplitModeChange,
  taskGenre,
  onTaskGenreChange,
  audience,
  onAudienceChange,
  thesis,
  onThesisChange,
  viewerTakeaway,
  onViewerTakeawayChange,
  enableResearch,
  onEnableResearchChange,
}: KnowledgeTaskFormProps) {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-primary/20 bg-primary/[0.04] px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Sparkles className="h-4 w-4 text-primary" />
          知识视频制作
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          先明确观众要理解什么，再由系统规划论点、来源和画面逻辑。风格与技术选项可稍后调整。
        </p>
      </div>

      <Tabs
        value={creationMode}
        onValueChange={(value) => onCreationModeChange(value as CreationMode)}
        className="space-y-0"
      >
        <TabsList aria-label="知识视频输入方式" className="w-full h-10 p-1 bg-secondary/50 rounded-xl">
          <TabsTrigger value="generate" className="flex-1 gap-2 text-sm font-medium h-8">
            <Sparkles className="h-4 w-4 text-primary" />
            从主题制作
          </TabsTrigger>
          <TabsTrigger value="fixed" className="flex-1 gap-2 text-sm font-medium h-8">
            <FileText className="h-4 w-4 text-primary" />
            使用已有文案
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="space-y-1.5">
        <label htmlFor="studio-task-topic" className="text-sm font-medium text-foreground flex items-center gap-1">
          <span>{creationMode === "generate" ? "主题 / 要回答的问题" : "视频标题（可选）"}</span>
          {creationMode === "generate" && <span className="text-destructive">*</span>}
        </label>
        <Input
          id="studio-task-topic"
          placeholder="例如：为什么量子纠缠被称为鬼魅般的超距作用？"
          value={taskTitle}
          onChange={(event) => onTaskTitleChange(event.target.value)}
          required={creationMode === "generate"}
          className="h-10 text-sm px-3.5"
        />
      </div>

      {creationMode === "generate" ? (
        <div className="space-y-3.5 rounded-xl border border-border/80 bg-card/40 p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div className="space-y-1.5">
              <label htmlFor="studio-knowledge-audience" className="text-sm font-medium text-foreground">
                面向谁
              </label>
              <Input
                id="studio-knowledge-audience"
                placeholder="例如：第一次接触量子力学的普通观众"
                value={audience}
                onChange={(event) => onAudienceChange(event.target.value)}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="studio-knowledge-genre" className="text-sm font-medium text-foreground">
                知识方向
              </label>
              <Select
                id="studio-knowledge-genre"
                value={taskGenre}
                onChange={(event) => onTaskGenreChange(event.target.value)}
                className="h-9 text-sm"
              >
                {GENRE_OPTIONS.map((genre) => (
                  <option key={genre.value} value={genre.value}>
                    {genre.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="studio-knowledge-thesis" className="text-sm font-medium text-foreground">
              核心主张
            </label>
            <Textarea
              id="studio-knowledge-thesis"
              placeholder="用一句话说清这条视频希望观众理解的核心结论"
              value={thesis}
              onChange={(event) => onThesisChange(event.target.value)}
              rows={2}
              className="text-sm leading-relaxed p-3"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="studio-knowledge-takeaway" className="text-sm font-medium text-foreground">
              观众看完应该带走什么
            </label>
            <Textarea
              id="studio-knowledge-takeaway"
              placeholder="例如：能用一次简单实验解释纠缠不是超光速传信"
              value={viewerTakeaway}
              onChange={(event) => onViewerTakeawayChange(event.target.value)}
              rows={2}
              className="text-sm leading-relaxed p-3"
            />
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="studio-fixed-script" className="text-sm font-medium text-foreground flex items-center gap-1">
                <span>完整口播 / 解说文案</span>
                <span className="text-destructive">*</span>
              </label>
              <span className="text-xs text-muted-foreground font-mono">{rawScript.length} 字</span>
            </div>
            <Textarea
              id="studio-fixed-script"
              placeholder="粘贴已有知识视频文案，系统会保留文案流程并补充分镜视觉角色。"
              value={rawScript}
              onChange={(event) => onRawScriptChange(event.target.value)}
              rows={7}
              required
              className="text-sm leading-relaxed p-3"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div className="space-y-1.5">
              <label htmlFor="studio-knowledge-audience-fixed" className="text-sm font-medium text-foreground">
                面向谁（可选）
              </label>
              <Input
                id="studio-knowledge-audience-fixed"
                placeholder="例如：普通观众"
                value={audience}
                onChange={(event) => onAudienceChange(event.target.value)}
                className="h-9 text-sm"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="studio-knowledge-genre-fixed" className="text-sm font-medium text-foreground">
                知识方向
              </label>
              <Select
                id="studio-knowledge-genre-fixed"
                value={taskGenre}
                onChange={(event) => onTaskGenreChange(event.target.value)}
                className="h-9 text-sm"
              >
                {GENRE_OPTIONS.map((genre) => (
                  <option key={genre.value} value={genre.value}>
                    {genre.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <span className="text-sm font-medium text-foreground">分镜拆分规则</span>
            <div className="grid grid-cols-3 gap-2.5">
              {[
                { mode: "paragraph" as const, label: "按段落", desc: "空行分镜" },
                { mode: "line" as const, label: "按换行", desc: "单行一镜" },
                { mode: "sentence" as const, label: "按标点", desc: "语义断句" },
              ].map((item) => (
                <button
                  key={item.mode}
                  type="button"
                  onClick={() => onSplitModeChange(item.mode)}
                  aria-pressed={splitMode === item.mode}
                  className={`p-2.5 rounded-lg border text-left transition-colors cursor-pointer ${
                    splitMode === item.mode
                      ? "border-primary bg-primary/5 text-foreground ring-1 ring-primary"
                      : "border-border bg-card text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                  }`}
                >
                  <div className="text-sm font-medium text-foreground">{item.label}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{item.desc}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <label
        htmlFor="studio-research"
        className="flex cursor-pointer items-center justify-between rounded-lg border border-border/80 bg-secondary/25 px-3.5 py-2.5 text-sm transition-colors hover:bg-secondary/45"
      >
        <div className="flex items-center gap-2.5">
          <Search className="h-4 w-4 text-primary shrink-0" />
          <div>
            <span className="font-medium text-foreground">联网核验来源</span>
            <span className="block text-xs text-muted-foreground mt-0.5">
              为关键主张保留来源关系，生成后可在分镜中复核
            </span>
          </div>
        </div>
        <input
          id="studio-research"
          type="checkbox"
          checked={enableResearch}
          onChange={(event) => onEnableResearchChange(event.target.checked)}
          className="rounded border-border text-primary focus:ring-primary h-4 w-4 cursor-pointer"
        />
      </label>
    </div>
  );
}
