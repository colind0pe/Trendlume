"use client";

import * as React from "react";
import { ChevronDown, FileText, Globe, SlidersHorizontal, Sparkles } from "lucide-react";
import { Select } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GENRE_OPTIONS, HOOK_OPTIONS } from "@/lib/ui-constants";

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
  hookType: string;
  onHookTypeChange: (value: string) => void;
  enableResearch: boolean;
  onEnableResearchChange: (value: boolean) => void;
  audience?: string;
  onAudienceChange?: (value: string) => void;
  thesis?: string;
  onThesisChange?: (value: string) => void;
  viewerTakeaway?: string;
  onViewerTakeawayChange?: (value: string) => void;
}

const SPLIT_MODE_OPTIONS: ReadonlyArray<{
  value: SplitMode;
  label: string;
  desc: string;
}> = [
  { value: "paragraph", label: "按段落", desc: "一段为一镜" },
  { value: "line", label: "按换行", desc: "一行一镜" },
  { value: "sentence", label: "按标点", desc: "按句拆分" },
];

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
  hookType,
  onHookTypeChange,
  enableResearch,
  onEnableResearchChange,
  audience,
  onAudienceChange,
  thesis,
  onThesisChange,
  viewerTakeaway,
  onViewerTakeawayChange,
}: KnowledgeTaskFormProps) {
  const [showAudienceBrief, setShowAudienceBrief] = React.useState(false);

  return (
    <div className="space-y-4">
      {/* 1. Input Mode Tabs */}
      <Tabs
        value={creationMode}
        onValueChange={(value) => onCreationModeChange(value as CreationMode)}
      >
        <TabsList
          aria-label="知识视频输入方式"
          className="h-11 w-full rounded-xl bg-secondary/50 p-1"
        >
          <TabsTrigger
            value="generate"
            className="h-9 flex-1 gap-2 text-sm font-medium"
          >
            <Sparkles aria-hidden="true" className="h-4 w-4 text-primary" />
            从主题制作
          </TabsTrigger>
          <TabsTrigger
            value="fixed"
            className="h-9 flex-1 gap-2 text-sm font-medium"
          >
            <FileText aria-hidden="true" className="h-4 w-4 text-primary" />
            使用已有文案
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* 2. Core Content Input */}
      {creationMode === "generate" ? (
        <div className="space-y-1.5">
          <label
            htmlFor="studio-task-topic"
            className="block text-sm font-medium text-foreground"
          >
            <span>
              核心主题 <span className="text-destructive">*</span>
            </span>
          </label>
          <Input
            id="studio-task-topic"
            placeholder="例如：为什么天空是蓝色的？"
            value={taskTitle}
            onChange={(event) => onTaskTitleChange(event.target.value)}
            required
            className="h-10 text-sm"
          />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <label
              htmlFor="studio-task-title-optional"
              className="text-sm font-medium text-foreground"
            >
              视频标题（可选）
            </label>
            <Input
              id="studio-task-title-optional"
              placeholder="不填则自动生成"
              value={taskTitle}
              onChange={(event) => onTaskTitleChange(event.target.value)}
              className="h-9 text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="studio-fixed-script"
                className="text-sm font-medium text-foreground"
              >
                文案正文 <span className="text-destructive">*</span>
              </label>
              <span className="text-xs text-muted-foreground">
                {rawScript.length} 字
              </span>
            </div>
            <Textarea
              id="studio-fixed-script"
              placeholder="粘贴您的完整文案或解说词…"
              value={rawScript}
              onChange={(event) => onRawScriptChange(event.target.value)}
              rows={6}
              required
              className="text-sm leading-relaxed"
            />
          </div>

          {/* Split Mode Selector */}
          <fieldset className="space-y-1.5">
            <legend className="text-xs font-medium text-muted-foreground">
              分镜切分依据
            </legend>
            <div className="grid grid-cols-3 gap-2">
              {SPLIT_MODE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onSplitModeChange(option.value)}
                  aria-pressed={splitMode === option.value}
                  className={`rounded-lg border p-2 text-left transition-all cursor-pointer ${
                    splitMode === option.value
                      ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary/60"
                      : "border-border bg-card text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                  }`}
                >
                  <div className="text-xs font-semibold">{option.label}</div>
                  <div className="text-[11px] text-muted-foreground truncate mt-0.5">
                    {option.desc}
                  </div>
                </button>
              ))}
            </div>
          </fieldset>
        </div>
      )}

      {/* 3. Content Preferences & Verification */}
      <section
        className="space-y-3 rounded-xl border border-border/80 bg-card/50 p-3.5"
        aria-labelledby="knowledge-preferences-heading"
      >
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3
            id="knowledge-preferences-heading"
            className="text-sm font-semibold text-foreground"
          >
            表达倾向与真实性
          </h3>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label
              htmlFor="studio-knowledge-genre"
              className="text-xs font-medium text-muted-foreground"
            >
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

          <div className="space-y-1">
            <label
              htmlFor="studio-knowledge-hook"
              className="text-xs font-medium text-muted-foreground"
            >
              开场表达
            </label>
            <Select
              id="studio-knowledge-hook"
              value={hookType}
              onChange={(event) => onHookTypeChange(event.target.value)}
              className="h-9 text-sm"
            >
              {HOOK_OPTIONS.map((hook) => (
                <option key={hook.value} value={hook.value}>
                  {hook.label}
                </option>
              ))}
            </Select>
          </div>
        </div>

        {/* Fact check toggle */}
        <label
          htmlFor="studio-research"
          className="flex cursor-pointer items-center justify-between rounded-lg border border-border bg-card/80 px-3 py-2.5 transition-colors hover:bg-secondary/40"
        >
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <Globe aria-hidden="true" className="h-3.5 w-3.5 text-primary" />
            <span>联网事实核验</span>
          </div>
          <input
            id="studio-research"
            type="checkbox"
            checked={enableResearch}
            onChange={(event) => onEnableResearchChange(event.target.checked)}
            className="h-4 w-4 shrink-0 rounded border-border text-primary focus:ring-primary cursor-pointer accent-primary"
          />
        </label>

        {/* Optional Audience & Thesis details */}
        {(onAudienceChange || onThesisChange || onViewerTakeawayChange) && (
          <div className="pt-1 border-t border-border/60">
            <button
              type="button"
              onClick={() => setShowAudienceBrief((v) => !v)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer py-1"
            >
              <span>补充受众与核心主张（可选）</span>
              <ChevronDown
                aria-hidden="true"
                className={`h-3 w-3 transition-transform ${showAudienceBrief ? "rotate-180" : ""}`}
              />
            </button>
            {showAudienceBrief && (
              <div className="mt-2 space-y-2.5 pt-1">
                {onAudienceChange && (
                  <div className="space-y-1">
                    <label htmlFor="studio-knowledge-audience" className="text-xs font-medium text-muted-foreground">
                      目标观众
                    </label>
                    <Input
                      id="studio-knowledge-audience"
                      placeholder="普通大众 / 行业从业者"
                      value={audience || ""}
                      onChange={(e) => onAudienceChange(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                )}
                {onThesisChange && (
                  <div className="space-y-1">
                    <label htmlFor="studio-knowledge-thesis" className="text-xs font-medium text-muted-foreground">
                      核心主张
                    </label>
                    <Input
                      id="studio-knowledge-thesis"
                      placeholder="核心论点或主张（可选）"
                      value={thesis || ""}
                      onChange={(e) => onThesisChange(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                )}
                {onViewerTakeawayChange && (
                  <div className="space-y-1">
                    <label htmlFor="studio-knowledge-takeaway" className="text-xs font-medium text-muted-foreground">
                      观众收获
                    </label>
                    <Input
                      id="studio-knowledge-takeaway"
                      placeholder="观众收获要点（可选）"
                      value={viewerTakeaway || ""}
                      onChange={(e) => onViewerTakeawayChange(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
