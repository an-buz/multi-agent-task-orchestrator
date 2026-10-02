import { create } from "zustand";

interface WorkflowEditorState {
  selectedNodeId: string | null;
  setSelectedNodeId: (nodeId: string | null) => void;
}

export const useWorkflowEditorStore = create<WorkflowEditorState>((set) => ({
  selectedNodeId: null,
  setSelectedNodeId: (selectedNodeId) => set({ selectedNodeId }),
}));
