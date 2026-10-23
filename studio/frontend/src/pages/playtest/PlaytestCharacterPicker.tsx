/**
 * 试玩舞台 V2 · 角色选择弹层
 *
 * 旧版页面下方常驻的"近期生成"长卡片收拢为可收起弹层（role=dialog，
 * Esc 关闭）；未选择角色时自动打开。
 */
import { useEffect, useRef } from "react";
import { Badge, Button, EmptyState, SafeImage, Skeleton, cx } from "../../components/ui";
import { Icon } from "../../components/icons";
import type { HistorySummary } from "../../types";

export interface PlaytestCharacterPickerProps {
  open: boolean;
  loading: boolean;
  people: HistorySummary[];
  selectedId?: string | null;
  onClose: () => void;
  onSelect: (assetId: string) => void;
  onGoWorkbench: () => void;
}

export function PlaytestCharacterPicker(props: PlaytestCharacterPickerProps) {
  const { open, loading, people, selectedId, onClose, onSelect, onGoWorkbench } = props;
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/35 p-4 backdrop-blur-[2px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="选择试玩人物"
        className="w-full max-w-3xl rounded-2xl border border-line bg-canvas p-4 shadow-xl"
      >
        <div className="mb-3 flex items-center gap-2">
          <span className="font-display text-[15px] font-semibold text-ink">选择试玩人物 · 近期生成</span>
          <Badge tone="neutral" icon="cube">
            {people.length} 位候选
          </Badge>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="关闭人物挑选"
            className="ml-auto rounded-md p-1 text-ink-3 hover:bg-surface-1"
          >
            <Icon name="x" className="h-4 w-4" />
          </button>
        </div>
        {loading ? (
          /* 骨架与最终网格同构，加载完不跳版 */
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-[150px] rounded-xl" />
            ))}
          </div>
        ) : people.length === 0 ? (
          <EmptyState
            icon="cube"
            title="还没有可用的人物"
            description="先去工作台生成一个角色，再回到这里挑选。"
            action={
              <Button variant="primary" size="sm" icon="spark" onClick={onGoWorkbench}>
                去工作台生成
              </Button>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {people.map((record) => (
              <button
                key={record.id}
                onClick={() => record.asset_id && onSelect(record.asset_id)}
                className={cx(
                  "flex flex-col overflow-hidden rounded-xl border transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard",
                  selectedId === record.asset_id ? "border-primary/60" : "border-line-subtle hover:border-line",
                )}
              >
                <SafeImage
                  src={record.image?.url ?? undefined}
                  alt={String(record.name ?? record.asset_id ?? "")}
                  className="h-[120px] w-full bg-paper object-contain"
                />
                <span className="truncate px-2 py-1.5 text-[11px] text-ink-3">
                  {record.name || record.asset_id}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
