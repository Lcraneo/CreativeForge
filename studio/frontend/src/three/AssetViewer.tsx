import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  DoubleSide,
  NearestFilter,
  SRGBColorSpace,
  TextureLoader,
  type Group,
  type Mesh,
  type Texture,
} from "three";

import {
  DEFAULT_TOON_PARAMETERS,
  applyToonShading,
  type ToonHandle,
  type ToonParameters,
} from "./toon/ToonMaterial";
import ToonSettingsPanel from "./toon/ToonSettingsPanel";

/**
 * 3D asset viewer (R3F): the produced character as a voxel-style stand-in
 * that rotates, with the asset card floating beside the canvas.
 *
 * 三渲二卡通渲染：ToonGroup 把角色网格替换为卡通着色材质并叠加法线外扩
 * 描边壳；参数面板实时改 uniform。地板与灯光保持标准材质（卡通化只作用于
 * 角色本体），切换开关可对照原始 PBR 视图。
 */

const TOON_STORAGE_KEY = "creativeforge.toon-settings";

function loadStoredParams(): ToonParameters {
  try {
    const raw = localStorage.getItem(TOON_STORAGE_KEY);
    if (raw) return { ...DEFAULT_TOON_PARAMETERS, ...JSON.parse(raw) };
  } catch {
    // 损坏的本地存储直接回落默认值
  }
  return { ...DEFAULT_TOON_PARAMETERS };
}

/** 把卡通着色（含描边壳）套到 children 上，参数变化只更新 uniform */
function ToonGroup({
  params,
  enabled,
  children,
}: {
  params: ToonParameters;
  enabled: boolean;
  children: ReactNode;
}) {
  const root = useRef<Group>(null);
  const handle = useRef<ToonHandle | null>(null);

  useEffect(() => {
    return () => {
      handle.current?.dispose();
      handle.current = null;
    };
  }, []);

  useEffect(() => {
    if (!root.current) return;
    if (enabled && !handle.current) {
      handle.current = applyToonShading(root.current, params);
    } else if (!enabled && handle.current) {
      handle.current.dispose();
      handle.current = null;
    }
  }, [enabled]); // eslint-disable-line react-hooks/exhaustive-deps -- 仅开关时挂/卸

  useEffect(() => {
    handle.current?.update(params);
  }, [params]);

  return <group ref={root}>{children}</group>;
}

/** 帧率探针：0.5s 聚合一次，验证参数调节不影响实时帧率 */
function FpsProbe({ onFps }: { onFps: (fps: number) => void }) {
  const frames = useRef(0);
  const elapsed = useRef(0);
  useFrame((_, delta) => {
    frames.current += 1;
    elapsed.current += delta;
    if (elapsed.current >= 0.5) {
      onFps(Math.round(frames.current / elapsed.current));
      frames.current = 0;
      elapsed.current = 0;
    }
  });
  return null;
}

function VoxelCharacter({ accent }: { accent: string }) {
  const group = useRef<Group>(null);
  const [hovered, setHovered] = useState(false);

  useFrame((_, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * (hovered ? 1.4 : 0.5);
    }
  });

  return (
    <group
      ref={group}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      {/* head */}
      <mesh position={[0, 1.15, 0]}>
        <boxGeometry args={[0.8, 0.7, 0.8]} />
        <meshStandardMaterial color="#f4d58d" />
      </mesh>
      {/* hat */}
      <mesh position={[0, 1.72, 0]}>
        <coneGeometry args={[0.62, 0.9, 4]} />
        <meshStandardMaterial color={accent} />
      </mesh>
      {/* body */}
      <mesh position={[0, 0.35, 0]}>
        <boxGeometry args={[1, 1.1, 0.7]} />
        <meshStandardMaterial color={accent} />
      </mesh>
      {/* legs */}
      <mesh position={[-0.28, -0.5, 0]}>
        <boxGeometry args={[0.36, 0.7, 0.5]} />
        <meshStandardMaterial color="#3f3f46" />
      </mesh>
      <mesh position={[0.28, -0.5, 0]}>
        <boxGeometry args={[0.36, 0.7, 0.5]} />
        <meshStandardMaterial color="#3f3f46" />
      </mesh>
      {/* staff */}
      <mesh position={[0.85, 0.45, 0]} rotation={[0, 0, -0.08]}>
        <cylinderGeometry args={[0.06, 0.06, 2.2, 6]} />
        <meshStandardMaterial color="#a16207" />
      </mesh>
      <mesh position={[0.96, 1.62, 0]}>
        <icosahedronGeometry args={[0.22, 0]} />
        <meshStandardMaterial color="#fb923c" emissive="#fb923c" emissiveIntensity={0.8} />
      </mesh>
    </group>
  );
}

