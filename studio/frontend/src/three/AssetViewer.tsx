import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { useRef, useState } from "react";
import type { Mesh, Group } from "three";

/**
 * 3D asset viewer (R3F): the produced character as a voxel-style stand-in
 * that rotates, with the asset card floating beside the canvas.
 */
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
      <meshStandardMaterial color="#141922" />
    </mesh>
  );
}

export default function AssetViewer({ accent = "#4cc2ff" }: { accent?: string }) {
  return (
    <Canvas
      camera={{ position: [3.2, 2.2, 4.2], fov: 45 }}
      style={{ background: "#0a0e15" }}
    >
      <ambientLight intensity={0.5} />
      <directionalLight position={[4, 6, 3]} intensity={1.1} />
      <pointLight position={[-3, 2, -2]} intensity={0.5} color="#4cc2ff" />
      <VoxelCharacter accent={accent} />
      <Grid />
      <OrbitControls enablePan={false} minDistance={3} maxDistance={9} />
    </Canvas>
  );
}
