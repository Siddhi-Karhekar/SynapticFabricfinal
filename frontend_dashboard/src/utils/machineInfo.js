// Synaptic Fabric - Nexus Edition
// 4-node manufacturing chain
export const MACHINE_INFO = {
  M_1: {
    name: "Induction Motor",
    process: "Primary Drive (Stage 1)",
    stage: 1
  },
  M_2: {
    name: "Industrial Gearbox",
    process: "Torque Transmission (Stage 2)",
    stage: 2
  },
  M_3: {
    name: "CNC Milling Tool",
    process: "Machining Operation (Stage 3)",
    stage: 3
  },
  M_4: {
    name: "Robotic Sorting Arm",
    process: "Pick & Place / Sort (Stage 4)",
    stage: 4
  }
};

export const CHAIN_ORDER = ["M_1", "M_2", "M_3", "M_4"];
