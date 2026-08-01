export const WORKFLOW_AGENTS = ["novel_parser", "role_analyzer", "dubbing_director"] as const;

export type WorkflowAgent = (typeof WORKFLOW_AGENTS)[number];
export type WorkflowMode = "automatic" | "step";
export type WorkflowStatus = "idle" | "running" | "awaiting_confirmation" | "completed";

export type WorkflowState = {
  mode: WorkflowMode;
  status: WorkflowStatus;
  activeAgent: WorkflowAgent | null;
  completedAgents: WorkflowAgent[];
};

export type WorkflowEvent =
  | { type: "SET_MODE"; mode: WorkflowMode }
  | { type: "START" }
  | { type: "AGENT_COMPLETED" }
  | { type: "PAUSE" }
  | { type: "CONTINUE" };

export function createWorkflowState(mode: WorkflowMode): WorkflowState {
  return {
    mode,
    status: "idle",
    activeAgent: null,
    completedAgents: [],
  };
}

export function transitionWorkflow(state: WorkflowState, event: WorkflowEvent): WorkflowState {
  if (event.type === "SET_MODE") {
    return {
      ...state,
      mode: event.mode,
      status:
        event.mode === "automatic" && state.status === "awaiting_confirmation"
          ? "running"
          : state.status,
    };
  }

  if (event.type === "START") {
    return {
      ...state,
      status: "running",
      activeAgent: WORKFLOW_AGENTS[0],
      completedAgents: [],
    };
  }

  if (event.type === "CONTINUE") {
    return state.status === "awaiting_confirmation" ? { ...state, status: "running" } : state;
  }

  if (event.type === "PAUSE") {
    return state.activeAgent === null ? state : { ...state, status: "awaiting_confirmation" };
  }

  if (state.status !== "running" || state.activeAgent === null) return state;

  const activeIndex = WORKFLOW_AGENTS.indexOf(state.activeAgent);
  const nextAgent = WORKFLOW_AGENTS[activeIndex + 1] ?? null;
  const completedAgents = state.completedAgents.includes(state.activeAgent)
    ? state.completedAgents
    : [...state.completedAgents, state.activeAgent];

  if (nextAgent === null) {
    return { ...state, status: "completed", activeAgent: null, completedAgents };
  }

  return {
    ...state,
    status: state.mode === "automatic" ? "running" : "awaiting_confirmation",
    activeAgent: nextAgent,
    completedAgents,
  };
}
