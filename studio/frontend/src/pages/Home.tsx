import { NavLink, useNavigate } from "react-router-dom";
import type { IconName } from "../components/icons";
import { Icon } from "../components/icons";
import { Button } from "../components/ui";
import {
  RococoDivider,
  RococoFleuron,
  RococoRibbon,
} from "../components/rococo/RococoOrnaments";

/** 工坊入口：只指向已存在的页面，不虚构功能 */
const ENTRIES: Array<{ to: string; title: string; kicker: string; icon: IconName; text: string }> = [
  {
    to: "/workspace",
    title: "生成角色",
    kicker: "Générer",
    icon: "spark",
    text: "用一句话描述角色与风格，生成立绘，并自动进入像素重建、切帧对齐与引擎导入炉程。",
  },
  {
    to: "/scenes",
    title: "构建场景",
    kicker: "Scène",
    icon: "grid",
    text: "描述想去的世界，生成经过校验的横版跑酷路线或 PVE 战斗场景；完成后可任选角色直接开玩。",
  },
  {
    to: "/asset",
    title: "资产档案",
    kicker: "Dossier",
    icon: "cube",
    text: "统一的 CreativeAsset 档案：原画、调色板、动画、引擎配置与质量评估在一页读完。",
  },
  {
    to: "/playtest",
    title: "试玩舞台",
    kicker: "Jouer",
    icon: "play",
    text: "把角色载入试玩舞台，用键盘操控走位与攻击，检查动作衔接和操作手感。",
  },
];

export default function Home() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 py-6 md:px-7 md:py-8">
      {/* 卷首：直接让全站背景图的雾中城堡与花体标题作封面，不再用纸面板遮挡 */}
      <section
        aria-label="卷首"
        className="relative flex min-h-[clamp(360px,54vh,560px)] flex-col items-center justify-center px-4 pb-10 pt-24 text-center md:pt-28"
      >
        <RococoRibbon className="cf-rococo-ribbon--mist">
          Salon Bleu · Atelier des Assets
        </RococoRibbon>

        <h1 className="mt-7 max-w-[22ch] font-serif text-[30px] font-black leading-[1.32] tracking-[0.01em] [text-wrap:balance] md:text-[42px]">
          将想象，铸造成可创造的游戏世界。
        </h1>
        <p className="mt-2.5 font-display text-[16px] italic text-ink-3 md:text-[19px]">
          From imagination to worlds.
        </p>

        <div className="mt-6 flex items-center gap-2.5 text-line-strong">
          <span
            className="h-px w-12 bg-[linear-gradient(90deg,transparent,var(--color-line-strong))]"
            aria-hidden="true"
          />
          <RococoFleuron className="h-4 w-8" />
          <span
            className="h-px w-12 bg-[linear-gradient(270deg,transparent,var(--color-line-strong))]"
            aria-hidden="true"
          />
        </div>

        <Button
          variant="primary"
          size="lg"
          icon="spark"
          onClick={() => navigate("/workspace")}
          className="mt-6 h-11 px-7 shadow-e2 tracking-[0.18em]"
        >
          开始创作
        </Button>
        <p className="mt-3 text-[12px] tracking-[0.06em] text-ink-3">
          把一个想法，变成可直接使用的游戏资源
        </p>

        <RococoDivider className="mt-8 h-5 w-56 text-line-strong/75" />
      </section>

      {/* 工坊入口：四项已存在的能力，四列等宽对齐 */}
      <section aria-label="工坊入口" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {ENTRIES.map((entry) => (
          <NavLink
            key={entry.to}
            to={entry.to}
            className="group cf-sheen relative flex flex-col gap-3 overflow-hidden rounded-lg border border-line bg-paper/85 p-5 shadow-e1 backdrop-blur-[2px] transition-[border-color,box-shadow,transform] duration-(--motion-base) ease-standard hover:-translate-y-0.5 hover:border-line-strong hover:shadow-e2"
          >
            <span
              className="pointer-events-none absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,rgba(74,98,126,.45),var(--color-line),transparent)]"
              aria-hidden="true"
            />
            <span className="flex items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-line bg-surface-1 text-primary">
                <Icon name={entry.icon} className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="block font-serif text-[16px] font-black leading-6">{entry.title}</span>
                <span className="block font-mono text-[9px] uppercase tracking-[0.16em] text-ink-4">
                  {entry.kicker}
                </span>
              </span>
            </span>
            <p className="text-[12.5px] leading-[19px] text-ink-3 [text-wrap:pretty]">{entry.text}</p>
            <span className="mt-auto flex items-center justify-between border-t border-line-subtle pt-3">
              <span className="cf-ref">进入</span>
              <span className="grid h-6 w-6 place-items-center rounded-full border border-line text-ink-4 transition-colors duration-(--motion-fast) ease-standard group-hover:border-line-strong group-hover:bg-surface-1 group-hover:text-ink">
                <Icon name="chevron" className="h-3.5 w-3.5" />
              </span>
            </span>
          </NavLink>
        ))}
      </section>
    </div>
  );
}
