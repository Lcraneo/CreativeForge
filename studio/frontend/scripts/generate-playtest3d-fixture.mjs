// 试玩舞台 3D POC-0 · GLB 测试夹具生成器
//
// 用途：生成一个「带真实 skin/骨骼 + 5 个 animation clips」的最小合法 GLB，
// 供前端 3D 舞台与后端 manifest 接口做离线验收（不依赖外网、不调用云厂商）。
//
// 运行（必须在 studio/frontend 下，解析裸 specifier "three"）：
//   node scripts/generate-playtest3d-fixture.mjs
//
// 输出：
//   studio/backend/tests/fixtures/playtest3d/character.glb
//   studio/backend/tests/fixtures/playtest3d/manifest.json

import { createHash } from "node:crypto";
/* global Buffer, console, process */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  Bone,
  BoxGeometry,
  BufferGeometry,
  Float32BufferAttribute,
  Quaternion,
  QuaternionKeyframeTrack,
  Scene,
  Skeleton,
  SkinnedMesh,
  Uint16BufferAttribute,
  Vector3,
  VectorKeyframeTrack,
  MeshStandardMaterial,
  AnimationClip,
} from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";

// Node 18 没有全局 FileReader，GLTFExporter 的二进制导出依赖它（readAsArrayBuffer）。
if (typeof globalThis.FileReader === "undefined") {
  globalThis.FileReader = class FileReaderPolyfill {
    constructor() {
      this.result = null;
      this.onloadend = null;
    }
    readAsArrayBuffer(blob) {
      blob.arrayBuffer().then((buf) => {
        this.result = buf;
        if (this.onloadend) this.onloadend();
      });
    }
    readAsDataURL(blob) {
      blob.arrayBuffer().then((buf) => {
        this.result =
          "data:application/octet-stream;base64," + buf.toString("base64");
        if (this.onloadend) this.onloadend();
      });
    }
  };
}

const FIXTURE_DIR = join(
  dirname(dirname(dirname(dirname(fileURLToPath(import.meta.url))))),
  "studio",
  "backend",
  "tests",
  "fixtures",
  "playtest3d",
);
mkdirSync(FIXTURE_DIR, { recursive: true });

// ── 骨骼层级（rest 姿态局部坐标）────────────────────────────────────────
// 索引顺序即 skinIndex 引用的骨骼编号，不能随意改动。
const BONE_DEFS = [
  { name: "hips", parent: null, pos: [0, 1.0, 0] },
  { name: "spine", parent: "hips", pos: [0, 0.25, 0] },
  { name: "chest", parent: "spine", pos: [0, 0.28, 0] },
  { name: "head", parent: "chest", pos: [0, 0.28, 0] },
  { name: "arm_upper_L", parent: "chest", pos: [0.3, 0.02, 0] },
  { name: "arm_lower_L", parent: "arm_upper_L", pos: [0, -0.26, 0] },
  { name: "arm_upper_R", parent: "chest", pos: [-0.3, 0.02, 0] },
  { name: "arm_lower_R", parent: "arm_upper_R", pos: [0, -0.26, 0] },
  { name: "leg_upper_L", parent: "hips", pos: [0.15, -0.5, 0] },
  { name: "leg_lower_L", parent: "leg_upper_L", pos: [0, -0.42, 0] },
  { name: "leg_upper_R", parent: "hips", pos: [-0.15, -0.5, 0] },
  { name: "leg_lower_R", parent: "leg_upper_R", pos: [0, -0.42, 0] },
];

const BONE_INDEX = new Map(BONE_DEFS.map((d, i) => [d.name, i]));

