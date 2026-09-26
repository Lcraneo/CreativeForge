import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssetLoader } from "../stores/assetStore";
import { toast } from "../stores/toastStore";
import { Badge, Button, Card, EmptyState, PageHeader } from "../components/ui";
import { DesignSheet } from "../components/DesignSheet";
import { CharacterArt } from "../components/CharacterArt";

export default function DesignCenter() {
  const asset = useAssetLoader();
  const navigate = useNavigate();
  const sheetRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);

  function serialize() {
    const svg = sheetRef.current?.querySelector("svg");
    if (!svg) return null;
    const clone = svg.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", "1680");
    clone.setAttribute("height", "1000");
    return new XMLSerializer().serializeToString(clone);
  }

  function download(name: string, href: string) {
    const link = document.createElement("a");
    link.href = href;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function exportSvg() {
    const data = serialize();
    if (!data) return;
    const blob = new Blob([data], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    download(`${asset?.id ?? "character"}-design-sheet.svg`, url);
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast({ tone: "success", title: "已导出 SVG 设计稿" });
  }

  async function exportPng() {
    const data = serialize();
    if (!data || busy) return;
    setBusy(true);
    try {
      const image = new Image();
      const svgUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(data)}`;
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error("SVG 渲染失败"));
        image.src = svgUrl;
      });
      const scale = 2;
      const canvas = document.createElement("canvas");
      canvas.width = 1680 * scale;
      canvas.height = 1000 * scale;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas 不可用");
      context.fillStyle = "#f4f0e9";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("PNG 生成失败");
      const url = URL.createObjectURL(blob);
      download(`${asset?.id ?? "character"}-design-sheet.png`, url);
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast({ tone: "success", title: "已导出 PNG 设计稿", description: "3360 × 2000 高清" });
    } catch (cause) {
      toast({ tone: "danger", title: "导出失败", description: String(cause) });
    } finally {
      setBusy(false);
    }
  }

  if (!asset) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="layers"
            title="还没有可出图的资产"
            description="先生成一个角色，或在历史记录中打开任意一次生成，即可查看并导出三视图设计稿。"
            action={
              <div className="flex gap-2">
                <Button variant="primary" icon="spark" onClick={() => navigate("/")}>
                  去生成角色
                </Button>
                <Button variant="secondary" icon="clock" onClick={() => navigate("/history")}>
                  打开历史记录
                </Button>
              </div>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Design Sheet"
        title="角色设计三视图"
        description="正视图 / 侧视图 / 俯视图 + 面部细节，含尺寸标注、关键细节说明、配色板与工程标题栏"
        actions={
          <>
            <Badge tone="primary" icon="cube">
              {asset.name ?? asset.id}
            </Badge>
            <Button variant="secondary" icon="download" onClick={exportSvg}>
              导出 SVG
            </Button>
            <Button variant="primary" icon="download" loading={busy} onClick={exportPng}>
              导出 PNG
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-3 rounded-xl border border-line-subtle bg-[#0a0e15] px-3 py-2">
          <CharacterArt
            spec={asset.character}
            palette={asset.pixel?.palette.colors}
            view="bust"
            className="h-14 w-12"
            detail="simple"
          />
          <div className="text-[11.5px] leading-4 text-ink-3">
            <div className="text-[12.5px] font-semibold text-ink">{asset.character?.summary ?? asset.name}</div>
            <div>
              {asset.character?.height_cm}cm · {asset.character?.build_label} · {asset.character?.weapon_label}
            </div>
          </div>
        </div>
        <span className="text-[11.5px] text-ink-3">
          比例尺与尺寸按 {asset.character?.height_cm ?? 170}cm 身高换算；单位 cm。
        </span>
        {asset.image && (
          <Badge tone="primary" icon="spark">
            正视图使用 {asset.image.model} 生成原画
          </Badge>
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line-subtle bg-[#f4f0e9] p-3 shadow-e3">
        <div ref={sheetRef} className="mx-auto min-w-[1180px]" style={{ maxWidth: 1680 }}>
          <DesignSheet
            spec={asset.character}
            palette={asset.pixel?.palette.colors}
            name={asset.name}
            assetId={asset.id}
            prompt={asset.source.prompt}
            imageUrl={asset.image?.url}
          />
        </div>
      </div>
    </div>
  );
}
