"""风格提示词模板库（出图质量下限保障）。

与「提示词增强」（ChatProvider，有随机性）互补的**确定性**规则：每套模板
是一段固定风格条款，由前端幂等拼接到用户提示词尾部（带「【风格】」标记，
可整段移除），不依赖模型发挥、不消耗对话额度。

约束：``clause`` 不得包含「【」「】」——前端按该标记整段剥离已套用条款。
"""

STYLE_TEMPLATES = {
    "pixel": {
        "label": "像素游戏",
        "clause": (
            "像素艺术游戏素材风格：清晰的像素网格、有限的 16~32 色调色板、"
            "1 像素描边、干净平涂色块、无抗锯齿（pixel art, limited palette, crisp pixels, clean outlines)"
        ),
        "negative": "blurry, anti-aliasing, smooth gradients, photorealistic, painterly",
        "note": "RPG / roguelike 立绘与 sprite 首选",
    },
    "anime": {
        "label": "日式动漫",
        "clause": (
            "日式动漫赛璐璐风格：干净利落的线稿、平整色块、柔和双层阴影、"
            "通透高光、和谐的高饱和点缀色（anime cel-shading, clean lineart, flat colors）"
        ),
        "negative": "photorealistic, muddy colors, rough sketch",
        "note": "二次元角色立绘通用",
    },
    "chibi": {
        "label": "Q 版可爱",
        "clause": (
            "Q 版二头身风格：大脑袋小身体、圆润简洁的轮廓、软萌表情、"
            "高明度低饱和配色、整体圆润无锐角（chibi style, big head, rounded shapes, cute）"
        ),
        "negative": "realistic proportions, gritty, horror",
        "note": "休闲/手游形象、表情包素材",
    },
    "ink": {
        "label": "中国水墨",
        "clause": (
            "中国水墨画风格：写意笔触、墨分五色、计白当黑的留白构图、"
            "淡淡的宣纸底色、一两个朱砂印章点缀（chinese ink painting, xieyi brushwork）"
        ),
        "negative": "neon, cyberpunk, 3d render, heavy saturation",
        "note": "国风角色与场景",
    },
    "watercolor": {
        "label": "水彩插画",
        "clause": (
            "水彩插画风格：透明叠色、柔和晕染边缘、纸张肌理、"
            "明快清新的光线、少量留白呼吸感（watercolor illustration, soft washes, paper texture）"
        ),
        "negative": "hard outlines, thick paint, digital gloss",
        "note": "绘本感角色与道具",
    },
    "cyberpunk": {
        "label": "赛博朋克",
        "clause": (
            "赛博朋克风格：霓虹光源（青/品红为主）、高对比明暗、"
            "雨夜反光质感、科技义体与全息元素点缀（cyberpunk, neon rim light, rain-soaked）"
        ),
        "negative": "pastel colors, rural, daylight pastel scene",
        "note": "科幻都市角色",
    },
    "darkfantasy": {
        "label": "暗黑奇幻",
        "clause": (
            "暗黑奇幻风格：厚重的体积光、低饱和大地色配冷调点缀、"
            "精致的金属与皮革质感、戏剧化的伦勃朗布光（dark fantasy, dramatic lighting, ornate armor）"
        ),
        "negative": "cute, chibi, flat pastel colors",
        "note": "Boss / 重甲角色",
    },
    "flat": {
        "label": "扁平几何",
        "clause": (
            "扁平化矢量插画风格：几何化的简洁形状、无描边或极细描边、"
            "有限的高饱和撞色、干净的大色块与轻微噪点肌理（flat vector illustration, geometric shapes）"
        ),
        "negative": "realistic shading, gradients, texture overload",
        "note": "图标化角色、UI 吉祥物",
    },
    "realistic": {
        "label": "写实概念",
        "clause": (
            "写实概念设计风格：电影级布光、真实材质细节（皮肤孔隙、织物纹理、"
            "金属磨损）、克制的配色、三视图级别的结构严谨（realistic concept art, cinematic lighting）"
        ),
        "negative": "cartoon, chibi, flat colors",
        "note": "影视级角色概念",
    },
    "retro": {
        "label": "复古 16-bit",
        "clause": (
            "复古 16-bit 游戏机风格：SFC 时代的有限色板、dither 抖动过渡、"
            "略微降低的分辨率质感、经典 JRPG 立绘构图（16-bit retro game art, dithering, SNES era）"
        ),
        "negative": "modern smooth shading, 3d render",
        "note": "怀旧主机游戏风",
    },
}