// ── 视觉分段（世界坐标 + 全权重绑定到单个骨骼）────────────────────────
const SKIN = { r: 0.86, g: 0.66, b: 0.52 };
const DARK = { r: 0.24, g: 0.26, b: 0.32 };
const BLUE = { r: 0.3, g: 0.5, b: 0.75 };
const SEGMENTS = [
  { bone: "hips", center: [0, 1.0, 0], size: [0.26, 0.24, 0.18], color: DARK },
  { bone: "spine", center: [0, 1.39, 0], size: [0.32, 0.42, 0.22], color: BLUE },
  { bone: "head", center: [0, 1.83, 0], size: [0.22, 0.26, 0.22], color: SKIN },
  { bone: "arm_upper_L", center: [0.3, 1.42, 0], size: [0.1, 0.26, 0.12], color: SKIN },
  { bone: "arm_lower_L", center: [0.3, 1.16, 0], size: [0.09, 0.26, 0.11], color: SKIN },
  { bone: "arm_upper_R", center: [-0.3, 1.42, 0], size: [0.1, 0.26, 0.12], color: SKIN },
  { bone: "arm_lower_R", center: [-0.3, 1.16, 0], size: [0.09, 0.26, 0.11], color: SKIN },
  { bone: "leg_upper_L", center: [0.15, 0.29, 0], size: [0.14, 0.42, 0.15], color: DARK },
  { bone: "leg_lower_L", center: [0.15, -0.13, 0], size: [0.11, 0.4, 0.13], color: DARK },
  { bone: "leg_upper_R", center: [-0.15, 0.29, 0], size: [0.14, 0.42, 0.15], color: DARK },
  { bone: "leg_lower_R", center: [-0.15, -0.13, 0], size: [0.11, 0.4, 0.13], color: DARK },
];

function buildSkeleton() {
  const bones = [];
  const byName = new Map();
  for (const def of BONE_DEFS) {
    const bone = new Bone();
    bone.name = def.name;
    bone.position.set(...def.pos);
    bones.push(bone);
    byName.set(def.name, bone);
  }
  let root = null;
  for (let i = 0; i < BONE_DEFS.length; i++) {
    const def = BONE_DEFS[i];
    if (def.parent) byName.get(def.parent).add(bones[i]);
    else root = bones[i];
  }
  return { bones, root };
}

function buildGeometry() {
  const positions = [];
  const normals = [];
  const uvs = [];
  const colors = [];
  const skinIndex = [];
  const skinWeight = [];
  const indices = [];
  let baseVertex = 0;
  for (const seg of SEGMENTS) {
    const g = new BoxGeometry(...seg.size);
    const pos = g.getAttribute("position");
    const nor = g.getAttribute("normal");
    const uv = g.getAttribute("uv");
    const boneIdx = BONE_INDEX.get(seg.bone);
    for (let i = 0; i < pos.count; i++) {
      positions.push(
        pos.getX(i) + seg.center[0],
        pos.getY(i) + seg.center[1],
        pos.getZ(i) + seg.center[2],
      );
      normals.push(nor.getX(i), nor.getY(i), nor.getZ(i));
      uvs.push(uv.getX(i), uv.getY(i));
      colors.push(seg.color.r, seg.color.g, seg.color.b);
      skinIndex.push(boneIdx, 0, 0, 0);
      skinWeight.push(1, 0, 0, 0);
    }
    for (const k of g.getIndex().array) indices.push(k + baseVertex);
    baseVertex += pos.count;
    g.dispose();
  }
  const geo = new BufferGeometry();
  geo.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geo.setAttribute("normal", new Float32BufferAttribute(normals, 3));
  geo.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
  geo.setAttribute("color", new Float32BufferAttribute(colors, 3));
  geo.setAttribute("skinIndex", new Uint16BufferAttribute(skinIndex, 4));
  geo.setAttribute("skinWeight", new Float32BufferAttribute(skinWeight, 4));
  geo.setIndex(indices);
  return geo;
}

// ── 动画轨道 ────────────────────────────────────────────────────────────
const X = new Vector3(1, 0, 0);

