import { describe, expect, it } from "vitest";

describe("v0.4 agent workflow modes", () => {
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
});
