import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

/* ───── Build a geometry that contains horizontal lines only ───── */
function buildHorizontalGeometry(
  width = 2,
  height = 2,
  segW = 128,
  segH = 128
): THREE.BufferGeometry {
  const plane = new THREE.PlaneGeometry(width, height, segW, segH);
  const pos = plane.attributes.position as THREE.BufferAttribute;

  const cols = segW + 1;
  const rows = segH + 1;
  const indices: number[] = [];

  // horizontal lines (left-to-right for every row)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < segW; c++) {
      const a = r * cols + c;
      const b = a + 1;
      indices.push(a, b);
    }
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", pos.clone()); // clone so we can mutate Z
  geom.setIndex(indices);
  return geom;
}

/* ───── Animated ripple lines ───── */
const WaveLines = () => {
  const lineRef = useRef<THREE.LineSegments>(null!);
  const geometry = useMemo(() => buildHorizontalGeometry(4, 2, 128, 100), []);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;
    const pos = geometry.attributes.position as THREE.BufferAttribute;

    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const SPEED = 0.6; // 1.0 = original speed
      const AMPLITUDE = 0.025;
      const z =
        (Math.sin(x * 4.0 + t * SPEED) + Math.sin(y * 3.0 + t * 1.3 * SPEED)) *
        0.5 *
        AMPLITUDE;
      pos.setZ(i, z);
    }
    pos.needsUpdate = true;
  });

  return (
    <lineSegments
      ref={lineRef}
      geometry={geometry}
      rotation={[-Math.PI / 2, 0, 0]}
    >
      <lineBasicMaterial
        color="#9b5de5"
        transparent
        opacity={0.9}
        toneMapped={false}
      />
    </lineSegments>
  );
};

/* ───── Full-screen transparent canvas ───── */
export const WavesBackground = () => (
  <Canvas
    style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: -1 }}
    gl={{ alpha: true }}
    camera={{ position: [0, 0, 1.3], fov: 45 }}
  >
    <WaveLines />
  </Canvas>
);