function swing(bone, times, angles) {
  const q = new Quaternion();
  const values = [];
  for (const a of angles) {
    q.setFromAxisAngle(X, a);
    values.push(q.x, q.y, q.z, q.w);
  }
  return new QuaternionKeyframeTrack(
    `character.bones[${bone}].quaternion`,
    times,
    values,
  );
}

function move(bone, times, points) {
  return new VectorKeyframeTrack(
    `character.bones[${bone}].position`,
    times,
    points.flat(),
  );
}

function buildClips() {
  const clips = [];

  // idle：轻微呼吸/摇摆（循环）
  clips.push(
    new AnimationClip("Idle", 1.2, [
      swing("arm_upper_L", [0, 0.5, 1.2], [0.06, -0.06, 0.06]),
      swing("arm_upper_R", [0, 0.5, 1.2], [-0.06, 0.06, -0.06]),
      swing("spine", [0, 0.5, 1.2], [0.03, -0.03, 0.03]),
      move("hips", [0, 0.6, 1.2], [[0, 1.0, 0], [0, 1.03, 0], [0, 1.0, 0]]),
    ]),
  );

  // walk：四肢交替摆动 + 身体起伏（循环）
  clips.push(
    new AnimationClip("Walk", 1.0, [
      swing("leg_upper_L", [0, 0.25, 0.5, 0.75, 1.0], [0.55, 0, -0.55, 0, 0.55]),
      swing("leg_upper_R", [0, 0.25, 0.5, 0.75, 1.0], [-0.55, 0, 0.55, 0, -0.55]),
      swing("leg_lower_L", [0, 0.5, 1.0], [-0.35, 0.2, -0.35]),
      swing("leg_lower_R", [0, 0.5, 1.0], [0.35, -0.2, 0.35]),
      swing("arm_upper_L", [0, 0.25, 0.5, 0.75, 1.0], [-0.55, 0, 0.55, 0, -0.55]),
      swing("arm_upper_R", [0, 0.25, 0.5, 0.75, 1.0], [0.55, 0, -0.55, 0, 0.55]),
      move("hips", [0, 0.5, 1.0], [[0, 1.0, 0], [0, 1.05, 0], [0, 1.0, 0]]),
    ]),
  );

  // run：更快更大摆幅 + 前倾（循环）
  clips.push(
    new AnimationClip("Run", 0.7, [
      swing("leg_upper_L", [0, 0.175, 0.35, 0.525, 0.7], [0.85, 0, -0.85, 0, 0.85]),
      swing("leg_upper_R", [0, 0.175, 0.35, 0.525, 0.7], [-0.85, 0, 0.85, 0, -0.85]),
      swing("leg_lower_L", [0, 0.35, 0.7], [-0.55, 0.35, -0.55]),
      swing("leg_lower_R", [0, 0.35, 0.7], [0.55, -0.35, 0.55]),
      swing("arm_upper_L", [0, 0.175, 0.35, 0.525, 0.7], [-0.7, 0, 0.7, 0, -0.7]),
      swing("arm_upper_R", [0, 0.175, 0.35, 0.525, 0.7], [0.7, 0, -0.7, 0, 0.7]),
      swing("spine", [0, 0.35, 0.7], [0.22, 0.18, 0.22]),
      move("hips", [0, 0.35, 0.7], [[0, 1.0, 0], [0, 1.08, 0], [0, 1.0, 0]]),
    ]),
  );

  // jump：起跳→滞空→落地（一次性）
  clips.push(
    new AnimationClip("Jump", 0.8, [
      move("hips", [0, 0.3, 0.5, 0.8], [[0, 1.0, 0], [0, 1.45, 0], [0, 1.6, 0], [0, 1.0, 0]]),
      swing("leg_upper_L", [0, 0.4, 0.8], [0, 0.5, 0]),
      swing("leg_upper_R", [0, 0.4, 0.8], [0, 0.5, 0]),
      swing("arm_upper_L", [0, 0.4, 0.8], [0, -0.9, 0]),
      swing("arm_upper_R", [0, 0.4, 0.8], [0, -0.9, 0]),
    ]),
  );

  // attack：右臂出拳（一次性）
  clips.push(
    new AnimationClip("Attack", 0.6, [
      swing("arm_upper_R", [0, 0.2, 0.6], [0, -1.1, 0]),
      swing("arm_lower_R", [0, 0.2, 0.6], [0, -0.4, 0]),
      swing("spine", [0, 0.2, 0.6], [0, 0.25, 0]),
      swing("arm_upper_L", [0, 0.2, 0.6], [0, 0.3, 0]),
    ]),
  );

  return clips;
}

