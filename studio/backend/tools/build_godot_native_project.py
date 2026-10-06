"""把 CreativeForge 通用 Godot 导出包升级为 Godot 4 原生工程 zip。

用途：线上真机验证。Godot 官方网页编辑器（editor.godotengine.org）的
项目管理器支持 Import 工程 zip——但现有导出包是「manifest + 图集」的
通用清单格式（路线图 E6 缺口），没有 project.godot / 场景文件，编辑器
无法直接打开播放。本脚本从包内图集合成最小可玩工程：

- project.godot          入口配置（main_scene 指向 main.tscn）
- frames.tres            SpriteFrames：每个动画 = N 个 AtlasTexture 子资源
                         （区域按 sheet 实际尺寸均分）+ 帧率/循环
- main.tscn              AnimatedSprite2D（autoplay=首个动画，缩放适配窗口）
- demo.gd                每 3 秒自动切换下一个动画（直观看到全部动作）
- animations/*.png       从原包原样复制

用法：python studio/backend/tools/build_godot_native_project.py [包zip路径]
缺省取 exports/ 下最新的 *godot*.zip。产物：exports/<asset>_godot_native.zip
"""

import json
import os
import sys
import time
import zipfile

from PIL import Image
import io as _io

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
EXPORTS_DIR = os.path.join(REPO, "studio", "backend", "exports")

WINDOW_W, WINDOW_H = 640, 480
# 网页编辑器轻量档：Godot web editor 的浏览器虚拟文件系统对大 zip 提取
# 不稳（28MB 包实测 PNG 提取失败 → 图集缺失连锁"缺少依赖"）。192px 帧
# 对像素画视觉无损，整包从 ~28MB 降到几 MB。
LIGHT_FRAME_WIDTH = 192


def _maybe_lighten(sheet_bytes: bytes, light: bool) -> tuple[bytes, int, int]:
    """light=True 时把横排条带等比缩到 LIGHT_FRAME_WIDTH 帧宽，返回 (bytes, w, h)。"""
    with Image.open(_io.BytesIO(sheet_bytes)) as handle:
        handle.load()  # 显式解码：惰性加载的 fp 在 resize 二次读取时会断言失败
        width, height = handle.size
        if not light or width <= LIGHT_FRAME_WIDTH * 2:
            return sheet_bytes, width, height
        frames = max(1, round(width / height)) if height else 1
        target_w = LIGHT_FRAME_WIDTH * frames
        target_h = max(1, round(height * target_w / width))
        resized = handle.resize((target_w, target_h), Image.LANCZOS)
    buffer = _io.BytesIO()
    resized.save(buffer, "PNG", optimize=True)
    return buffer.getvalue(), target_w, target_h


def _safe(name: str) -> str:
    import re

    return re.sub(r"[^\w-]+", "_", str(name), flags=re.UNICODE)


def latest_godot_package() -> str:
    candidates = [
        os.path.join(EXPORTS_DIR, name)
        for name in os.listdir(EXPORTS_DIR)
        if name.endswith(".zip") and "godot" in name.lower()
    ]
    if not candidates:
        raise SystemExit("exports/ 下没有 godot 包——先在导出中心导出一次 Godot 包")
    return max(candidates, key=os.path.getmtime)


