/**
 * 试玩舞台 V2 · 薄入口
 *
 * 实现全部在 ./playtest/ 下（原生 Canvas 渲染，无 react-konva/konva）。
 * 本文件只负责资产绑定（?asset= 深链 → 当前角色）与按角色重挂载。
 */
import { SelectedAssetBoundary } from "../components/SelectedAssetBoundary";
import { PlaytestContent } from "./playtest/PlaytestPage";

export default function PlaytestStage() {
  return (
    <SelectedAssetBoundary>
      {(asset) => <PlaytestContent key={asset?.id ?? "unselected"} selected={asset} />}
    </SelectedAssetBoundary>
  );
}
