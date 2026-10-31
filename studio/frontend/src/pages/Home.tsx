import { NavLink, useNavigate } from "react-router-dom";
import type { IconName } from "../components/icons";
import { Icon } from "../components/icons";
import { Button, Stamp } from "../components/ui";
import {
  RococoCorner,
  RococoDivider,
  RococoFleuron,
  RococoRibbon,
} from "../components/rococo/RococoOrnaments";
import { RococoBackdrop } from "../components/rococo/RococoBackdrop";

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
      {/* 卷首插画：雾气、城堡与花体标题 */}
      <section className="cf-sheen relative overflow-hidden rounded-lg border border-line bg-paper shadow-e1">
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
          <div className="absolute inset-0 bg-[radial-gradient(900px_420px_at_50%_-16%,rgba(255,255,255,.92),transparent_72%),radial-gradient(760px_360px_at_8%_118%,rgba(174,191,215,.42),transparent_70%),radial-gradient(820px_380px_at_96%_112%,rgba(147,169,196,.38),transparent_72%)]" />
          <div className="cf-home-castle">
            <RococoBackdrop />
          </div>
          <RococoCorner className="absolute left-3 top-3 h-24 w-24 text-line/40" />
          <RococoCorner className="absolute right-3 top-3 h-24 w-24 rotate-90 text-line/40" />
          <RococoCorner className="absolute bottom-3 left-3 h-20 w-20 rotate-180 text-line/25" />
          <RococoCorner className="absolute bottom-3 right-3 h-20 w-20 -rotate-90 text-line/25" />
        </div>

        {/* 浮动便笺：纸面手迹，纯装饰 */}
        <div
          className="pointer-events-none absolute left-7 top-9 hidden w-40 -rotate-6 rounded-sm border border-line bg-paper/85 p-3.5 shadow-e1 xl:block"
          aria-hidden="true"
        >
          <div className="font-display text-[15px] italic leading-6 text-ink-3">
            Rêver · Créer · Jouer
          </div>
          <span className="mt-2.5 block h-px bg-line" />
          <div className="mt-2 font-serif text-[10.5px] leading-4 text-ink-4">
            以一笔一画，铸造世界
          </div>
        </div>
        <div className="pointer-events-none absolute right-6 top-6 hidden select-none flex-col items-center gap-3 xl:flex" aria-hidden="true">
          <Stamp char="造" tone="ember" size={26} />
          <span className="cf-vertical font-serif text-[11px] font-semibold text-ink-3">蓝雾工坊</span>
        </div>

        <div className="relative z-10 flex min-h-[clamp(380px,54vh,560px)] flex-col items-center justify-center px-5 py-14 text-center md:py-16">
          <RococoRibbon className="cf-rococo-ribbon--mist">
            AI Game Asset Creation Studio
          </RococoRibbon>

          <h1 className="mt-6 font-display text-[52px] font-semibold leading-[0.95] tracking-[-0.03em] md:text-[76px] lg:text-[88px]">
            CreativeForge
          </h1>

          <div className="mt-4 flex items-center gap-2.5 text-line-strong">
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

          <p className="mt-4 font-serif text-[20px] font-black leading-8 tracking-[0.01em] md:text-[24px]">
            将想象，铸造成可创造的游戏世界。
          </p>
          <p className="mt-1.5 font-display text-[15px] italic text-ink-3 md:text-[17px]">
            From imagination to worlds.
          </p>

          <Button
            variant="primary"
            size="lg"
            icon="spark"
            onClick={() => navigate("/workspace")}
            className="mt-7 h-11 px-7 tracking-[0.18em]"
          >
            开始创作
          </Button>
          <p className="mt-3 text-[12px] tracking-[0.06em] text-ink-3">
            把一个想法，变成可直接使用的游戏资源
          </p>

          <RococoDivider className="mt-8 h-5 w-56 text-line-strong/75" />
        </div>
      </section>

      {/* 工坊入口：与卷首同一纸面语言，五项已存在的能力 */}
      <section aria-label="工坊入口" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {ENTRIES.map((entry) => (
          <NavLink
            key={entry.to}
            to={entry.to}
            className="group cf-sheen relative flex flex-col gap-3 overflow-hidden rounded-lg border border-line bg-paper p-5 shadow-e1 transition-[border-color,box-shadow,transform] duration-(--motion-base) ease-standard hover:-translate-y-0.5 hover:border-line-strong hover:shadow-e2"
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
