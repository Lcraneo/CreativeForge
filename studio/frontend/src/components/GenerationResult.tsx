import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Badge, Button, Card, SafeImage } from "./ui";
import { toast } from "../stores/toastStore";
import { assetHref, useAssetStore } from "../stores/assetStore";
import type { CreativeAsset } from "../types";

interface Props {
  asset: CreativeAsset;
}

/**
 * Result banner shown on the agent dashboard once a task passes: the produced
 * character image plus its model/engine provenance, the human review verdict
 * (通过 / 重做 — P1 体验：机器审 + 人工审双关卡) and quick links.
 */
export function GenerationResult({ asset }: Props) {
  const navigate = useNavigate();
  const setAsset = useAssetStore((state) => state.set);
  const [reviewing, setReviewing] = useState<"pass" | "redo" | null>(null);
  const image =
    (asset as { image?: { url?: string; model?: string; cached?: boolean } }).image?.url ||
    asset.source?.ai_image?.url ||
    `/api/assets/${asset.id}/image.png?view=front&size=512`;
  const model =
    (asset as { image?: { model?: string } }).image?.model ||
    asset.source?.ai_image?.model ||
    "artgen-2d";
  const cached = (asset as { image?: { cached?: boolean } }).image?.cached === true;
  const engine = (asset as { engine?: { target?: string } }).engine?.target;
  const review = asset.review;

  async function submitReview(approved: boolean) {
    if (!asset.id || reviewing) return;
    setReviewing(approved ? "pass" : "redo");
    try {
      const result = await api.reviewAsset(asset.id, approved);
      setAsset({ ...asset, review: result.review });
      toast({
        tone: approved ? "success" : "warning",
        title: approved ? "已通过审核" : "已标记重做",
        description: approved
          ? "资产进入可用状态，已记录到历史"
          : "可在工作台调整提示词后重新生成，历史版本可在版本控制中心回溯",
      });
    } catch (cause) {
      toast({ tone: "danger", title: "审核操作失败", description: String(cause).slice(0, 160) });
    } finally {
      setReviewing(null);
    }
  }

  return (
    <Card title="生成结果 Generation Result" icon="spark" iconClassName="text-primary">
      <div className="flex flex-wrap items-center gap-5">
        <div className="grid h-36 w-36 shrink-0 place-items-center overflow-hidden rounded-xl border border-line-subtle bg-surface-1">
          <SafeImage
            src={image}
            alt={asset.name ?? "generated"}
            className="h-full w-full object-contain"
          />
        </div>
        <div className="min-w-[220px] flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-semibold text-ink">{asset.name ?? asset.id}</span>
            <Badge tone="primary">{model}</Badge>
            {cached && <Badge tone="neutral">来自缓存 · 零额度</Badge>}
            {engine && <Badge tone="neutral">{engine}</Badge>}
            {review?.approved === true && <Badge tone="success">人工审核通过</Badge>}
            {review?.approved === false && <Badge tone="warning">待重做</Badge>}
            {asset.model_fallback && (
              <span
                title={`AI 生图失败：${asset.model_fallback.detail}`}
                className="inline-block"
              >
                <Badge tone="warning">AI 生图失败 · 离线示意</Badge>
              </span>
            )}
          </div>
          {asset.model_fallback && (
            <p className="mt-2 text-[11.5px] leading-[18px] text-warning">
              AI 生图失败（{asset.model_fallback.detail}），当前展示的是离线确定性示意，可能与目标主题不符；可在历史记录中一键重试。
            </p>
          )}
          {asset.source?.prompt && (
            <p className="mt-2 line-clamp-2 text-[12.5px] text-ink-3">{asset.source.prompt}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-3">
            <Button variant="primary" size="sm" icon="cube" onClick={() => navigate(assetHref("/asset", asset.id))}>
              查看资产
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon="film"
              onClick={() => navigate(assetHref("/animation", asset.id))}
            >
              动画工作台
            </Button>
            {!review && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="check"
                  loading={reviewing === "pass"}
                  onClick={() => submitReview(true)}
                >
                  审核通过
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon="refresh"
                  loading={reviewing === "redo"}
                  onClick={() => submitReview(false)}
                >
                  标记重做
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
