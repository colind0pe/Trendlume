"use client";

import Link from "next/link";
import { ExternalLink, PackageCheck, ShoppingBag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/field";
import { CREATIVE_ANGLE_OPTIONS } from "@/lib/ui-constants";
import { CreativeAngle, CreativePlan, Product } from "@/lib/types";

export interface CommerceTaskFormProps {
  products: Product[];
  productsLoading?: boolean;
  productId: string;
  onProductIdChange: (value: string) => void;
  creativePlans: CreativePlan[];
  creativePlansLoading?: boolean;
  creativePlanId: string;
  onCreativePlanIdChange: (value: string) => void;
  creativeAngle: CreativeAngle;
  onCreativeAngleChange: (value: CreativeAngle) => void;
  taskTitle: string;
  onTaskTitleChange: (value: string) => void;
}

export function CommerceTaskForm({
  products,
  productsLoading = false,
  productId,
  onProductIdChange,
  creativePlans,
  creativePlansLoading = false,
  creativePlanId,
  onCreativePlanIdChange,
  creativeAngle,
  onCreativeAngleChange,
  taskTitle,
  onTaskTitleChange,
}: CommerceTaskFormProps) {
  const selectedProduct = products.find((product) => product.id === productId);
  const activePlans = creativePlans.filter((plan) => plan.status !== "archived");

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-amber-500/25 bg-amber-500/[0.06] px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <ShoppingBag className="h-4 w-4 text-amber-500" />
          Commerce 商品视频
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          先选择商品事实，再规划商业镜头。商品主体镜头会锁定商品库的真实素材，不会为了生成效果自动重绘商品。
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className="text-sm font-medium text-foreground">Creative Plan <span className="text-destructive">*</span></span>
            <p className="mt-1 text-xs text-muted-foreground">先选择已审阅的方向，再进入 storyboard/media；这里不会重新生成方案。</p>
          </div>
          <Link href={selectedProduct ? `/products?product=${encodeURIComponent(selectedProduct.id)}` : "/products"} className="shrink-0 text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">管理方案</Link>
        </div>
        {creativePlansLoading ? (
          <div className="h-20 animate-pulse rounded-lg bg-secondary/50" />
        ) : activePlans.length === 0 ? (
          <div className="rounded-lg border border-dashed border-amber-500/40 bg-amber-500/[0.05] px-3 py-3 text-xs leading-relaxed text-muted-foreground">
            尚未生成方案。请先打开商品库的 Creative Planning，生成并选择一个方案。
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {activePlans.map((plan) => {
              const selected = plan.id === creativePlanId;
              return (
                <button
                  key={plan.id}
                  type="button"
                  onClick={() => { onCreativePlanIdChange(plan.id); onCreativeAngleChange(plan.angle); }}
                  aria-pressed={selected}
                  className={`min-h-[116px] rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selected ? "border-primary bg-primary/10 ring-1 ring-primary/60" : "border-border bg-card hover:bg-secondary/60"}`}
                >
                  <div className="flex items-center justify-between gap-2"><span className="truncate text-xs font-semibold text-foreground">{plan.variant_label}</span><Badge variant={selected ? "success" : "outline"}>{plan.status === "selected" ? "已选" : "可选"}</Badge></div>
                  <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-foreground">{plan.hook}</p>
                  <p className="mt-2 text-[11px] text-muted-foreground">{plan.scene_outline.length} 个 scene beat · {plan.claims.length} 个主张</p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <label htmlFor="commerce-product" className="flex items-center gap-1 text-sm font-medium text-foreground">
          商品 <span className="text-destructive">*</span>
        </label>
        <Select
          id="commerce-product"
          value={productId}
          onChange={(event) => onProductIdChange(event.target.value)}
          required
          disabled={productsLoading || products.length === 0}
          className="h-10 text-sm"
        >
          <option value="">{productsLoading ? "正在加载商品…" : products.length ? "选择商品事实卡" : "暂无商品，请先创建商品"}</option>
          {products.map((product) => (
            <option key={product.id} value={product.id}>
              {product.brand ? `${product.brand} · ` : ""}{product.title}
            </option>
          ))}
        </Select>
        {selectedProduct ? (
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
            <Badge variant="success"><PackageCheck className="h-3 w-3" />{selectedProduct.assets.filter((asset) => asset.asset_id).length} 个真实素材</Badge>
            {selectedProduct.truth_sheet.unresolved_fields.length > 0 && (
              <Badge variant="warning">{selectedProduct.truth_sheet.unresolved_fields.length} 项待确认</Badge>
            )}
            <Link href={`/products?product=${encodeURIComponent(selectedProduct.id)}`} className="inline-flex items-center gap-1 text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
              查看商品事实 <ExternalLink className="h-3 w-3" />
            </Link>
          </div>
        ) : (
          <Link href="/products" className="inline-flex items-center gap-1 text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
            前往商品库创建商品 <ExternalLink className="h-3 w-3" />
          </Link>
        )}
      </div>

      <div className="space-y-1.5">
        <label htmlFor="commerce-task-title" className="text-sm font-medium text-foreground">任务名称</label>
        <Input
          id="commerce-task-title"
          value={taskTitle}
          onChange={(event) => onTaskTitleChange(event.target.value)}
          placeholder={selectedProduct?.title || "例如：新品核心卖点短视频"}
          className="h-10 text-sm"
        />
      </div>

      <div className="space-y-2">
        <div>
          <span className="text-sm font-medium text-foreground">创意角度</span>
          <p className="mt-1 text-xs text-muted-foreground">角度只决定表达策略；商品事实仍以 Truth Sheet 为准。</p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {CREATIVE_ANGLE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onCreativeAngleChange(option.value)}
              aria-pressed={creativeAngle === option.value}
              className={`rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                creativeAngle === option.value
                  ? "border-primary bg-primary/10 text-foreground ring-1 ring-primary/70"
                  : "border-border bg-card text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
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
