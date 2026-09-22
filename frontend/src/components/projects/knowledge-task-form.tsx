"use client";

import * as React from "react";
import { ChevronDown, FileText, Search, Sparkles } from "lucide-react";
import { Select } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
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

const SPLIT_MODE_OPTIONS: ReadonlyArray<{
  value: SplitMode;
  label: string;
}> = [
  { value: "paragraph", label: "按段落" },
  { value: "line", label: "按换行" },
  { value: "sentence", label: "按标点" },
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
  audience,
  onAudienceChange,
  thesis,
  onThesisChange,
  viewerTakeaway,
  onViewerTakeawayChange,
  enableResearch,
  onEnableResearchChange,
}: KnowledgeTaskFormProps) {
  const [showAdditional, setShowAdditional] = React.useState(false);

  return (
    <div className="space-y-4">
      <Tabs
        value={creationMode}
        onValueChange={(value) =>
          onCreationModeChange(value as CreationMode)
        }
      >
        <TabsList
          aria-label="知识视频输入方式"
          className="h-12 w-full rounded-xl bg-secondary/50 p-1"
        >
          <TabsTrigger
            value="generate"
            className="h-10 flex-1 gap-2 text-sm font-medium"
          >
            <Sparkles aria-hidden="true" className="h-4 w-4 text-primary" />
            从主题制作
          </TabsTrigger>
          <TabsTrigger
            value="fixed"
            className="h-10 flex-1 gap-2 text-sm font-medium"
          >
            <FileText aria-hidden="true" className="h-4 w-4 text-primary" />
            使用已有文案
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="space-y-1.5">
        <label
          htmlFor="studio-task-topic"
          className="flex items-center gap-1 text-sm font-medium text-foreground"
        >
          <span>{creationMode === "generate" ? "主题" : "视频标题（可选）"}</span>
          {creationMode === "generate" && (
            <span className="text-destructive">*</span>
          )}
        </label>
        <Input
          id="studio-task-topic"
          placeholder={
            creationMode === "generate" ? "想讲清楚什么？" : "不填则从文案生成"
          }
          value={taskTitle}
          onChange={(event) => onTaskTitleChange(event.target.value)}
          required={creationMode === "generate"}
          className="h-10 text-sm"
        />
      </div>

      {creationMode === "fixed" && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="studio-fixed-script"
              className="text-sm font-medium text-foreground"
            >
              已有文案 <span className="text-destructive">*</span>
            </label>
            <span className="text-xs text-muted-foreground">
              {rawScript.length} 字
            </span>
          </div>
          <Textarea
            id="studio-fixed-script"
            placeholder="粘贴完整文案"
            value={rawScript}
            onChange={(event) => onRawScriptChange(event.target.value)}
            rows={7}
            required
            className="text-sm leading-relaxed"
          />
        </div>
      )}

      <div className="border-t border-border pt-3">
        <button
          type="button"
          onClick={() => setShowAdditional((value) => !value)}
          aria-expanded={showAdditional}
          aria-controls="knowledge-additional-fields"
          className="flex min-h-11 w-full items-center justify-between rounded-lg px-1 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <span>补充要求</span>
          <ChevronDown
            aria-hidden="true"
            className={`h-4 w-4 transition-transform ${showAdditional ? "rotate-180" : ""}`}
          />
        </button>
        {showAdditional && (
          <div
            id="knowledge-additional-fields"
            className="mt-3 space-y-4 rounded-xl border border-border bg-card/40 p-4"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <label
                htmlFor="studio-knowledge-audience"
                className="space-y-1.5 text-sm font-medium"
              >
                面向谁
                <Input
                  id="studio-knowledge-audience"
                  placeholder="默认：普通观众"
                  value={audience}
                  onChange={(event) => onAudienceChange(event.target.value)}
                  className="h-9 text-sm"
                />
              </label>
              <label
                htmlFor="studio-knowledge-genre"
                className="space-y-1.5 text-sm font-medium"
              >
                知识方向
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
              </label>
            </div>

            {creationMode === "generate" ? (
              <>
                <label
                  htmlFor="studio-knowledge-thesis"
                  className="block space-y-1.5 text-sm font-medium"
                >
                  核心主张
                  <Textarea
                    id="studio-knowledge-thesis"
                    placeholder="希望观众理解的结论"
                    value={thesis}
                    onChange={(event) => onThesisChange(event.target.value)}
                    rows={2}
                    className="text-sm"
                  />
                </label>
                <label
                  htmlFor="studio-knowledge-takeaway"
                  className="block space-y-1.5 text-sm font-medium"
                >
                  观众收获
                  <Textarea
                    id="studio-knowledge-takeaway"
                    placeholder="看完能知道或做到什么"
                    value={viewerTakeaway}
                    onChange={(event) =>
                      onViewerTakeawayChange(event.target.value)
                    }
                    rows={2}
                    className="text-sm"
                  />
                </label>
              </>
            ) : (
              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">分镜拆分方式</legend>
                <div className="grid grid-cols-3 gap-2">
                  {SPLIT_MODE_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => onSplitModeChange(option.value)}
                      aria-pressed={splitMode === option.value}
                      className={`min-h-11 rounded-lg border px-2 text-sm ${
                        splitMode === option.value
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border text-muted-foreground hover:bg-secondary/60"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            )}

            <label
              htmlFor="studio-research"
              className="flex min-h-11 cursor-pointer items-center justify-between rounded-lg border border-border px-3 text-sm"
            >
              <span className="flex items-center gap-2">
                <Search aria-hidden="true" className="h-4 w-4 text-primary" />
                联网核验
              </span>
              <input
                id="studio-research"
                type="checkbox"
                checked={enableResearch}
                onChange={(event) =>
                  onEnableResearchChange(event.target.checked)
                }
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
              />
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
