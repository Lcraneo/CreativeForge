/** API 配置参数校验（工作台面板与模型广场共用同一套规则，保证口径一致）。 */

export type SettingsScope = "image" | "video" | "all";

export type SettingsValidationErrors = Record<string, string>;

const URL_PATTERN = /^https?:\/\/.+/i;
const SIZE_PATTERN = /^\d{2,4}[x*]\d{2,4}$/i;

export interface SettingsValidationInput {
  enabled?: boolean;
  base_url?: string;
  api_key?: string;
  model?: string;
  chat_model?: string;
  video_model?: string;
  use_chat?: boolean;
  use_image?: boolean;
  use_video?: boolean;
  size?: string;
  video_size?: string;
  timeout?: number | string;
}

/** 校验一份（部分）配置。返回字段 → 错误信息；空对象 = 通过。 */
export function validateModelSettings(
  input: SettingsValidationInput,
  scope: SettingsScope = "all",
): SettingsValidationErrors {
  const errors: SettingsValidationErrors = {};

  if (input.base_url != null && input.base_url && !URL_PATTERN.test(input.base_url)) {
    errors.base_url = "Base URL 必须以 http:// 或 https:// 开头";
  }
  if (input.api_key != null && input.api_key) {
    if (/\s/.test(input.api_key)) errors.api_key = "API Key 不能包含空格";
    else if (input.api_key.length < 8) errors.api_key = "API Key 长度异常（至少 8 位）";
  }
  if (input.size != null && input.size && !SIZE_PATTERN.test(input.size)) {
    errors.size = "生图尺寸格式：宽x高，如 1024x1024";
  }
  if (input.video_size != null && input.video_size && !SIZE_PATTERN.test(input.video_size)) {
    errors.video_size = "视频尺寸格式：宽*高，如 1280*720";
  }
  if (input.timeout != null && input.timeout !== ("") as unknown) {
    const timeout = Number(input.timeout);
    if (!Number.isFinite(timeout) || timeout < 10 || timeout > 600) {
      errors.timeout = "超时需在 10 ~ 600 秒之间";
    }
  }

  // 工作台作用域只校验本工作台关心的字段；模型广场（all）额外校验启用态完整性
  const needsImage = scope === "image" || scope === "all";
  const needsVideo = scope === "video" || scope === "all";
  if (needsImage && input.enabled && !String(input.model ?? "").trim()) {
    errors.model = "启用图像生成时必须填写图像模型";
  }
  if (needsVideo && input.enabled && !String(input.video_model ?? "").trim()) {
    errors.video_model = "启用视频生成时必须填写视频模型";
  }
  if (scope === "all" && input.enabled && !String(input.chat_model ?? "").trim() && input.use_chat) {
    errors.chat_model = "启用文本增强时必须填写对话模型";
  }
  return errors;
}

/** 保存前把错误对象转成提示文本；无错误返回 null。 */
export function firstError(errors: SettingsValidationErrors): string | null {
  const entries = Object.entries(errors);
  return entries.length ? `${entries[0][1]}` : null;
}
