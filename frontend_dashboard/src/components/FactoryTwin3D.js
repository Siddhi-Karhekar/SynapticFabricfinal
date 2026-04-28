import React, { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Text } from "@react-three/drei";
import { MACHINE_INFO, CHAIN_ORDER } from "../utils/machineInfo";

function getMachineColor(machine) {

  if (!machine) return "#888";

  if (machine.health_status === "Critical") return "#ff3b3b";
  if (machine.health_status === "Warning") return "#ffa500";
  if (machine.health_status === "Healthy") return "#00ff88";

  return "#888";
}

function ConveyorBox({ start }) {

  const ref = useRef();

  useFrame(() => {

    ref.current.position.x += 0.05;

    if (ref.current.position.x > 14)
      ref.current.position.x = -14;

  });

  return (
    <mesh ref={ref} position={[start, 0.5, 0]}>
      <boxGeometry args={[0.6, 0.6, 0.6]}/>
      <meshStandardMaterial color="#cccccc"/>
    </mesh>
  );
}

function Machine({ machine, position, label }) {

  const color = getMachineColor(machine);

  return (
    <group position={position}>
      <mesh>
        <boxGeometry args={[2, 2, 2]}/>
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.5}
        />
      </mesh>

      {/* MACHINE NAME LABEL */}
      <Text
        position={[0, 1.7, 0]}
        fontSize={0.45}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.03}
        outlineColor="#000"
      >
        {label}
      </Text>

      {/* STAGE / ID */}
      <Text
        position={[0, -1.6, 0]}
        fontSize={0.32}
        color="#9ad1ff"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.02}
        outlineColor="#000"
      >
        {machine?.machine_id || ""}
      </Text>
    </group>
  );
}

export default function FactoryTwin3D({ machines }) {

  // Render in canonical chain order so the visual matches
  // the manufacturing flow even if the API returns differently.
  const ordered = CHAIN_ORDER
    .map((id) => machines?.[id])
    .filter(Boolean);

  return (
    <div style={{ height: "320px", width: "100%" }}>
      <Canvas camera={{ position: [0, 9, 18], fov: 60 }}>

        <ambientLight intensity={0.6}/>
        <directionalLight position={[10, 10, 5]}/>

        {/* floor */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1, 0]}>
          <planeGeometry args={[44, 22]}/>
          <meshStandardMaterial color="#222"/>
        </mesh>

        {/* conveyor belt */}
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[34, 0.5, 2]}/>
          <meshStandardMaterial color="#111"/>
        </mesh>

        <ConveyorBox start={-12}/>
        <ConveyorBox start={-4}/>
        <ConveyorBox start={4}/>
        <ConveyorBox start={12}/>

        {/* machines */}
        {ordered.map((machine, i) => {

          const spacing = 8;
          const start = -(ordered.length - 1) * spacing / 2;
          const info = MACHINE_INFO[machine.machine_id] || {};
          const label = info.name || machine.machine_id;

          return (
            <Machine
              key={machine.machine_id}
              machine={machine}
              position={[start + i * spacing, 1, 0]}
              label={label}
            />
          );
        })}

        <OrbitControls/>
      </Canvas>
    </div>
  );
}