function Grid() {
  const ref = useRef<Mesh>(null);
  useFrame((state) => {
    if (ref.current) {
      ref.current.position.y = -1.25 + Math.sin(state.clock.elapsedTime * 1.2) * 0.04;
    }
  });
  return (
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[6, 6]} />
      <meshStandardMaterial color="#e3dfd6" />
    </mesh>
  );
}

/** 真实像素重建贴图牌：把当前资产的像素图作为纹理立在 3D 舞台上，
 * NearestFilter 保持像素锐利；加载失败由父级回落体素替身。 */
function TexturedBillboard({
  url,
  onFail,
}: {
  url: string;
  onFail: () => void;
}) {
  const group = useRef<Group>(null);
  const [texture, setTexture] = useState<Texture | null>(null);

  useFrame((_, delta) => {
    if (group.current) {
      group.current.rotation.y += delta * 0.5;
    }
  });

  useEffect(() => {
    let cancelled = false;
    setTexture(null);
    const loader = new TextureLoader();
    loader.load(
      url,
      (loaded) => {
        if (cancelled) return;
        loaded.magFilter = NearestFilter;
        loaded.colorSpace = SRGBColorSpace;
        setTexture(loaded);
      },
      undefined,
      onFail,
    );
    return () => {
      cancelled = true;
    };
  }, [url, onFail]);

  if (!texture) return null;
  const image = texture.image as { width?: number; height?: number };
  const height = 2.6;
  const aspect =
    image.width && image.height ? image.width / image.height : 1;
  return (
    <group ref={group}>
      <mesh>
        <planeGeometry args={[height * aspect, height]} />
        <meshStandardMaterial
          map={texture}
          transparent
          alphaTest={0.05}
          side={DoubleSide}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

/** 有真实贴图用贴图牌，加载失败或未提供时回落体素替身。 */
function AssetModel({ textureUrl, accent }: { textureUrl?: string; accent: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [textureUrl]);
  if (!textureUrl || failed) return <VoxelCharacter accent={accent} />;
  return <TexturedBillboard url={textureUrl} onFail={() => setFailed(true)} />;
}

export default function AssetViewer({
  accent = "#93a9c4",
  textureUrl,
}: {
  accent?: string;
  /** 当前资产像素重建图 URL：提供后用真实角色贴图替代体素替身 */
  textureUrl?: string;
}) {
  const [params, setParams] = useState<ToonParameters>(loadStoredParams);
  const [toonEnabled, setToonEnabled] = useState(true);
  const [fps, setFps] = useState(60);

  useEffect(() => {
    try {
      localStorage.setItem(TOON_STORAGE_KEY, JSON.stringify(params));
    } catch {
      // 存储不可用时静默忽略
    }
  }, [params]);

  return (
    <div className="relative h-full w-full">
      <Canvas camera={{ position: [3.2, 2.2, 4.2], fov: 45 }} style={{ background: "#f3f6fa" }}>
        <FpsProbe onFps={setFps} />
        <ambientLight intensity={0.65} />
        <directionalLight position={[4, 6, 3]} intensity={1.15} />
        <pointLight position={[-3, 2, -2]} intensity={0.55} color="#93a9c4" />
        <ToonGroup params={params} enabled={toonEnabled && !textureUrl}>
          <AssetModel textureUrl={textureUrl} accent={accent} />
        </ToonGroup>
        <Grid />
        <OrbitControls enablePan={false} minDistance={3} maxDistance={9} />
      </Canvas>

      <div className="pointer-events-none absolute inset-0">
        <ToonSettingsPanel
          params={params}
          fps={fps}
          enabled={toonEnabled}
          onToggle={setToonEnabled}
          onChange={setParams}
        />
      </div>
    </div>
  );
}
