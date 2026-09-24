"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
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

export function TaskDetailFields({ detail, onChange, projectId }: { detail: Detail; onChange: (detail: Detail) => void; projectId?: string }) {
  const set = (key: string, value: unknown) => onChange({ ...detail, [key]: value });
  const characters = useQuery({ queryKey: ["drama-characters", projectId], queryFn: () => api.listDramaCharacters(projectId!), enabled: detail.type === "drama" && Boolean(projectId) });
  const locations = useQuery({ queryKey: ["drama-locations", projectId], queryFn: () => api.listDramaLocations(projectId!), enabled: detail.type === "drama" && Boolean(projectId) });
  const props = useQuery({ queryKey: ["drama-props", projectId], queryFn: () => api.listDramaProps(projectId!), enabled: detail.type === "drama" && Boolean(projectId) });
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
  const continuity = (detail.continuity_data as Record<string, unknown>) || {};
  const setContinuity = (key: string, value: unknown) => set("continuity_data", { ...continuity, [key]: value });
  const pickers = [
    { label: "本集人物", key: "character_ids", items: characters.data || [] },
    { label: "主要地点", key: "location_ids", items: locations.data || [] },
    { label: "关键道具", key: "prop_ids", items: props.data || [] },
  ];
  return <div className="grid gap-3 md:grid-cols-2">
    <label className="space-y-1.5 text-sm font-medium"><span>集数</span><Input type="number" min={1} value={Number(detail.episode_number ?? 1)} onChange={(event) => set("episode_number", Number(event.target.value))} /></label>
    <Field label="本集梗概" value={detail.synopsis} onChange={(value) => set("synopsis", value)} multiline />
    <Field label="核心冲突" value={continuity.core_conflict} onChange={(value) => setContinuity("core_conflict", value)} multiline />
    <Field label="结尾钩子" value={continuity.ending_hook} onChange={(value) => setContinuity("ending_hook", value)} multiline />
    {pickers.map((picker) => {
      const selected = Array.isArray(continuity[picker.key]) ? continuity[picker.key] as string[] : [];
      return <fieldset key={picker.key} className="space-y-2 md:col-span-2"><legend className="text-sm font-medium">{picker.label}</legend><div className="flex flex-wrap gap-2">{picker.items.filter((item) => item.approval_status === "approved").map((item) => { const active = selected.includes(item.id); return <button key={item.id} type="button" aria-pressed={active} onClick={() => setContinuity(picker.key, active ? selected.filter((id) => id !== item.id) : [...selected, item.id])} className={`min-h-9 rounded-full border px-3 text-sm ${active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>{item.name}</button>; })}</div></fieldset>;
    })}
    <div className="md:col-span-2"><Field label="剧本" value={detail.script_text} onChange={(value) => set("script_text", value)} multiline /></div>
  </div>;
}
