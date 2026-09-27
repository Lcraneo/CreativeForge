import { useNavigate } from "react-router-dom";
import { Badge, Button, Card } from "./ui";
import type { CreativeAsset } from "../types";

interface Props {
  asset: CreativeAsset;
}

/**
 * Result banner shown on the agent dashboard once a task passes: the produced
 * character image plus its model/engine provenance and quick links into the
 * asset inspector and the animation workbench.
 */
export function GenerationResult({ asset }: Props) {
  const navigate = useNavigate();
  const image =
    (asset as { image?: { url?: string; model?: string } }).image?.url ||
    asset.source?.ai_image?.url ||
    `/api/assets/${asset.id}/image.png?view=front&size=512`;
  const model =
    (asset as { image?: { model?: string } }).image?.model ||
    asset.source?.ai_image?.model ||
    "artgen-2d";
  const engine = (asset as { engine?: { target?: string } }).engine?.target;

  return (
    <Card title="生成结果 Generation Result" icon="spark" iconClassName="text-primary">
      <div className="flex flex-wrap items-center gap-5">
        <div className="grid h-36 w-36 shrink-0 place-items-center overflow-hidden rounded-xl border border-line-subtle bg-surface-1">
          <img src={image} alt={asset.name ?? "generated"} className="h-full w-full object-contain" />
        </div>
        <div className="min-w-[220px] flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[15px] font-semibold text-ink">{asset.name ?? asset.id}</span>
            <Badge tone="primary">{model}</Badge>
            {engine && <Badge tone="neutral">{engine}</Badge>}
          </div>
          {asset.source?.prompt && (
            <p className="mt-2 line-clamp-2 text-[12.5px] text-ink-3">{asset.source.prompt}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-3">
            <Button variant="primary" size="sm" icon="cube" onClick={() => navigate("/asset")}>
              查看资产
            </Button>
            <Button variant="secondary" size="sm" icon="film" onClick={() => navigate("/animation")}>
              动画工作台
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