function buildScene() {
  const { bones, root } = buildSkeleton();
  const geometry = buildGeometry();
  const material = new MeshStandardMaterial({ vertexColors: true, roughness: 0.85 });
  const mesh = new SkinnedMesh(geometry, material);
  mesh.name = "character";
  mesh.add(root);
  const scene = new Scene();
  scene.add(mesh);
  scene.updateMatrixWorld(true);
  mesh.bind(new Skeleton(bones));
  return { scene, bones };
}

// ── GLB 结构校验（不依赖 three 加载器，纯容器/JSON 检查）────────────────
function parseGlb(bytes) {
  if (bytes.readUint32LE(0) !== 0x46546c67) throw new Error("GLB magic 缺失");
  if (bytes.readUint32LE(4) !== 2) throw new Error("GLB 版本非 2");
  const jsonLen = bytes.readUint32LE(12);
  const json = JSON.parse(bytes.subarray(20, 20 + jsonLen).toString("utf8"));
  return json;
}

async function main() {
  const clipNames = [];
  const { scene, bones } = buildScene();
  const clips = buildClips();

  const exporter = new GLTFExporter();
  const glb = await new Promise((resolve, reject) => {
    exporter.parse(
      scene,
      (result) => resolve(Buffer.from(result)),
      (err) => reject(err),
      { binary: true, animations: clips },
    );
  });

  const glbPath = join(FIXTURE_DIR, "character.glb");
  writeFileSync(glbPath, glb);

  const json = parseGlb(glb);
  const animCount = (json.animations || []).length;
  const skinCount = (json.skins || []).length;
  const meshCount = (json.meshes || []).length;
  const jointCount = json.skins?.[0]?.joints?.length ?? 0;
  if (animCount < 5) throw new Error(`动画 clip 不足：${animCount}`);
  if (skinCount < 1) throw new Error("缺少 skin");
  if (meshCount < 1) throw new Error("缺少 mesh");
  if (jointCount < 1) throw new Error("skin 缺少 joints");
  clipNames.push(...((json.animations || []).map((a) => a.name) || []));

  const sha256 = createHash("sha256").update(glb).digest("hex");
  const manifest = {
    version: "1.0",
    asset_id: "playtest3d-fixture",
    available: true,
    error: null,
    mesh_url: "/api/playtest/3d/fixture.glb",
    bytes: glb.length,
    sha256,
    rig: { provider: "fixture", rigged: true },
    clips: [
      { name: "idle", source_clip: "Idle", loop: true },
      { name: "walk", source_clip: "Walk", loop: true },
      { name: "run", source_clip: "Run", loop: true },
      { name: "jump", source_clip: "Jump", loop: false },
      { name: "attack", source_clip: "Attack", loop: false },
    ],
    fallback_url: "/playtest",
  };
  writeFileSync(join(FIXTURE_DIR, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");

  console.log(
    JSON.stringify(
      {
        glb: glbPath,
        bytes: glb.length,
        sha256: sha256.slice(0, 16),
        bones: bones.length,
        clips: clipNames,
        skins: skinCount,
        joints: jointCount,
      },
      null,
      2,
    ),
  );
}

main().catch((err) => {
  console.error("生成失败：", err);
  process.exit(1);
});
