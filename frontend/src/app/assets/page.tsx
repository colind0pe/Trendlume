"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckSquare,
  Download,
  Eye,
  ExternalLink,
  Image as ImageIcon,
  Loader2,
  Music,
  Pause,
  Play,
  Tag,
  Trash2,
  Upload,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Input, SearchInput } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/ui/page-shell";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { formatBytes, isBgmAsset, safePexelsPageUrl } from "@/lib/utils";
import { AssetType, Asset } from "@/lib/types";
import { ASSET_TYPE_LABELS } from "@/lib/ui-constants";

const assetFilters = [
  { label: "全部", value: "all" },
  { label: "图片", value: "image" },
  { label: "视频", value: "video" },
  { label: "配音", value: "audio" },
  { label: "背景音乐", value: "bgm" },
];

export default function AssetsPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [selectedType, setSelectedType] = React.useState("all");
  const [selectedProject, setSelectedProject] = React.useState("");
  const [searchQuery, setSearchQuery] = React.useState("");
  const [isUploading, setIsUploading] = React.useState(false);
  const [assetToDelete, setAssetToDelete] = React.useState<{ id: string; name: string } | null>(null);
  const [selectedAssetIds, setSelectedAssetIds] = React.useState<Set<string>>(new Set());
  const [isTagDialogOpen, setIsTagDialogOpen] = React.useState(false);
  const [tagsInput, setTagsInput] = React.useState("");
  const [previewAsset, setPreviewAsset] = React.useState<Asset | null>(null);
  const [playingAssetId, setPlayingAssetId] = React.useState<string | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  React.useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  const toggleAudioPlayback = (asset: Asset) => {
    if (playingAssetId === asset.id) {
      audioRef.current?.pause();
      setPlayingAssetId(null);
    } else {
      if (!audioRef.current) {
        audioRef.current = new Audio();
        audioRef.current.onended = () => setPlayingAssetId(null);
      }
      audioRef.current.src = `/api/v1/assets/files/${asset.file_path}`;
      audioRef.current.play().catch(() => {});
      setPlayingAssetId(asset.id);
    }
  };

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  });

  const { data: assets = [], isLoading } = useQuery({
    queryKey: ["assets", selectedType],
    queryFn: () => api.listAssets(undefined, selectedType === "all" ? undefined : selectedType),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteAsset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      toast("素材已删除。", "success");
    },
    onError: (error: any) => toast(`删除素材失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const batchDeleteMutation = useMutation({
    mutationFn: (ids: string[]) => api.batchDeleteAssets(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      setSelectedAssetIds(new Set());
      const skippedCount = result.skipped?.length || 0;
      toast(
        skippedCount
          ? `已删除 ${result.deleted_ids?.length || 0} 个素材，${skippedCount} 个素材因被引用或文件缺失而跳过。`
          : `已删除 ${result.deleted_ids?.length || 0} 个素材。`,
        skippedCount ? "warning" : "success",
      );
    },
    onError: (error: any) => toast(`批量删除失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const batchTagMutation = useMutation({
    mutationFn: ({ ids, tags }: { ids: string[]; tags: string[] }) => api.batchTagAssets(ids, tags),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      setIsTagDialogOpen(false);
      setTagsInput("");
      const skippedCount = result.skipped?.length || 0;
      toast(
        skippedCount
          ? `已为 ${result.updated_ids?.length || 0} 个素材添加标签，${skippedCount} 个素材跳过。`
          : `已为 ${result.updated_ids?.length || 0} 个素材添加标签。`,
        skippedCount ? "warning" : "success",
      );
    },
    onError: (error: any) => toast(`批量标签失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const downloadMutation = useMutation({
    mutationFn: (ids: string[]) => api.downloadAssets(ids),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `trendlume-assets-${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast("素材压缩包已开始下载。", "success");
    },
    onError: (error: any) => toast(`下载素材失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const filteredAssets = React.useMemo(() => {
    return assets.filter((asset) => {
      if (selectedType === "bgm" && !isBgmAsset(asset)) return false;
      if (selectedProject && asset.project_id && asset.project_id !== selectedProject) return false;
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase();
      const matchName = asset.file_name.toLowerCase().includes(q);
      const matchTag = Array.isArray(asset.metadata_json?.tags) &&
        asset.metadata_json.tags.some((t: string) => String(t).toLowerCase().includes(q));
      return matchName || matchTag;
    });
  }, [assets, selectedProject, searchQuery]);

  const selectableAssets = filteredAssets.filter(
    (asset) => !(asset.project_id === null && asset.metadata_json?.scope === "system"),
  );
  const selectableIds = selectableAssets.map((asset) => asset.id);
  const selectedIds = Array.from(selectedAssetIds).filter((id) => selectableIds.includes(id));
  const isAllSelected = selectableIds.length > 0 && selectableIds.every((id) => selectedAssetIds.has(id));
  const isBatchBusy = batchDeleteMutation.isPending || batchTagMutation.isPending || downloadMutation.isPending;

  React.useEffect(() => {
    setSelectedAssetIds((current) => {
      const next = new Set(Array.from(current).filter((id) => selectableIds.includes(id)));
      return next.size === current.size ? current : next;
    });
  }, [selectedType, filteredAssets.length]);

  const toggleAssetSelection = (assetId: string, checked: boolean) => {
    setSelectedAssetIds((current) => {
      const next = new Set(current);
      if (checked) next.add(assetId);
      else next.delete(assetId);
      return next;
    });
  };

  const toggleAllAssets = () => {
    setSelectedAssetIds((current) => {
      if (isAllSelected) return new Set(Array.from(current).filter((id) => !selectableIds.includes(id)));
      return new Set([...current, ...selectableIds]);
    });
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    let assetType: AssetType = selectedType === "bgm" ? "bgm" : "image";
    if (selectedType !== "bgm" && file.type.startsWith("video/")) assetType = "video";
    else if (selectedType !== "bgm" && file.type.startsWith("audio/")) assetType = "audio";

    setIsUploading(true);
    try {
      await api.uploadAsset(file, assetType, selectedProject || undefined);
      queryClient.invalidateQueries({ queryKey: ["assets"] });
      if (assetType === "bgm" && selectedProject) {
        queryClient.invalidateQueries({ queryKey: ["project-bgm", selectedProject] });
        queryClient.invalidateQueries({ queryKey: ["task-project-bgm", selectedProject] });
      }
      toast("素材上传完成。", "success");
    } catch (error: any) {
      toast(`上传失败：${error?.message || "请稍后重试"}`, "error");
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  return (
    <PageContainer width="wide" className="space-y-5">
      <PageHeader
        title="素材库"
        description="集中管理视觉画面、视频切片与背景音频资产。"
        actions={(
          <>
            <input
              type="file"
              id="asset-file-input"
              className="hidden"
              accept={
                selectedType === "bgm" || selectedType === "audio"
                  ? "audio/*"
                  : selectedType === "video"
                  ? "video/*"
                  : selectedType === "image"
                  ? "image/*"
                  : undefined
              }
              onChange={handleFileUpload}
              disabled={isUploading}
            />
            <Button
              type="button"
              disabled={isUploading}
              title={!selectedProject ? "请先选择具体项目空间以指定素材归属" : undefined}
              className="gap-1.5 h-9 px-3.5 text-sm"
              onClick={() => {
                if (!selectedProject) {
                  toast("请先选择具体项目空间，以明确素材归属。", "warning");
                  document.getElementById("asset-project")?.focus();
                  return;
                }
                document.getElementById("asset-file-input")?.click();
              }}
            >
              <Upload aria-hidden="true" className="h-4 w-4" />
              {isUploading ? "上传中…" : selectedType === "bgm" ? "上传背景音乐" : "上传素材"}
            </Button>
          </>
        )}
      />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 flex-1 max-w-2xl">
          <div className="w-full sm:w-64">
            <Select id="asset-project" value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)} className="h-9 text-sm">
              <option value="">全部空间资产</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>{project.name} ({project.aspect_ratio})</option>
              ))}
            </Select>
          </div>
          <div className="w-full sm:w-72">
            <SearchInput
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onClear={() => setSearchQuery("")}
              placeholder="搜索素材名或标签…"
              className="h-9 text-sm bg-card"
            />
          </div>
        </div>

        <Tabs value={selectedType} onValueChange={setSelectedType} className="space-y-0 sm:self-end">
          <TabsList aria-label="素材类型" className="h-9 max-w-full overflow-x-auto no-scrollbar">
            {assetFilters.map((filter) => (
              <TabsTrigger key={filter.value} value={filter.value} className="text-sm h-8 px-3">{filter.label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {assets.length > 0 && (
        <div className="flex flex-col gap-2.5 rounded-xl glass-panel p-3 sm:px-4 sm:flex-row sm:items-center sm:justify-between shadow-glass">
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-foreground">
            <input
              type="checkbox"
              checked={isAllSelected}
              onChange={toggleAllAssets}
              disabled={!selectableIds.length || isBatchBusy}
              aria-label="选择当前列表中的全部可管理素材"
              className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
            />
            <CheckSquare aria-hidden="true" className="h-4 w-4 text-primary" />
            {selectedIds.length ? `已选择 ${selectedIds.length} 个素材` : "批量选择素材"}
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="gap-1.5 h-8 px-3 text-xs sm:text-sm"
              disabled={!selectedIds.length || isBatchBusy}
              onClick={() => setIsTagDialogOpen(true)}
            >
              <Tag aria-hidden="true" className="h-3.5 w-3.5" />
              批量加标签
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="gap-1.5 h-8 px-3 text-xs sm:text-sm"
              disabled={!selectedIds.length || isBatchBusy}
              onClick={() => downloadMutation.mutate(selectedIds)}
            >
              {downloadMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download aria-hidden="true" className="h-3.5 w-3.5" />}
              下载所选
            </Button>
            <Button
              type="button"
              size="sm"
              variant="destructive"
              className="gap-1.5 h-8 px-3 text-xs sm:text-sm"
              disabled={!selectedIds.length || isBatchBusy}
              onClick={() => setAssetToDelete({ id: "__batch__", name: `${selectedIds.length} 个选中素材` })}
            >
              {batchDeleteMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />}
              批量删除
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {[1, 2, 3, 4, 5, 6].map((item) => (
            <div key={item} className="h-44 animate-pulse rounded-xl border border-border/60 bg-card/40" />
          ))}
        </div>
      ) : assets.length === 0 ? (
        <EmptyState icon={ImageIcon} title="暂无素材资产" description="选择项目后，可点击右上角上传自定义素材图片或音频。" />
      ) : filteredAssets.length === 0 ? (
        <EmptyState
          icon={ImageIcon}
          title="未找到匹配的素材"
          description="尝试更改搜索关键词或切换素材分类与空间。"
          action={
            (searchQuery || selectedProject) ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchQuery("");
                  setSelectedProject("");
                }}
                className="h-7 text-xs"
              >
                重置筛选
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {filteredAssets.map((asset) => (
            <Card key={asset.id} className="group flex flex-col justify-between overflow-hidden glass-card rounded-2xl hover:border-primary/40 hover:shadow-glass-hover transition-all duration-200">
              <div className="relative flex h-36 sm:h-40 items-center justify-center overflow-hidden border-b border-border/50 bg-secondary/30">
                {asset.asset_type === "image" ? (
                  <div
                    onClick={() => setPreviewAsset(asset)}
                    className="relative h-full w-full cursor-pointer group/img"
                    title="点击全屏预览"
                  >
                    <img
                      src={`/api/v1/assets/files/${asset.file_path}`}
                      alt={asset.file_name}
                      className="h-full w-full object-cover transition-transform duration-150 group-hover/img:scale-105"
                    />
                    <div className="absolute inset-0 bg-black/35 opacity-0 group-hover/img:opacity-100 transition-opacity flex items-center justify-center">
                      <Eye className="h-5 w-5 text-white drop-shadow" />
                    </div>
                  </div>
                ) : asset.asset_type === "audio" || asset.asset_type === "bgm" ? (
                  <div className="flex flex-col items-center gap-2 p-3">
                    <button
                      type="button"
                      onClick={() => toggleAudioPlayback(asset)}
                      aria-label={playingAssetId === asset.id ? "暂停试听" : "播放试听"}
                      title={playingAssetId === asset.id ? "暂停试听" : "点击试听"}
                      className={`h-11 w-11 rounded-full flex items-center justify-center transition-all cursor-pointer shadow-xs ${
                        playingAssetId === asset.id
                          ? "bg-primary text-primary-foreground shadow-md animate-pulse"
                          : "bg-background border border-border text-foreground hover:bg-primary/20 hover:text-primary"
                      }`}
                    >
                      {playingAssetId === asset.id ? (
                        <Pause className="h-5 w-5 fill-current" />
                      ) : (
                        <Play className="h-5 w-5 fill-current translate-x-0.5" />
                      )}
                    </button>
                    <span className="font-mono text-xs uppercase text-muted-foreground">{asset.mime_type.split("/")[1] || asset.asset_type}</span>
                  </div>
                ) : (
                  <div
                    onClick={() => setPreviewAsset(asset)}
                    className="flex flex-col items-center gap-2 p-3 cursor-pointer group/video w-full h-full justify-center"
                    title="点击播放视频"
                  >
                    <div className="h-11 w-11 rounded-full bg-background border border-border flex items-center justify-center group-hover/video:bg-primary/20 group-hover/video:text-primary transition-colors shadow-xs">
                      <Play className="h-5 w-5 fill-current translate-x-0.5" />
                    </div>
                    <span className="font-mono text-xs uppercase text-muted-foreground">{asset.mime_type.split("/")[1] || asset.asset_type}</span>
                  </div>
                )}
                <Badge variant="outline" className="absolute left-2 top-2 bg-background/80 backdrop-blur-sm text-xs px-2 py-0.5">
                  {ASSET_TYPE_LABELS[asset.asset_type] || asset.asset_type}
                </Badge>
                {asset.metadata_json?.source_kind === "online_asset" && (
                  <Badge variant="secondary" className="absolute right-2 top-2 bg-background/80 text-xs px-2 py-0.5">
                    在线素材 · Pexels
                  </Badge>
                )}
                {asset.project_id !== null || asset.metadata_json?.scope !== "system" ? (
                  <input
                    type="checkbox"
                    checked={selectedAssetIds.has(asset.id)}
                    onChange={(event) => toggleAssetSelection(asset.id, event.target.checked)}
                    disabled={isBatchBusy}
                    aria-label={`选择素材 ${asset.file_name}`}
                    className="absolute right-2 top-2 h-4 w-4 rounded border-input bg-background text-primary shadow-subtle focus:ring-primary"
                  />
                ) : null}
              </div>

              <div className="space-y-1.5 p-3">
                <p
                  className="truncate text-sm font-medium text-foreground hover:text-primary transition-colors cursor-pointer"
                  title={asset.file_name}
                  onClick={() => setPreviewAsset(asset)}
                >
                  {asset.file_name}
                </p>
                {asset.metadata_json?.source_kind === "online_asset" && (
                  <div className="flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                    {safePexelsPageUrl(asset.metadata_json?.source_page_url) && (
                      <a
                        href={safePexelsPageUrl(asset.metadata_json?.source_page_url) || undefined}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 truncate text-primary hover:underline"
                      >
                        Pexels 来源
                        <ExternalLink aria-hidden="true" className="h-3 w-3 shrink-0" />
                      </a>
                    )}
                    {safePexelsPageUrl(asset.metadata_json?.author_url, "author") && (
                      <a
                        href={safePexelsPageUrl(asset.metadata_json?.author_url, "author") || undefined}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 truncate text-muted-foreground hover:text-primary hover:underline"
                      >
                        作者：{asset.metadata_json.author || "查看作者"}
                        <ExternalLink aria-hidden="true" className="h-3 w-3 shrink-0" />
                      </a>
                    )}
                  </div>
                )}
                {Array.isArray(asset.metadata_json?.tags) && asset.metadata_json.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {asset.metadata_json.tags.slice(0, 3).map((tag: string) => (
                      <Badge key={tag} variant="secondary" className="max-w-24 truncate text-xs px-2 py-0.5">#{tag}</Badge>
                    ))}
                  </div>
                )}
                <div className="flex items-center justify-between gap-1.5 pt-1 text-xs text-muted-foreground">
                  <span className="font-mono text-muted-foreground/80">{formatBytes(asset.file_size_bytes)}</span>
                  {asset.project_id === null && asset.metadata_json?.scope === "system" ? (
                    <span className="shrink-0 text-primary font-medium text-xs">系统内置</span>
                  ) : (
                    <IconButton
                      label={`删除素材 ${asset.file_name}`}
                      variant="ghost"
                      className="h-7 w-7 shrink-0 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10"
                      onClick={() => setAssetToDelete({ id: asset.id, name: asset.file_name })}
                    >
                      <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                    </IconButton>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={Boolean(assetToDelete)}
        onOpenChange={(open) => {
          if (!open) setAssetToDelete(null);
        }}
        title="删除素材？"
        description={assetToDelete ? `将删除“${assetToDelete.name}”，此操作无法撤销。` : "此操作无法撤销。"}
        confirmLabel="确认删除"
        variant="destructive"
        onConfirm={async () => {
          if (!assetToDelete) return;
          if (assetToDelete.id === "__batch__") {
            await batchDeleteMutation.mutateAsync(selectedIds);
          } else {
            await deleteMutation.mutateAsync(assetToDelete.id);
          }
          setAssetToDelete(null);
        }}
      />

      <Dialog open={isTagDialogOpen} onOpenChange={setIsTagDialogOpen} className="max-w-md">
        <DialogHeader>
          <DialogTitle>编辑素材标签</DialogTitle>
          <DialogDescription>输入分类标签（以逗号或空格分隔），便于分镜检索。</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-1">
          <label htmlFor="asset-batch-tags" className="text-xs font-semibold text-foreground">标签</label>
          <Input
            id="asset-batch-tags"
            value={tagsInput}
            onChange={(event) => setTagsInput(event.target.value)}
            placeholder="例如：科技, 竖屏, 待发布"
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setIsTagDialogOpen(false)}>取消</Button>
          <Button
            type="button"
            disabled={!tagsInput.trim() || batchTagMutation.isPending}
            onClick={() => batchTagMutation.mutate({
              ids: selectedIds,
              tags: tagsInput.split(/[,，\s]+/).map((tag) => tag.trim()).filter(Boolean),
            })}
          >
            {batchTagMutation.isPending ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Check className="mr-1.5 h-3.5 w-3.5" />}
            保存标签
          </Button>
        </DialogFooter>
      </Dialog>

      {/* Lightbox / Asset Preview Modal */}
      <Dialog open={Boolean(previewAsset)} onOpenChange={(open) => !open && setPreviewAsset(null)} className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="truncate pr-6 text-base font-semibold">{previewAsset?.file_name || "素材预览"}</DialogTitle>
          <DialogDescription>
            {previewAsset ? `${ASSET_TYPE_LABELS[previewAsset.asset_type] || previewAsset.asset_type} · ${formatBytes(previewAsset.file_size_bytes)} · ${previewAsset.mime_type}` : ""}
          </DialogDescription>
        </DialogHeader>
        {previewAsset && (
          <div className="space-y-3 pt-1">
            <div className="flex max-h-[580px] items-center justify-center overflow-hidden rounded-xl border border-border bg-black/95 p-1.5">
              {previewAsset.asset_type === "image" ? (
                <img
                  src={`/api/v1/assets/files/${previewAsset.file_path}`}
                  alt={previewAsset.file_name}
                  className="max-h-[550px] w-auto max-w-full object-contain"
                />
              ) : previewAsset.asset_type === "video" ? (
                <video
                  src={`/api/v1/assets/files/${previewAsset.file_path}`}
                  controls
                  autoPlay
                  className="max-h-[550px] w-full"
                />
              ) : (
                <div className="flex flex-col items-center justify-center py-8 px-4 w-full">
                  <Music className="h-12 w-12 text-primary mb-4 animate-pulse" />
                  <audio
                    src={`/api/v1/assets/files/${previewAsset.file_path}`}
                    controls
                    autoPlay
                    className="w-full max-w-md"
                  />
                </div>
              )}
            </div>
            <div className="flex items-center justify-between pt-1 text-xs">
              <span className="font-mono text-muted-foreground">
                {previewAsset.width && previewAsset.height ? `${previewAsset.width} × ${previewAsset.height} px` : previewAsset.mime_type}
              </span>
              <a
                href={`/api/v1/assets/files/${previewAsset.file_path}`}
                download={previewAsset.file_name}
                className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
              >
                <Download className="h-3.5 w-3.5" />
                下载素材文件
              </a>
            </div>
          </div>
        )}
      </Dialog>
    </PageContainer>
  );
}
