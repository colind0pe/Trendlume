"use client";

import { ShoppingBag } from "lucide-react";

import { Input } from "@/components/ui/input";
import { CREATIVE_ANGLE_OPTIONS } from "@/lib/ui-constants";
import type { CreativeAngle } from "@/lib/types";

export interface CommerceTaskFormProps {
  creativeAngle: CreativeAngle;
  onCreativeAngleChange: (value: CreativeAngle) => void;
  taskTitle: string;
  onTaskTitleChange: (value: string) => void;
}

export function CommerceTaskForm({
  creativeAngle,
  onCreativeAngleChange,
  taskTitle,
  onTaskTitleChange,
}: CommerceTaskFormProps) {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <ShoppingBag className="h-4 w-4 text-amber-500" />
          Commerce 商品视频
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          使用当前 Project 的主商品 Truth Sheet 与素材。本条 Task 只定义创意角度和具体表达。
        </p>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="commerce-task-title" className="text-sm font-medium text-foreground">
          视频标题
        </label>
        <Input
          id="commerce-task-title"
          value={taskTitle}
          onChange={(event) => onTaskTitleChange(event.target.value)}
          placeholder="例如：新品核心卖点短视频"
          className="h-10 text-sm"
        />
      </div>

      <div className="space-y-2">
        <div>
          <span className="text-sm font-medium text-foreground">创意角度</span>
          <p className="mt-1 text-xs text-muted-foreground">商品事实始终以 Project Truth Sheet 为准。</p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {CREATIVE_ANGLE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onCreativeAngleChange(option.value)}
              aria-pressed={creativeAngle === option.value}
              className={`rounded-lg border p-3 text-left transition-colors ${
                creativeAngle === option.value
                  ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary/70"
                  : "border-border bg-card text-muted-foreground hover:bg-secondary/60"
              }`}
            >
              <div className="text-sm font-medium">{option.label}</div>
              <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{option.description}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
