import { Canvas, useFrame } from "@react-three/fiber";
import { Grid, OrbitControls } from "@react-three/drei";
import { useEffect, useRef, useState } from "react";
import {
  AnimationMixer,
  Box3,
  LoopOnce,
  LoopRepeat,
  Vector3,
  type AnimationAction,
  type Object3D,
  type SkinnedMesh,
} from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import {
  isLoopAction,
  resolveClips,
  type Playtest3DLoadError,
  type ResolvedClips,
  type StandardAction,
} from "../lib/playtest3d";
import type { Playtest3DClip } from "../types";

/** 动作切换的短交叉淡化时长（秒）：避免明显 T-pose 闪帧。 */
const CROSSFADE = 0.25;

export interface Playtest3DCanvasProps {
  meshUrl: string;
  manifestClips: Playtest3DClip[];
  activeAction: StandardAction;
  onReady?: (info: { clipNames: string[]; resolved: ResolvedClips }) => void;
  onError?: (error: Playtest3DLoadError) => void;
  onActionSettled?: (settledAction: StandardAction) => void;
}

/** 加载完成后把角色摆正：中心对齐 X/Z、脚底贴地，过大时等比收缩。 */
function autoCenter(root: Object3D): void {
  const box = new Box3().setFromObject(root);
  if (box.isEmpty()) return;
  const size = box.getSize(new Vector3());
  const center = box.getCenter(new Vector3());
  root.position.x -= center.x;
  root.position.z -= center.z;
  root.position.y -= box.min.y;
  const maxDim = Math.max(size.x, size.y, size.z);
  if (maxDim > 3) root.scale.setScalar(3 / maxDim);
  root.updateMatrixWorld(true);
}

/** 在 R3F Canvas 内加载真实 GLB 并用 AnimationMixer 播放自带动画。 */
function AnimatedModel({
  meshUrl,
  manifestClips,
  activeAction,
  onReady,
  onError,
  onActionSettled,
}: Playtest3DCanvasProps) {
  const [scene, setScene] = useState<Object3D | null>(null);
  const [ready, setReady] = useState(false);
  const mixerRef = useRef<AnimationMixer | null>(null);
  const actionsRef = useRef<Record<string, AnimationAction>>({});
  const resolvedRef = useRef<ResolvedClips>({} as ResolvedClips);
  const currentClipRef = useRef<AnimationAction | null>(null);
  const currentActionRef = useRef<StandardAction>("idle");
  const startedRef = useRef(false);
  const manifestClipsRef = useRef(manifestClips);

  const onReadyRef = useRef(onReady);
  const onErrorRef = useRef(onError);
  const onActionSettledRef = useRef(onActionSettled);
  useEffect(() => {
    manifestClipsRef.current = manifestClips;
    onReadyRef.current = onReady;
    onErrorRef.current = onError;
    onActionSettledRef.current = onActionSettled;
  });

  /** 播放一个标准动作：循环动作 LoopRepeat，一次性动作播放完回 idle。 */
  const playStandardAction = (action: StandardAction) => {
    const mixer = mixerRef.current;
    if (!mixer) return;
    const source = resolvedRef.current[action];
    const target = source ? actionsRef.current[source] : undefined;
    if (!target) return; // 动作缺失：保持当前片段，不借用其他动作
    const previous = currentClipRef.current;
    if (previous && previous !== target) previous.fadeOut(CROSSFADE);
    target.reset().fadeIn(CROSSFADE);
    if (isLoopAction(action)) {
      target.loop = LoopRepeat;
      target.clampWhenFinished = false;
    } else {
      target.loop = LoopOnce;
      target.clampWhenFinished = true;
    }
    target.play();
    currentClipRef.current = target;
    currentActionRef.current = action;
  };

  // 加载 + 校验 + 建 mixer
  useEffect(() => {
    let cancelled = false;
    const loader = new GLTFLoader();
    loader.load(
      meshUrl,
      (gltf) => {
        if (cancelled) return;
        let hasSkeleton = false;
        gltf.scene.traverse((obj) => {
          if ((obj as SkinnedMesh).isSkinnedMesh) hasSkeleton = true;
        });
        if (!hasSkeleton) {
          onErrorRef.current?.("no_skeleton");
          return;
        }
        const clipNames = gltf.animations.map((clip) => clip.name);
        if (clipNames.length === 0) {
          onErrorRef.current?.("no_animations");
          return;
        }

        autoCenter(gltf.scene);
        const mixer = new AnimationMixer(gltf.scene);
        mixerRef.current = mixer;
        const actions: Record<string, AnimationAction> = {};
        for (const clip of gltf.animations) actions[clip.name] = mixer.clipAction(clip);
        actionsRef.current = actions;

        // 用 manifest 声明的动作契约把 GLB clip 映射到 5 个标准动作
        const resolved = resolveClips(clipNames, manifestClipsRef.current);
        resolvedRef.current = resolved;

        setScene(gltf.scene);
        setReady(true);
        onReadyRef.current?.({ clipNames, resolved });
      },
      undefined,
      (error) => {
        if (cancelled) return;
        // GLTFLoader：下载失败走 FileLoader 的 ErrorEvent；损坏的 GLB 在
        // parse 阶段抛 Error 后经同一回调吐出——据此区分两类失败。
        onErrorRef.current?.(error instanceof Error ? "parse_failed" : "download_failed");
      },
    );
    return () => {
      cancelled = true;
      mixerRef.current?.stopAllAction();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅 meshUrl 变更时重载
  }, [meshUrl]);

  // 动作切换（含首次加载完成后的 idle 起播）；已播且动作未变时跳过，
  // 避免一次性动作结束回到 idle 后重复 reset 造成的轻微重播。
  useEffect(() => {
    if (!ready) return;
    if (activeAction === currentActionRef.current && startedRef.current) return;
    playStandardAction(activeAction);
    startedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeAction, ready]);

  // 一次性动作播放完 → 回 idle 并通知页面复位高亮
  useEffect(() => {
    const mixer = mixerRef.current;
    if (!mixer) return;
    const onFinished = (event: { action: AnimationAction; direction: number }) => {
      if (event.action !== currentClipRef.current) return;
      if (event.direction === 1 && !isLoopAction(currentActionRef.current)) {
        playStandardAction("idle");
        onActionSettledRef.current?.("idle");
      }
    };
    mixer.addEventListener("finished", onFinished);
    return () => mixer.removeEventListener("finished", onFinished);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mixer 在 load 后绑定
  }, [scene]);

  useFrame((_, delta) => {
    mixerRef.current?.update(delta);
  });

  return scene ? <primitive object={scene} /> : null;
}

export default function Playtest3DCanvas(props: Playtest3DCanvasProps) {
  return (
    <Canvas
      camera={{ position: [3.2, 2.2, 4.4], fov: 45 }}
      style={{ background: "#eef1f6" }}
    >
      <color attach="background" args={["#eef1f6"]} />
      <ambientLight intensity={0.75} />
      <directionalLight position={[4, 6, 3]} intensity={1.2} />
      <pointLight position={[-3, 2, -2]} intensity={0.5} />
      <AnimatedModel {...props} />
      <Grid
        position={[0, -0.01, 0]}
        sectionColor="#d6dbe4"
        cellColor="#e8ebf0"
        infiniteGrid
        fadeDistance={40}
      />
      <OrbitControls enablePan={false} minDistance={1.8} maxDistance={12} target={[0, 0.8, 0]} />
    </Canvas>
  );
}