"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type Detail = Record<string, unknown> & { type: "knowledge" | "commerce" | "drama" };

function Field({ label, value, onChange, multiline = false }: { label: string; value: unknown; onChange: (value: string) => void; multiline?: boolean }) {
  const control = multiline
    ? <Textarea value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} />
    : <Input value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} />;
  return <label className="space-y-1.5 text-sm font-medium"><span>{label}</span>{control}</label>;
}

function JsonField({ label, value, onChange }: { label: string; value: unknown; onChange: (value: unknown) => void }) {
  const [text, setText] = React.useState(() => JSON.stringify(value ?? [], null, 2));
  const [error, setError] = React.useState("");
  React.useEffect(() => setText(JSON.stringify(value ?? [], null, 2)), [value]);
  const validate = () => {
    try { onChange(JSON.parse(text)); setError(""); } catch { setError("请输入有效 JSON。"); }
  };
  return <label className="space-y-1.5 text-sm font-medium"><span>{label}</span><Textarea className="min-h-28 font-mono text-xs" value={text} onChange={(event) => setText(event.target.value)} onBlur={validate} aria-invalid={Boolean(error)} aria-describedby={error ? `${label}-error` : undefined} />{error && <span id={`${label}-error`} className="block text-xs text-destructive">{error}</span>}</label>;
}

export function TaskDetailFields({ detail, onChange }: { detail: Detail; onChange: (detail: Detail) => void }) {
  const set = (key: string, value: unknown) => onChange({ ...detail, [key]: value });
  if (detail.type === "knowledge") return <div className="grid gap-3 md:grid-cols-2">
    <Field label="主题" value={detail.topic} onChange={(value) => set("topic", value)} />
    <Field label="目标受众" value={detail.audience} onChange={(value) => set("audience", value)} />
    <Field label="核心论点" value={detail.thesis} onChange={(value) => set("thesis", value)} multiline />
    <Field label="用户收获" value={detail.takeaway} onChange={(value) => set("takeaway", value)} multiline />
    <JsonField label="事实与论据" value={detail.claims} onChange={(value) => set("claims", value)} />
    <JsonField label="资料来源" value={detail.sources} onChange={(value) => set("sources", value)} />
  </div>;
  if (detail.type === "commerce") return <div className="grid gap-3 md:grid-cols-2">
    <Field label="创意角度" value={detail.creative_angle} onChange={(value) => set("creative_angle", value)} />
    <Field label="目标受众" value={detail.audience} onChange={(value) => set("audience", value)} />
    <Field label="开场 Hook" value={detail.hook} onChange={(value) => set("hook", value)} multiline />
    <Field label="核心信息" value={detail.core_message} onChange={(value) => set("core_message", value)} multiline />
    <Field label="行动号召" value={detail.cta} onChange={(value) => set("cta", value)} />
    <Field label="优惠信息" value={detail.offer} onChange={(value) => set("offer", value)} />
    <JsonField label="选用商品事实" value={detail.selected_claims} onChange={(value) => set("selected_claims", value)} />
    <JsonField label="场景大纲" value={detail.scene_outline} onChange={(value) => set("scene_outline", value)} />
  </div>;
  return <div className="grid gap-3 md:grid-cols-2">
    <label className="space-y-1.5 text-sm font-medium"><span>集数</span><Input type="number" min={1} value={Number(detail.episode_number ?? 1)} onChange={(event) => set("episode_number", Number(event.target.value))} /></label>
    <Field label="本集梗概" value={detail.synopsis} onChange={(value) => set("synopsis", value)} multiline />
    <div className="md:col-span-2"><Field label="剧本" value={detail.script_text} onChange={(value) => set("script_text", value)} multiline /></div>
    <div className="md:col-span-2"><JsonField label="连续性数据" value={detail.continuity_data ?? {}} onChange={(value) => set("continuity_data", value)} /></div>
  </div>;
}
