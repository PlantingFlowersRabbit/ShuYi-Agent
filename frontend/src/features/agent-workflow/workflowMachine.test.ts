import { describe, expect, it } from "vitest";

describe("v0.4 agent workflow modes", () => {
  it("uses the exact three product agents", async () => {
    const { WORKFLOW_AGENTS } = await import("./workflowMachine");
    expect(WORKFLOW_AGENTS).toEqual(["novel_parser", "role_analyzer", "dubbing_director"]);
  });

  it("changes the mode through workflow state", async () => {
    const { createWorkflowState, transitionWorkflow } = await import("./workflowMachine");
    const automatic = createWorkflowState("automatic");
    const step = transitionWorkflow(automatic, { type: "SET_MODE", mode: "step" });

    expect(step).toEqual({ ...automatic, mode: "step" });
  });

  it("automatic mode advances directly to the next agent", async () => {
    const { createWorkflowState, transitionWorkflow } = await import("./workflowMachine");
    const idle = createWorkflowState("automatic");
    const parsing = transitionWorkflow(idle, { type: "START" });
    const analyzing = transitionWorkflow(parsing, { type: "AGENT_COMPLETED" });

    expect(parsing).toMatchObject({
      mode: "automatic",
      status: "running",
      activeAgent: "novel_parser",
    });
    expect(analyzing).toMatchObject({
      status: "running",
      activeAgent: "role_analyzer",
      completedAgents: ["novel_parser"],
    });
  });

  it("step mode pauses between agents until the user continues", async () => {
    const { createWorkflowState, transitionWorkflow } = await import("./workflowMachine");
    const idle = createWorkflowState("step");
    const parsing = transitionWorkflow(idle, { type: "START" });
    const paused = transitionWorkflow(parsing, { type: "AGENT_COMPLETED" });
    const continued = transitionWorkflow(paused, { type: "CONTINUE" });

    expect(paused).toMatchObject({
      mode: "step",
      status: "awaiting_confirmation",
      activeAgent: "role_analyzer",
      completedAgents: ["novel_parser"],
    });
    expect(continued).toMatchObject({
      status: "running",
      activeAgent: "role_analyzer",
    });
  });

  it("continues a paused workflow when switched to automatic mode", async () => {
    const { createWorkflowState, transitionWorkflow } = await import("./workflowMachine");
    const parsing = transitionWorkflow(createWorkflowState("step"), { type: "START" });
    const paused = transitionWorkflow(parsing, { type: "AGENT_COMPLETED" });

    expect(transitionWorkflow(paused, { type: "SET_MODE", mode: "automatic" })).toMatchObject({
      mode: "automatic",
      status: "running",
      activeAgent: "role_analyzer",
    });
  });
});
