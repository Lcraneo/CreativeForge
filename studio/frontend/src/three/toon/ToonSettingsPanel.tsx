import { useState } from "react";
import { Button, Switch, cx } from "../../components/ui";
import { Icon } from "../../components/icons";
import {
  DEFAULT_TOON_PARAMETERS,
  TOON_PARAMETER_LIMITS,
  type ToonParameters,
} from "./ToonMaterial";

/** 数值型可调参数（描边颜色是字符串，走色板控件不走滑杆） */
type NumericParamKey = Exclude<keyof ToonParameters, "outlineColor">;

interface SliderSpec {
  key: NumericParamKey;
  label: string;
  min: number;
  max: number;
  step: number;
  format?: (value: number) => string;
}

const SLIDERS: SliderSpec[] = [
  {
    key: "outlineWidth",
    label: "描边宽度",
    ...TOON_PARAMETER_LIMITS.outlineWidth,
    format: (v) => v.toFixed(3),
  },
  {
    key: "colorSteps",
    label: "明暗色阶",
    ...TOON_PARAMETER_LIMITS.colorSteps,
    format: (v) => `${v} 阶`,
  },
  {
    key: "shadowThreshold",
    label: "阴影阈值",
    ...TOON_PARAMETER_LIMITS.shadowThreshold,
    format: (v) => v.toFixed(2),
  },
  {
    key: "specularRange",
    label: "高光范围",
    ...TOON_PARAMETER_LIMITS.specularRange,
    format: (v) => v.toFixed(2),
  },
  {
    key: "rimIntensity",
    label: "边缘光强度",
    ...TOON_PARAMETER_LIMITS.rimIntensity,
    format: (v) => v.toFixed(2),
  },
];

interface Props {
  params: ToonParameters;
  fps: number;
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
  onChange: (params: ToonParameters) => void;
}

/**
 * 三渲二卡通渲染配置面板：浮在 3D 视口右上角，可折叠。
 * 所有参数实时改 uniform，不重建材质。
 */
export default function ToonSettingsPanel({ params, fps, enabled, onToggle, onChange }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="pointer-events-auto absolute right-3 top-3 z-10 w-[264px] rounded-lg border border-line-subtle bg-surface/95 shadow-lg backdrop-blur-sm">
      <div className="flex items-center justify-between gap-2 border-b border-line-subtle px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Icon name="spark" className="h-3.5 w-3.5 text-accent" />
          <span className="text-[12px] font-semibold text-ink">卡通渲染参数</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cx(
              "font-mono text-[10.5px]",
              fps >= 50 ? "text-success" : fps >= 30 ? "text-warning" : "text-danger",
            )}
            title="实时渲染帧率（参数改动不重编译着色器）"
          >
            {fps} FPS
          </span>
          <Switch checked={enabled} onChange={onToggle} label="启用卡通渲染" />
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            className="rounded p-0.5 text-ink-4 transition-colors hover:text-ink-2"
            aria-label={collapsed ? "展开" : "折叠"}
          >
            <Icon
              name="chevron"
              className={cx(
                "h-3.5 w-3.5 transition-transform",
                collapsed ? "rotate-90" : "-rotate-90",
              )}
            />
          </button>
        </div>
      </div>

      {!collapsed && enabled && (
        <div className="flex flex-col gap-2.5 px-3 py-3">
          {SLIDERS.map((slider) => (
            <label key={slider.key} className="block">
              <span className="mb-1 flex items-center justify-between text-[11px] text-ink-3">
                <span>{slider.label}</span>
                <span className="font-mono text-ink-4">
                  {slider.format ? slider.format(params[slider.key]) : String(params[slider.key])}
                </span>
              </span>
              <input
                type="range"
                className="h-1.5 w-full cursor-pointer accent-[#a9812f]"
                min={slider.min}
                max={slider.max}
                step={slider.step}
                value={params[slider.key]}
                onChange={(event) =>
                  onChange({ ...params, [slider.key]: Number(event.target.value) })
                }
              />
            </label>
          ))}

          <label className="mt-0.5 flex items-center justify-between text-[11px] text-ink-3">
            <span>描边颜色</span>
            <span className="flex items-center gap-1.5">
              <span className="font-mono text-[10px] text-ink-4">{params.outlineColor}</span>
              <input
                type="color"
                className="h-5 w-7 cursor-pointer rounded border border-line-subtle bg-transparent p-0"
                value={params.outlineColor}
                onChange={(event) => onChange({ ...params, outlineColor: event.target.value })}
              />
            </span>
          </label>

          <Button
            variant="secondary"
            icon="refresh"
            className="mt-1 w-full"
            onClick={() => onChange({ ...DEFAULT_TOON_PARAMETERS })}
          >
            恢复默认
          </Button>
        </div>
      )}
    </div>
  );
}