def build(package_path: str, light: bool = True) -> str:
    with zipfile.ZipFile(package_path) as package:
        manifest = json.loads(package.read("manifest.json"))
        asset = manifest.get("asset") or {}
        asset_id = asset.get("id") or "character"

        # 收集动画：manifest 声明 + 包内 sheet 实存
        animations = []
        for entry in manifest.get("animations") or []:
            action = entry.get("action")
            engine = entry.get("engine") or "video"
            sheet_name = "{}__{}_sheet.png".format(action, engine)
            sheet_path = "animations/" + sheet_name
            if sheet_path not in package.namelist():
                continue
            sheet_bytes, sheet_w, sheet_h = _maybe_lighten(package.read(sheet_path), light)
            frames = int(entry.get("frames") or 1)
            fps = float(entry.get("fps") or 12)
            if frames < 1 or sheet_w % frames:
                # 布局异常时按整除回退，避免 region 越界
                frames = max(1, sheet_w // max(1, sheet_h or 1))
            frame_w = sheet_w // frames
            animations.append(
                {
                    "action": action,
                    "sheet_name": sheet_name,
                    "sheet_bytes": sheet_bytes,
                    "sheet_w": sheet_w,
                    "sheet_h": sheet_h,
                    "frames": frames,
                    "fps": fps,
                }
            )
        if not animations:
            raise SystemExit("包内没有可用的动画条带图（*_sheet.png）")

        # frames.tres：ext_resource 每图集一条；子资源 AtlasTexture 逐帧
        ext_lines = []
        sub_lines = []
        anim_blocks = []
        for index, anim in enumerate(animations, start=1):
            res_id = "sheet_{}".format(index)
            ext_lines.append(
                '[ext_resource type="Texture2D" path="res://animations/{name}" id="{rid}"]'.format(
                    name=anim["sheet_name"], rid=res_id
                )
            )
            frame_ids = []
            for frame_index in range(anim["frames"]):
                sub_id = "Atlas_{}_{}".format(index, frame_index)
                frame_ids.append(sub_id)
                sub_lines.append(
                    '[sub_resource type="AtlasTexture" id="{sid}"]\n'
                    'atlas = ExtResource("{rid}")\n'
                    "region = Rect2({x}, 0, {w}, {h})\n".format(
                        sid=sub_id,
                        rid=res_id,
                        x=frame_index * (anim["sheet_w"] // anim["frames"]),
                        w=anim["sheet_w"] // anim["frames"],
                        h=anim["sheet_h"],
                    )
                )
            frame_items = ", ".join(
                '{{\n"duration": 1.0,\n"texture": SubResource("{sid}")\n}}'.format(sid=sid)
                for sid in frame_ids
            )
            anim_blocks.append(
                '{{\n"frames": [{items}],\n"loop": true,\n"name": &"{name}",\n"speed": {speed}\n}}'.format(
                    items=frame_items, name=anim["action"], speed=anim["fps"]
                )
            )
        load_steps = len(ext_lines) + len(sub_lines) + 1
        frames_tres = "\n".join(
            [
                '[gd_resource type="SpriteFrames" load_steps={} format=3]'.format(load_steps),
                "",
                *ext_lines,
                "",
                "\n".join(sub_lines),
                "[resource]",
                "animations = [{}]".format(", ".join(anim_blocks)),
                "",
            ]
        )

        project_godot = "\n".join(
            [
                "config_version=5",
                "",
                "[application]",
                'config/name="CreativeForge {}"'.format(asset.get("name") or asset_id),
                'run/main_scene="res://main.tscn"',
                'config/features=PackedStringArray("4.3")',
                "",
                "[display]",
                "window/size/viewport_width={}".format(WINDOW_W),
                "window/size/viewport_height={}".format(WINDOW_H),
                "",
            ]
        )

        # 缩放：让最高的角色落进窗口（sheet 高即角色高）
        max_h = max(anim["sheet_h"] for anim in animations)
        scale = round(min(1.0, (WINDOW_H * 0.8) / max(1, max_h)), 3)

        main_tscn = "\n".join(
            [
                "[gd_scene load_steps=3 format=3]",
                "",
                '[ext_resource type="Script" path="res://demo.gd" id="1_script"]',
                '[ext_resource type="SpriteFrames" path="res://frames.tres" id="2_frames"]',
                "",
                '[node name="Character" type="AnimatedSprite2D"]',
                "position = Vector2({}, {})".format(WINDOW_W // 2, WINDOW_H // 2),
                "scale = Vector2({}, {})".format(scale, scale),
                'sprite_frames = ExtResource("2_frames")',
                'animation = "{}"'.format(animations[0]["action"]),
                'autoplay = "{}"'.format(animations[0]["action"]),
                'script = ExtResource("1_script")',
                "",
            ]
        )

        demo_gd = "\n".join(
            [
                "extends AnimatedSprite2D",
                "",
                "# 演示脚本：每 3 秒切换到下一个动画，直观巡览全部动作；",
                "# 也可直接在动画面板手动点选任意动画。",
                "",
                "var _actions: PackedStringArray = PackedStringArray()",
                "var _index := 0",
                "",
                "",
                "func _ready() -> void:",
                "\t_actions = sprite_frames.get_animation_names()",
                "\tvar timer := Timer.new()",
                "\ttimer.wait_time = 3.0",
                "\ttimer.autostart = true",
                "\ttimer.timeout.connect(_next_action)",
                "\tadd_child(timer)",
                "",
                "",
                "func _next_action() -> void:",
                "\tif _actions.is_empty():",
                "\t\treturn",
                "\t_index = (_index + 1) % _actions.size()",
                "\tplay(_actions[_index])",
                "",
            ]
        )

        readme = "\n".join(
            [
                "# CreativeForge Godot 原生工程（真机验证用）",
                "",
                "资产：{}（{}）".format(asset.get("name") or asset_id, asset_id),
                "生成：{}，来源包：{}".format(
                    time.strftime("%Y-%m-%d %H:%M"), os.path.basename(package_path)
                ),
                "",
                "## 网页编辑器玩法（零安装）",
                "1. 打开 https://editor.godotengine.org/releases/latest/（首次加载约 1-2 分钟）",
                "2. 项目管理器点 Import → 选择本 zip",
                "3. 双击打开工程 → 左侧 FileSystem 双击 main.tscn → 按 F5（播放）",
                "4. 角色每 3 秒自动切换 idle/walk/run/attack/jump；也可在底部动画面板手动点选",
                "",
                "## 包含动画",
                *[ "- {}：{} 帧 @ {}fps（{}）".format(a["action"], a["frames"], a["fps"], a["sheet_name"]) for a in animations ],
                "",
                "注意：网页编辑器的工程存在浏览器 IndexedDB 里，清浏览器数据会丢；",
                "正式开发请用桌面版 Godot（免安装、无登录）。",
                "",
            ]
        )

        out_name = "{}_godot_native{}.zip".format(_safe(asset_id), "" if light else "_full")
        out_path = os.path.join(EXPORTS_DIR, out_name)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out:
            out.writestr("project.godot", project_godot)
            out.writestr("frames.tres", frames_tres)
            out.writestr("main.tscn", main_tscn)
            out.writestr("demo.gd", demo_gd)
            out.writestr("README_GODOT.md", readme)
            for anim in animations:
                out.writestr("animations/" + anim["sheet_name"], anim["sheet_bytes"])

        print("== Godot 原生工程已生成 ==")
        print("  产物:", out_path)
        print("  动画:", ", ".join("{}({}帧@{}fps, {}x{})".format(
            a["action"], a["frames"], a["fps"], a["sheet_w"] // a["frames"], a["sheet_h"]
        ) for a in animations))
        print("  角色缩放:", scale)
        return out_path


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    light = "--full" not in sys.argv[1:]  # 缺省轻量档（网页编辑器友好）；--full 保原尺寸
    package = args[0] if args else latest_godot_package()
    build(package, light=light)
