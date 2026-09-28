import * as THREE from "three";

/**
 * 三渲二卡通着色模块（参考 Windup 出帧台的着色思路重写，不拷贝代码）。
 *
 * 提炼自参考项目的三条核心经验：
 *  1. 硬边色阶（ramp 量化）——卡通着色的本体：明暗被量化为离散色阶，
 *     不做平滑过渡（参考项目用 NearestFilter 的 gradientMap，这里直接在
 *     shader 里 floor 量化，少一次纹理采样，实时渲染更便宜）。
 *  2. 描边走"法线外扩 + 背面壳"（inverted hull）——单 pass、无后处理，
 *     不需要深度图/法线缓冲，帧率代价接近一次普通绘制。
 *  3. 材质重建必须继承源材质的 side / map / color——参考项目踩过的坑：
 *     丢掉 doubleSided 会在减面网格上表现为满身单像素白斑。
 *
 * 可调参数（对应需求：描边宽度/颜色、明暗色阶数量、阴影阈值、高光范围、
 * 边缘光强度）全部走 uniform，改参数不重建材质、不重编译 shader。
 */

export interface ToonParameters {
  /** 描边宽度（模型空间，法线外扩距离） */
  outlineWidth: number;
  /** 描边颜色 */
  outlineColor: string;
  /** 明暗色阶数量（2–8） */
  colorSteps: number;
  /** 阴影阈值：光照低于该值的区域整体压到最暗阶 */
  shadowThreshold: number;
  /** 高光范围（0–1）：越大高光覆盖越大 */
  specularRange: number;
  /** 边缘光强度（0–2） */
  rimIntensity: number;
}

export const DEFAULT_TOON_PARAMETERS: ToonParameters = {
  outlineWidth: 0.025,
  outlineColor: "#26262e",
  colorSteps: 3,
  shadowThreshold: 0.42,
  specularRange: 0.3,
  rimIntensity: 0.55,
};

export const TOON_PARAMETER_LIMITS = {
  outlineWidth: { min: 0, max: 0.08, step: 0.001 },
  colorSteps: { min: 2, max: 8, step: 1 },
  shadowThreshold: { min: 0, max: 1, step: 0.01 },
  specularRange: { min: 0, max: 0.8, step: 0.01 },
  rimIntensity: { min: 0, max: 2, step: 0.05 },
} as const;

/** 主光方向（世界空间，对齐 AssetViewer 的平行光位姿） */
const LIGHT_DIR = new THREE.Vector3(4, 6, 3).normalize();

