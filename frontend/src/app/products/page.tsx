"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Image as ImageIcon,
  Link2,
  Layers3,
  PackageOpen,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  Video,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { CreativePlan, Product } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { PageContainer, PageHeader, SectionHeader } from "@/components/ui/page-shell";
import { useToast } from "@/components/ui/toast";

const assetUrl = (filePath: string) => `/api/v1/assets/files/${filePath.split("/").map(encodeURIComponent).join("/")}`;

function sourceLabel(source: string) {
  return {
    user_input: "用户输入",
    manual_correction: "人工修正",
    json_ld: "JSON-LD",
    opengraph: "OpenGraph",
    page_structure: "页面结构",
  }[source] || source;
}

const angleLabels: Record<string, string> = {
  direct: "直接介绍",
  pain_point: "痛点切入",
  use_case: "使用场景",
  demo: "功能演示",
  review: "真实测评",
  comparison: "对比选择",
  story: "故事叙事",
};

const planStatusLabels: Record<string, string> = {
  draft: "待选择",
  selected: "已选择",
  variant: "Variant",
  archived: "已归档",
};

function ProductsPageContent() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const [selectedId, setSelectedId] = React.useState<string | null>(searchParams.get("product"));
  const [mode, setMode] = React.useState<"manual" | "import">("manual");
  const [importUrl, setImportUrl] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [brand, setBrand] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [price, setPrice] = React.useState("");
  const [currency, setCurrency] = React.useState("CNY");
  const [specificationsText, setSpecificationsText] = React.useState("");
  const [sellingPointsText, setSellingPointsText] = React.useState("");
  const [assetType, setAssetType] = React.useState<"image" | "video">("image");
  const [productToDelete, setProductToDelete] = React.useState<Product | null>(null);

  const { data: products = [], isLoading } = useQuery({
    queryKey: ["products"],
    queryFn: () => api.listProducts(),
  });
  const selected = products.find((product) => product.id === selectedId) || null;

  const { data: creativePlans = [], isLoading: creativePlansLoading } = useQuery<CreativePlan[]>({
    queryKey: ["creative-plans", selected?.id],
    queryFn: () => api.listCreativePlans(selected!.id),
    enabled: Boolean(selected?.id),
  });
  const activeCreativePlans = creativePlans.filter((plan) => plan.status !== "archived");

  React.useEffect(() => {
    if (!selectedId && products[0]) setSelectedId(products[0].id);
    if (selectedId && !products.some((product) => product.id === selectedId)) setSelectedId(products[0]?.id || null);
  }, [products, selectedId]);

  React.useEffect(() => {
    if (!selected) return;
    setTitle(selected.title);
    setBrand(selected.brand);
    setDescription(selected.description);
    setPrice(selected.price);
    setCurrency(selected.currency || "CNY");
    setSpecificationsText(Object.entries(selected.specifications || {}).map(([key, value]) => `${key}=${value}`).join("\n"));
    setSellingPointsText(selected.truth_sheet.selling_points.map((claim) => claim.text).join("\n"));
  }, [selected]);

  const parseSpecifications = () => Object.fromEntries(
    specificationsText.split(/\r?\n/).map((line) => line.split("=")).filter(([key, value]) => key?.trim() && value?.trim()).map(([key, value]) => [key.trim(), value.trim()]),
  );

  const createMutation = useMutation({
    mutationFn: () => api.createProduct({
      title: title.trim(), brand: brand.trim(), description: description.trim(), price: price.trim(), currency: currency.trim(),
      specifications: parseSpecifications(),
      selling_points: sellingPointsText.split(/\r?\n/).map((text) => text.trim()).filter(Boolean).map((text) => ({ text })),
    }),
    onSuccess: (product) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setSelectedId(product.id);
      toast("商品已加入商品库。", "success");
    },
    onError: (error: any) => toast(`创建商品失败：${error?.message || "请检查输入"}`, "error"),
  });

  const importMutation = useMutation({
    mutationFn: () => api.importProduct(importUrl.trim()),
    onSuccess: (product) => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setSelectedId(product.id);
      setImportUrl("");
      toast("商品页面已解析，请核对 Truth Sheet。", "success");
    },
    onError: (error: any) => toast(`导入失败：${error?.message || "请检查公开商品 URL"}`, "error"),
  });

  const updateMutation = useMutation({
    mutationFn: () => selected ? api.updateProduct(selected.id, {
      title: title.trim(), brand: brand.trim(), description: description.trim(), price: price.trim(), currency: currency.trim(), specifications: parseSpecifications(),
      selling_points: sellingPointsText.split(/\r?\n/).map((text) => text.trim()).filter(Boolean).map((text) => ({ text })),
    }) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast("商品事实已保存，变更已标记为人工修正。", "success");
    },
    onError: (error: any) => toast(`保存商品失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => selected ? api.uploadProductAsset(selected.id, file, assetType, assetType === "image" ? "gallery" : "demo") : Promise.reject(new Error("尚未选择商品")),
    onSuccess: (product) => {
      queryClient.setQueryData<Product[]>(["products"], (current = []) => current.map((item) => item.id === product.id ? product : item));
      toast("商品素材已上传。", "success");
    },
    onError: (error: any) => toast(`素材上传失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const deleteAssetMutation = useMutation({
    mutationFn: (productAssetId: string) => selected ? api.deleteProductAsset(selected.id, productAssetId) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast("商品素材已移除。", "success");
    },
    onError: (error: any) => toast(`移除素材失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: () => selected ? api.deleteProduct(selected.id) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["products"] });
      setSelectedId(null);
      setProductToDelete(null);
      toast("商品已删除。", "success");
    },
    onError: (error: any) => toast(`删除失败：${error?.message || "商品可能已被任务引用"}`, "error"),
  });

  const generatePlansMutation = useMutation({
    mutationFn: () => selected ? api.generateCreativePlans(selected.id) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: (plans) => {
      queryClient.setQueryData(["creative-plans", selected?.id], plans);
      toast("已生成 3 个低成本 Creative Plan，尚未生成媒体。", "success");
    },
    onError: (error: any) => toast(`方案生成失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const selectPlanMutation = useMutation({
    mutationFn: (planId: string) => selected ? api.selectCreativePlan(selected.id, planId) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["creative-plans", selected?.id] });
      toast("方案已选择，可以进入 storyboard/media。", "success");
    },
    onError: (error: any) => toast(`选择方案失败：${error?.message || "请稍后重试"}`, "error"),
  });

  const duplicatePlanMutation = useMutation({
    mutationFn: (planId: string) => selected ? api.duplicateCreativePlan(selected.id, planId) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["creative-plans", selected?.id] });
      toast("已复制 Variant，共享当前 Product Truth 和商品素材。", "success");
    },
    onError: (error: any) => toast(`复制 Variant 失败：${error?.message || "请先选择方案"}`, "error"),
  });

  const confirmFactsMutation = useMutation({
    mutationFn: (planId: string) => selected ? api.confirmCreativePlanFacts(selected.id, planId) : Promise.reject(new Error("尚未选择商品")),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["creative-plans", selected?.id] });
      toast("动态事实已记录确认时间。", "success");
    },
    onError: (error: any) => toast(`确认事实失败：${error?.message || "请稍后重试"}`, "error"),
  });

  return (
    <PageContainer width="wide" className="space-y-5">
      <PageHeader
        title="商品库"
        description="维护商品事实、真实商品素材与可追溯商业主张，再进入 Commerce 视频任务。"
        actions={<Button onClick={() => { setSelectedId(null); setMode("manual"); setTitle(""); setBrand(""); setDescription(""); setPrice(""); setSpecificationsText(""); setSellingPointsText(""); }} className="gap-1.5"><Plus className="h-4 w-4" />新建商品</Button>}
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2"><PackageOpen className="h-4 w-4 text-primary" />商品清单</CardTitle>
            <CardDescription>商品事实是 Commerce 任务的固定输入。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {isLoading ? <div className="h-28 animate-pulse rounded-lg bg-secondary/50" /> : products.length === 0 ? (
              <EmptyState icon={PackageOpen} title="还没有商品" description="手工创建或导入一个公开商品页面。" />
            ) : products.map((product) => (
              <button key={product.id} type="button" onClick={() => setSelectedId(product.id)} aria-pressed={selectedId === product.id} className={`w-full rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedId === product.id ? "border-primary bg-primary/10" : "border-border bg-card hover:bg-secondary/60"}`}>
                <div className="flex items-start justify-between gap-2"><span className="truncate text-sm font-medium text-foreground">{product.title}</span><Badge variant={product.status === "ready" ? "success" : "secondary"}>{product.status === "ready" ? "可用" : "草稿"}</Badge></div>
                <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground"><span>{product.brand || "未填写品牌"}</span><span>{product.assets.filter((asset) => asset.asset_id).length} 素材</span></div>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="space-y-5">
          {!selected ? (
            <Card>
              <CardHeader><CardTitle>建立商品事实</CardTitle><CardDescription>解析结果只作为来源报告信息，保存前请人工核对和修正。</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2 rounded-lg bg-secondary/60 p-1" role="tablist" aria-label="商品输入方式">
                  <button type="button" role="tab" aria-selected={mode === "manual"} onClick={() => setMode("manual")} className={`flex-1 rounded-md px-3 py-2 text-sm font-medium ${mode === "manual" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}>手工输入</button>
                  <button type="button" role="tab" aria-selected={mode === "import"} onClick={() => setMode("import")} className={`flex-1 rounded-md px-3 py-2 text-sm font-medium ${mode === "import" ? "bg-card text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"}`}>公开 URL 导入</button>
                </div>
                {mode === "import" ? (
                  <div className="space-y-3">
                    <Field label="公开商品 URL" htmlFor="product-import-url" required description="仅抓取公开 HTTP/HTTPS 页面，服务端会拒绝内网地址并限制大小、重定向和超时。">
                      <Input id="product-import-url" type="url" value={importUrl} onChange={(event) => setImportUrl(event.target.value)} placeholder="https://shop.example/products/item" className="h-10" />
                    </Field>
                    <Button type="button" onClick={() => importMutation.mutate()} disabled={!importUrl.trim() || importMutation.isPending} className="gap-1.5">{importMutation.isPending ? "解析中…" : "解析商品页面"}<Link2 className="h-4 w-4" /></Button>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Field label="商品名称" htmlFor="product-title" required><Input id="product-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：轻量保温杯" className="h-10" /></Field>
                      <Field label="品牌" htmlFor="product-brand"><Input id="product-brand" value={brand} onChange={(event) => setBrand(event.target.value)} placeholder="可留空" className="h-10" /></Field>
                      <Field label="价格" htmlFor="product-price"><Input id="product-price" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="例如：199" className="h-10" /></Field>
                      <Field label="货币" htmlFor="product-currency"><Input id="product-currency" value={currency} onChange={(event) => setCurrency(event.target.value)} placeholder="CNY" className="h-10" /></Field>
                    </div>
                    <Field label="商品描述" htmlFor="product-description"><Textarea id="product-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="只填写你确认过的商品信息" rows={3} /></Field>
                    <Field label="规格（每行 key=value）" htmlFor="product-specifications" description="规格会生成可追溯的 numerical claim。"><Textarea id="product-specifications" value={specificationsText} onChange={(event) => setSpecificationsText(event.target.value)} placeholder={'容量=500ml\n材质=不锈钢'} rows={3} /></Field>
                    <Field label="卖点（每行一条）" htmlFor="product-selling-points" description="未提供证据的卖点会标记为待确认，不会被当作来源事实。"><Textarea id="product-selling-points" value={sellingPointsText} onChange={(event) => setSellingPointsText(event.target.value)} placeholder="便于随身携带\n用户确认的其他卖点" rows={3} /></Field>
                    <Button type="button" onClick={() => createMutation.mutate()} disabled={!title.trim() || createMutation.isPending} className="gap-1.5">{createMutation.isPending ? "保存中…" : "加入商品库"}<CheckCircle2 className="h-4 w-4" /></Button>
                  </>
                )}
              </CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><CardTitle>{selected.title}</CardTitle><CardDescription className="mt-1">商品事实可人工修正；变更会留下 manual_correction 来源标记。</CardDescription></div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => setProductToDelete(selected)} className="gap-1.5 text-destructive hover:text-destructive"><Trash2 className="h-3.5 w-3.5" />删除</Button><Button size="sm" onClick={() => updateMutation.mutate()} disabled={updateMutation.isPending || !title.trim()}>{updateMutation.isPending ? "保存中…" : "保存修正"}</Button></div></div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2"><Field label="商品名称" htmlFor="edit-product-title" required><Input id="edit-product-title" value={title} onChange={(event) => setTitle(event.target.value)} className="h-10" /></Field><Field label="品牌" htmlFor="edit-product-brand"><Input id="edit-product-brand" value={brand} onChange={(event) => setBrand(event.target.value)} className="h-10" /></Field><Field label="价格" htmlFor="edit-product-price"><Input id="edit-product-price" value={price} onChange={(event) => setPrice(event.target.value)} className="h-10" /></Field><Field label="货币" htmlFor="edit-product-currency"><Input id="edit-product-currency" value={currency} onChange={(event) => setCurrency(event.target.value)} className="h-10" /></Field></div>
                  <Field label="商品描述" htmlFor="edit-product-description"><Textarea id="edit-product-description" value={description} onChange={(event) => setDescription(event.target.value)} rows={3} /></Field>
                  <Field label="规格（每行 key=value）" htmlFor="edit-product-specifications"><Textarea id="edit-product-specifications" value={specificationsText} onChange={(event) => setSpecificationsText(event.target.value)} rows={3} /></Field>
                  <Field label="卖点（每行一条）" htmlFor="edit-product-selling-points" description="只保留已确认或可追溯的商业主张。"><Textarea id="edit-product-selling-points" value={sellingPointsText} onChange={(event) => setSellingPointsText(event.target.value)} rows={3} /></Field>
                  {selected.source_url && <a href={selected.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><ExternalLink className="h-3 w-3" />查看原始商品页面</a>}
                </CardContent>
              </Card>

              <Card className="border-primary/20 bg-primary/[0.02]">
                <CardHeader className="pb-3">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-primary" />Creative Planning</CardTitle>
                      <CardDescription className="mt-1">先并排审阅 3 个低成本方向；确认后才进入 storyboard 和媒体生成。</CardDescription>
                    </div>
                    <Button type="button" size="sm" onClick={() => generatePlansMutation.mutate()} disabled={generatePlansMutation.isPending} className="shrink-0 gap-1.5">
                      <Sparkles className="h-3.5 w-3.5" />{generatePlansMutation.isPending ? "规划中…" : "生成 3 个方案"}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {creativePlansLoading ? (
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-3"><div className="h-64 animate-pulse rounded-xl bg-secondary/50" /><div className="h-64 animate-pulse rounded-xl bg-secondary/50" /><div className="h-64 animate-pulse rounded-xl bg-secondary/50" /></div>
                  ) : activeCreativePlans.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
                      <p className="text-sm font-medium text-foreground">还没有 Creative Plan</p>
                      <p className="mt-1 text-xs text-muted-foreground">生成方案只保存 angle、hook、受众、主张和 scene outline，不会调用媒体 Provider。</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                      {activeCreativePlans.map((plan) => {
                        const isSelected = plan.status === "selected";
                        const factsConfirmed = Boolean(plan.fact_snapshot?.confirmed_by_user);
                        return (
                          <article key={plan.id} className={`flex min-h-[300px] flex-col rounded-xl border p-4 transition-colors ${isSelected ? "border-primary bg-primary/[0.06] ring-1 ring-primary/30" : "border-border bg-card/60"}`}>
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex min-w-0 items-center gap-2"><Badge variant={isSelected ? "success" : plan.status === "variant" ? "info" : "outline"}>{planStatusLabels[plan.status] || plan.status}</Badge><span className="truncate text-sm font-semibold text-foreground">{plan.variant_label}</span></div>
                              <span className="shrink-0 text-xs text-muted-foreground">{angleLabels[plan.angle] || plan.angle}</span>
                            </div>
                            <p className="mt-4 text-sm font-medium leading-relaxed text-foreground">{plan.hook}</p>
                            <dl className="mt-3 space-y-2 text-xs">
                              <div><dt className="text-muted-foreground">受众</dt><dd className="mt-0.5 leading-relaxed text-foreground">{plan.audience}</dd></div>
                              <div><dt className="text-muted-foreground">核心信息</dt><dd className="mt-0.5 leading-relaxed text-foreground">{plan.core_message}</dd></div>
                            </dl>
                            <div className="mt-3 flex flex-wrap gap-1.5"><Badge variant="secondary">{plan.scene_outline.length} 个场景 beat</Badge><Badge variant={plan.claims.every((claim) => claim.evidence_refs.length > 0) ? "success" : "warning"}>{plan.claims.length} 个可追溯主张</Badge></div>
                            <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">CTA：</span>{plan.cta}</p>
                            <div className="mt-auto flex flex-wrap gap-2 pt-4">
                              {!isSelected && <Button type="button" size="sm" onClick={() => selectPlanMutation.mutate(plan.id)} disabled={selectPlanMutation.isPending} className="gap-1.5"><Check className="h-3.5 w-3.5" />选择方案</Button>}
                              {isSelected && <Badge variant="success" className="h-8 px-3"><Check className="h-3.5 w-3.5" />已选择，可进入生产</Badge>}
                              {isSelected && <Button type="button" size="sm" variant="outline" onClick={() => duplicatePlanMutation.mutate(plan.id)} disabled={duplicatePlanMutation.isPending} className="gap-1.5"><Copy className="h-3.5 w-3.5" />复制 Variant</Button>}
                              {!factsConfirmed && <Button type="button" size="sm" variant="ghost" onClick={() => confirmFactsMutation.mutate(plan.id)} disabled={confirmFactsMutation.isPending} className="w-full justify-start px-0 text-xs text-muted-foreground hover:text-foreground">确认动态事实 snapshot</Button>}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3"><SectionHeader title="商品资产" description="优先使用本地商品图片/视频；Commerce 商品镜头会锁定这些资产。" actions={<><Select aria-label="商品素材类型" value={assetType} onChange={(event) => setAssetType(event.target.value as "image" | "video")} className="h-8 w-24 text-xs"><option value="image">图片</option><option value="video">视频</option></Select><label className="inline-flex"><input type="file" className="sr-only" accept={assetType === "image" ? "image/*" : "video/*"} onChange={(event) => { const file = event.target.files?.[0]; if (file) uploadMutation.mutate(file); event.target.value = ""; }} /><span className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground focus-within:outline-none focus-within:ring-2 focus-within:ring-ring"><Upload className="h-3.5 w-3.5" />上传</span></label></>} /></CardHeader>
                <CardContent><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{selected.assets.map((productAsset) => <div key={productAsset.id} className="overflow-hidden rounded-lg border border-border bg-secondary/25">{productAsset.asset?.file_path ? productAsset.asset_type === "video" ? <video controls preload="metadata" className="aspect-square w-full object-cover" src={assetUrl(productAsset.asset.file_path)} /> : <img src={assetUrl(productAsset.asset.file_path)} alt={productAsset.alt_text || selected.title} className="aspect-square w-full object-cover" /> : <div className="flex aspect-square items-center justify-center text-muted-foreground">{productAsset.asset_type === "video" ? <Video className="h-6 w-6" /> : <ImageIcon className="h-6 w-6" />}</div>}<div className="flex items-center justify-between gap-2 p-2 text-[11px] text-muted-foreground"><span className="truncate">{productAsset.role} · {productAsset.source_kind}</span><span className="flex shrink-0 items-center gap-2">{productAsset.source_url && <a href={productAsset.source_url} target="_blank" rel="noreferrer" aria-label="打开素材来源" className="text-primary"><ExternalLink className="h-3 w-3" /></a>}<button type="button" onClick={() => deleteAssetMutation.mutate(productAsset.id)} disabled={deleteAssetMutation.isPending} aria-label="移除商品素材" className="text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Trash2 className="h-3 w-3" /></button></span></div></div>)}</div>{selected.assets.length === 0 && <p className="text-sm text-muted-foreground">暂无商品资产，请上传商品图片或视频。</p>}</CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3"><SectionHeader title="Product Truth Sheet" description="每个事实和商业主张都保留来源与确定性。" /></CardHeader>
                <CardContent className="space-y-4"><div className="flex flex-wrap gap-2"><Badge variant="info"><ShieldCheck className="h-3 w-3" />事实来源可追溯</Badge>{selected.truth_sheet.unresolved_fields.map((field) => <Badge key={field} variant="warning">待确认：{field}</Badge>)}</div><div className="divide-y divide-border/60 rounded-lg border border-border/70">{selected.truth_sheet.facts.map((fact) => <div key={fact.id} className="grid grid-cols-1 gap-1 px-3 py-2.5 text-xs sm:grid-cols-[150px_minmax(0,1fr)_auto] sm:items-center"><span className="font-medium text-foreground">{fact.field}</span><span className="break-words text-muted-foreground">{String(fact.value)}</span><span className="flex items-center gap-1.5 sm:justify-end"><Badge variant={fact.certainty === "uncertain" ? "warning" : fact.certainty === "user_asserted" ? "success" : "secondary"}>{fact.certainty === "source_reported" ? "来源报告" : fact.certainty === "user_asserted" ? "用户确认" : "待确认"}</Badge><span className="text-muted-foreground">{sourceLabel(fact.source_type)}</span></span></div>)}</div><div><h3 className="mb-2 text-sm font-medium text-foreground">可用商业主张</h3><div className="space-y-2">{[...selected.truth_sheet.selling_points, ...selected.truth_sheet.numerical_claims].map((claim) => <div key={claim.id} className="rounded-lg border border-border/70 bg-card/40 px-3 py-2 text-xs"><div className="flex items-start justify-between gap-3"><span className="text-foreground">{claim.text}</span><Badge variant={claim.certainty === "uncertain" ? "warning" : "success"}>{claim.certainty === "uncertain" ? "待确认" : "可追溯"}</Badge></div><div className="mt-1 text-muted-foreground">证据：{claim.evidence_refs.join("、") || "未提供"}</div></div>)}</div></div></CardContent>
              </Card>
            </>
          )}
        </div>
      </div>

      <ConfirmDialog open={Boolean(productToDelete)} onOpenChange={(open) => !open && setProductToDelete(null)} title={`删除商品“${productToDelete?.title || ""}”？`} description="商品被 Commerce 任务引用时，服务端会拒绝删除。商品资产也会一并移除。" confirmLabel="删除商品" variant="destructive" onConfirm={() => deleteMutation.mutateAsync().then(() => undefined)} />
    </PageContainer>
  );
}

export default function ProductsPage() {
  return (
    <React.Suspense fallback={<PageContainer width="wide" className="space-y-5"><div className="h-8 w-48 animate-pulse rounded-lg bg-secondary/50" /><div className="h-96 animate-pulse rounded-xl bg-secondary/30" /></PageContainer>}>
      <ProductsPageContent />
    </React.Suspense>
  );
}
