"use client";

import { Select } from "@/components/ui/field";
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
    <div className="space-y-4">
      <label
        htmlFor="commerce-task-title"
        className="block space-y-1.5 text-sm font-medium text-foreground"
      >
        视频标题（可选）
        <Input
          id="commerce-task-title"
          value={taskTitle}
          onChange={(event) => onTaskTitleChange(event.target.value)}
          placeholder="不填则使用默认标题"
          className="h-10 text-sm"
        />
      </label>
      <label
        htmlFor="commerce-creative-angle"
        className="block space-y-1.5 text-sm font-medium text-foreground"
      >
        创意角度
        <Select
          id="commerce-creative-angle"
          value={creativeAngle}
          onChange={(event) =>
            onCreativeAngleChange(event.target.value as CreativeAngle)
          }
          className="h-10 text-sm"
        >
          {CREATIVE_ANGLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </label>
    </div>
  );
}