const TOON_VERTEX = /* glsl */ `
  varying vec3 vWorldNormal;
  varying vec3 vViewPosition;
  varying vec2 vUv;

  void main() {
    vUv = uv;
    vec4 worldPos = modelMatrix * vec4(position, 1.0);
    vWorldNormal = normalize(mat3(modelMatrix) * normal);
    vec4 mvPosition = viewMatrix * worldPos;
    vViewPosition = mvPosition.xyz;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const TOON_FRAGMENT = /* glsl */ `
  uniform vec3 uColor;
  uniform vec3 uEmissive;
  uniform sampler2D uMap;
  uniform float uUseMap;
  uniform float uUseEmissive;
  uniform vec3 uLightDir;
  uniform float uColorSteps;
  uniform float uShadowThreshold;
  uniform float uSpecularRange;
  uniform float uRimIntensity;

  varying vec3 vWorldNormal;
  varying vec3 vViewPosition;
  varying vec2 vUv;

  void main() {
    vec3 N = normalize(vWorldNormal);
    vec3 V = normalize(cameraPosition - vViewPosition);
    vec3 L = normalize(uLightDir);

    vec3 base = uColor;
    if (uUseMap > 0.5) {
      base *= texture2D(uMap, vUv).rgb;
    }

    // ── 离散色阶：floor 量化，硬边无过渡 ──
    float ndl = dot(N, L) * 0.5 + 0.5;
    float steps = max(uColorSteps, 2.0);
    float band = floor(ndl * steps) / (steps - 1.0);

    // ── 阴影阈值：阈值以下强制压到最暗阶（硬边卡通阴影） ──
    float shadowed = 1.0 - step(uShadowThreshold, ndl);
    band = mix(band, 0.0, shadowed);

    vec3 color = base * (0.28 + 0.72 * band);

    // ── 带状高光：范围越大覆盖越广；仅出现在受光区 ──
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 48.0);
    float specOn = step(1.0 - uSpecularRange, spec) * (1.0 - shadowed);
    color += vec3(0.95) * specOn;

    // ── 边缘光：视线掠射角发亮 ──
    float rim = pow(1.0 - max(dot(N, V), 0.0), 3.0);
    color += vec3(1.0) * rim * uRimIntensity;

    color += uEmissive * uUseEmissive;

    gl_FragColor = vec4(color, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

const OUTLINE_VERTEX = /* glsl */ `
  uniform float uOutlineWidth;

  void main() {
    // 法线外扩（inverted hull）：沿法线把顶点顶出去，配合 BackSide 只露壳
    vec3 pos = position + normal * uOutlineWidth;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const OUTLINE_FRAGMENT = /* glsl */ `
  uniform vec3 uOutlineColor;

  void main() {
    gl_FragColor = vec4(uOutlineColor, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

interface SourceMaterialInfo {
  color: THREE.Color;
  emissive: THREE.Color;
  emissiveIntensity: number;
  map: THREE.Texture | null;
  side: THREE.Side;
}

function readSource(material: THREE.Material | null): SourceMaterialInfo {
  const info: SourceMaterialInfo = {
    color: new THREE.Color(0xcccccc),
    emissive: new THREE.Color(0x000000),
    emissiveIntensity: 0,
    map: null,
    side: THREE.FrontSide,
  };
  const std = material as THREE.MeshStandardMaterial | null;
  if (material && "color" in material && (material as THREE.MeshBasicMaterial).color) {
    info.color.copy((material as THREE.MeshBasicMaterial).color);
  }
  if (std && "emissive" in std && std.emissive) {
    info.emissive.copy(std.emissive);
    info.emissiveIntensity = Number(std.emissiveIntensity ?? 0);
  }
  if (std && "map" in std && std.map) {
    info.map = std.map;
  }
  if (material && "side" in material) {
    info.side = (material as { side: THREE.Side }).side;
  }
  return info;
}

export interface ToonHandle {
  /** 更新可调参数（只改 uniform，不重建材质） */
  update(params: ToonParameters): void;
  /** 还原原始材质并移除描边壳 */
  dispose(): void;
}

const OUTLINE_TAG = "__cfToonOutline";

/**
 * 给 root 下所有静态 Mesh 套上卡通着色 + 描边壳。
 *
 * 限制：跳过 SkinnedMesh（蒙皮需要 skinning 顶点块，当前查看器只有静态
 * 体素模型；接 GLB 蒙皮模型时再扩展）。
 */
export function applyToonShading(root: THREE.Object3D, params: ToonParameters): ToonHandle {
  const toonMaterials: THREE.ShaderMaterial[] = [];
  const originals: Array<{ mesh: THREE.Mesh; material: THREE.Material | THREE.Material[] }> = [];
  const outlines: THREE.Mesh[] = [];

  // 描边材质全局共享一份：uniform 更新一次即可作用于所有壳
  const outlineMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uOutlineWidth: { value: params.outlineWidth },
      uOutlineColor: { value: new THREE.Color(params.outlineColor) },
    },
    vertexShader: OUTLINE_VERTEX,
    fragmentShader: OUTLINE_FRAGMENT,
    side: THREE.BackSide,
  });

  root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (!mesh.isMesh || (mesh as THREE.SkinnedMesh).isSkinnedMesh) return;
    if (mesh.userData[OUTLINE_TAG]) return;

    originals.push({ mesh, material: mesh.material });
    const sources = Array.isArray(mesh.material)
      ? mesh.material.map((m) => readSource(m))
      : [readSource(mesh.material)];
    const primary = sources[0];

    const toonMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uColor: { value: primary.color.clone() },
        uEmissive: { value: primary.emissive.clone() },
        uMap: { value: primary.map },
        uUseMap: { value: primary.map ? 1 : 0 },
        uUseEmissive: { value: primary.emissiveIntensity },
        uLightDir: { value: LIGHT_DIR.clone() },
        uColorSteps: { value: params.colorSteps },
        uShadowThreshold: { value: params.shadowThreshold },
        uSpecularRange: { value: params.specularRange },
        uRimIntensity: { value: params.rimIntensity },
      },
      vertexShader: TOON_VERTEX,
      fragmentShader: TOON_FRAGMENT,
      side: primary.side,
    });
    toonMaterials.push(toonMaterial);
    mesh.material = toonMaterial;

    // 描边壳：同几何体的子 Mesh，跟随父级变换
    const outline = new THREE.Mesh(mesh.geometry, outlineMaterial);
    outline.userData[OUTLINE_TAG] = true;
    outline.raycast = () => {}; // 壳不参与拾取，避免 hover 判定翻倍
    mesh.add(outline);
    outlines.push(outline);
  });

  return {
    update(next: ToonParameters) {
      for (const material of toonMaterials) {
        material.uniforms.uColorSteps.value = next.colorSteps;
        material.uniforms.uShadowThreshold.value = next.shadowThreshold;
        material.uniforms.uSpecularRange.value = next.specularRange;
        material.uniforms.uRimIntensity.value = next.rimIntensity;
      }
      outlineMaterial.uniforms.uOutlineWidth.value = next.outlineWidth;
      (outlineMaterial.uniforms.uOutlineColor.value as THREE.Color).set(next.outlineColor);
      for (const outline of outlines) {
        outline.visible = next.outlineWidth > 0;
      }
    },
    dispose() {
      for (const { mesh, material } of originals) {
        mesh.material = material;
      }
      for (const outline of outlines) {
        outline.removeFromParent();
      }
      for (const material of toonMaterials) material.dispose();
      outlineMaterial.dispose();
    },
  };
}
