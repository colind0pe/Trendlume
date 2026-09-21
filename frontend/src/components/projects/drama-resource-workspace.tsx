"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, MapPin, Package, Pencil, Plus, Trash2, Users } from "lucide-react";

import { api } from "@/lib/api-client";
import type { DramaCharacter, DramaLocation, DramaProp } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";

type ResourceKind = "character" | "location" | "prop";
type DramaResource = DramaCharacter | DramaLocation | DramaProp;

const specs = {
  character: { label: "人物", plural: "人物", icon: Users },
  location: { label: "地点", plural: "地点", icon: MapPin },
  prop: { label: "道具", plural: "道具", icon: Package },
} as const;

function notesOf(item: DramaResource) {
  if ("appearance_rules" in item) return String(item.appearance_rules?.notes || "");
  return String(item.continuity_data?.notes || "");
}

function descriptionOf(item: DramaResource) {
  if ("visual_description" in item) return item.visual_description;
  return item.description;
}

export function DramaResourceWorkspace({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editor, setEditor] = React.useState<{
    kind: ResourceKind;
    item?: DramaResource;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<{
    kind: ResourceKind;
    item: DramaResource;
  } | null>(null);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [continuityNotes, setContinuityNotes] = React.useState("");
  const [wardrobeNotes, setWardrobeNotes] = React.useState("");

  const characters = useQuery({
    queryKey: ["drama-characters", projectId],
    queryFn: () => api.listDramaCharacters(projectId),
  });
  const locations = useQuery({
    queryKey: ["drama-locations", projectId],
    queryFn: () => api.listDramaLocations(projectId),
  });
  const props = useQuery({
    queryKey: ["drama-props", projectId],
    queryFn: () => api.listDramaProps(projectId),
  });

  const groups: Array<{ kind: ResourceKind; items: DramaResource[] }> = [
    { kind: "character", items: characters.data || [] },
    { kind: "location", items: locations.data || [] },
    { kind: "prop", items: props.data || [] },
  ];
  const total = groups.reduce((sum, group) => sum + group.items.length, 0);
  const approved = groups.reduce(
    (sum, group) => sum + group.items.filter((item) => item.approval_status === "approved").length,
    0,
  );

  const invalidate = (kind: ResourceKind) =>
    queryClient.invalidateQueries({ queryKey: [`drama-${kind === "character" ? "characters" : kind === "location" ? "locations" : "props"}`, projectId] });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!editor) throw new Error("未选择资源类型");
      const common = { name: name.trim() };
      const payload = editor.kind === "character"
        ? {
            ...common,
            description: description.trim(),
            appearance_rules: { notes: continuityNotes.trim() },
            wardrobe_rules: { notes: wardrobeNotes.trim() },
          }
        : editor.kind === "location"
          ? {
              ...common,
              visual_description: description.trim(),
              continuity_data: { notes: continuityNotes.trim() },
            }
          : {
              ...common,
              description: description.trim(),
              continuity_data: { notes: continuityNotes.trim() },
            };
      if (editor.item) {
        if (editor.kind === "character") return api.updateDramaCharacter(projectId, editor.item.id, payload);
        if (editor.kind === "location") return api.updateDramaLocation(projectId, editor.item.id, payload);
        return api.updateDramaProp(projectId, editor.item.id, payload);
      }
      if (editor.kind === "character") return api.createDramaCharacter(projectId, payload);
      if (editor.kind === "location") return api.createDramaLocation(projectId, payload);
      return api.createDramaProp(projectId, payload);
    },
    onSuccess: () => {
      if (editor) invalidate(editor.kind);
      toast(`${editor?.item ? "修改" : "创建"}成功，请确认连续性设定后审批。`, "success");
      setEditor(null);
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const approveMutation = useMutation({
    mutationFn: async ({ kind, id }: { kind: ResourceKind; id: string }) => {
      if (kind === "character") return api.approveDramaCharacter(projectId, id);
      if (kind === "location") return api.approveDramaLocation(projectId, id);
      return api.approveDramaProp(projectId, id);
    },
    onSuccess: (_, variables) => {
      invalidate(variables.kind);
      toast("连续性设定已审批。", "success");
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: async ({ kind, id }: { kind: ResourceKind; id: string }) => {
      if (kind === "character") return api.deleteDramaCharacter(projectId, id);
      if (kind === "location") return api.deleteDramaLocation(projectId, id);
      return api.deleteDramaProp(projectId, id);
    },
    onSuccess: (_, variables) => {
      invalidate(variables.kind);
      toast("资源已删除。", "success");
    },
    onError: (error: Error) => toast(error.message, "error"),
  });

  const openEditor = (kind: ResourceKind, item?: DramaResource) => {
    setName(item?.name || "");
    setDescription(item ? descriptionOf(item) : "");
    setContinuityNotes(item ? notesOf(item) : "");
    setWardrobeNotes(item && "wardrobe_rules" in item ? String(item.wardrobe_rules?.notes || "") : "");
    setEditor({ kind, item });
  };

  return (
    <div className="space-y-5">
      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="max-w-2xl space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Drama continuity bible</p>
            <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">连续性资料库</h2>
            <p className="text-sm leading-6 text-muted-foreground">
              先锁定角色外观、常驻场景和关键道具，再创建剧集。已审批设定会随任务写入生产 Snapshot，避免跨镜头漂移。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 rounded-xl border border-border bg-muted/35 p-3 text-center">
            <div className="min-w-24"><div className="text-xl font-semibold tabular-nums">{total}</div><div className="text-xs text-muted-foreground">资源总数</div></div>
            <div className="min-w-24 border-l border-border"><div className="text-xl font-semibold tabular-nums">{approved}/{total}</div><div className="text-xs text-muted-foreground">已审批</div></div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {groups.map(({ kind, items }) => {
          const spec = specs[kind];
          const Icon = spec.icon;
          return (
            <section key={kind} aria-labelledby={`drama-${kind}-heading`} className="min-w-0 space-y-3">
              <div className="flex min-h-11 items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary"><Icon aria-hidden="true" className="h-4 w-4" /></span>
                  <div><h3 id={`drama-${kind}-heading`} className="font-semibold">{spec.plural}</h3><p className="text-xs text-muted-foreground">{items.filter((item) => item.approval_status === "approved").length}/{items.length} 已审批</p></div>
                </div>
                <Button type="button" variant="outline" size="sm" className="min-h-9 gap-1.5" onClick={() => openEditor(kind)}><Plus aria-hidden="true" className="h-4 w-4" />新增</Button>
              </div>
              {items.length === 0 ? (
                <EmptyState icon={Icon} title={`还没有${spec.label}`} description={`添加第一条${spec.label}设定，作为后续剧集的连续性基准。`} />
              ) : (
                <div className="space-y-3">
                  {items.map((item) => (
                    <Card key={item.id} className="overflow-hidden">
                      <CardHeader className="p-4 pb-2">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0"><CardTitle className="truncate text-base">{item.name}</CardTitle><span className={`mt-1.5 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${item.approval_status === "approved" ? "border-success/30 bg-success/10 text-success" : "border-warning/30 bg-warning/10 text-warning"}`}>{item.approval_status === "approved" && <Check aria-hidden="true" className="h-3 w-3" />}{item.approval_status === "approved" ? "已审批" : "待审批"}</span></div>
                          <div className="flex gap-1">
                            <IconButton label={`编辑${spec.label} ${item.name}`} variant="ghost" className="h-9 w-9" onClick={() => openEditor(kind, item)}><Pencil aria-hidden="true" className="h-4 w-4" /></IconButton>
                            <IconButton label={`删除${spec.label} ${item.name}`} variant="ghost" className="h-9 w-9 text-destructive" onClick={() => setDeleteTarget({ kind, item })}><Trash2 aria-hidden="true" className="h-4 w-4" /></IconButton>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-3 p-4 pt-2">
                        <p className="line-clamp-3 text-sm leading-6 text-muted-foreground">{descriptionOf(item) || "暂无描述"}</p>
                        {item.approval_status !== "approved" && <Button type="button" size="sm" className="w-full min-h-9 gap-1.5" disabled={approveMutation.isPending} onClick={() => approveMutation.mutate({ kind, id: item.id })}><Check aria-hidden="true" className="h-4 w-4" />确认并审批</Button>}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>

      <Dialog open={Boolean(editor)} onOpenChange={(open) => !open && setEditor(null)}>
        <DialogHeader><DialogTitle>{editor?.item ? "编辑" : "新增"}{editor ? specs[editor.kind].label : "资源"}</DialogTitle><DialogDescription>保存修改后状态会回到待审批，审批后的版本才会进入新的生产 Snapshot。</DialogDescription></DialogHeader>
        <div className="space-y-4">
          <label className="block space-y-1.5 text-sm font-medium"><span>名称</span><Input value={name} onChange={(event) => setName(event.target.value)} placeholder={editor?.kind === "character" ? "例如：林夏" : editor?.kind === "location" ? "例如：旧城区咖啡馆" : "例如：银色怀表"} autoFocus /></label>
          <label className="block space-y-1.5 text-sm font-medium"><span>{editor?.kind === "location" ? "视觉描述" : "设定描述"}</span><Textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} placeholder="写清不可漂移的识别特征、质感与叙事用途。" /></label>
          <label className="block space-y-1.5 text-sm font-medium"><span>连续性备注</span><Textarea value={continuityNotes} onChange={(event) => setContinuityNotes(event.target.value)} rows={3} placeholder="例如：左右位置、损耗状态、昼夜变化等。" /></label>
          {editor?.kind === "character" && <label className="block space-y-1.5 text-sm font-medium"><span>服装规则</span><Textarea value={wardrobeNotes} onChange={(event) => setWardrobeNotes(event.target.value)} rows={3} placeholder="常服、场景换装和不可变化的配饰。" /></label>}
        </div>
        <DialogFooter><Button type="button" variant="outline" onClick={() => setEditor(null)}>取消</Button><Button type="button" disabled={!name.trim() || saveMutation.isPending} onClick={() => saveMutation.mutate()}>{saveMutation.isPending ? "保存中…" : "保存为待审批"}</Button></DialogFooter>
      </Dialog>

      <ConfirmDialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)} title={`删除${deleteTarget ? specs[deleteTarget.kind].label : "资源"}？`} description="已被剧集或分镜引用的资源不会被删除。此操作不可撤销。" confirmLabel="删除" variant="destructive" onConfirm={async () => { if (!deleteTarget) return; await deleteMutation.mutateAsync({ kind: deleteTarget.kind, id: deleteTarget.item.id }); setDeleteTarget(null); }} />
    </div>
  );
}
