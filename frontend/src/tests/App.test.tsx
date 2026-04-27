import { render, screen } from "@testing-library/react";
import App from "../App";

vi.mock("../api/client", () => ({
  fetchHealth: vi.fn().mockResolvedValue({
    status: "ok",
    timestamp: new Date().toISOString(),
    connector_backend: "mock",
    llm_backend: "mock",
    llm_model: "mock",
    model_inference: "local",
    external_ai_calls: "none",
    components: [],
  }),
  fetchDemoUsers: vi.fn().mockResolvedValue({
    items: [
      {
        user_id: "demo_manager_meryem",
        display_name: "Meryem Ait Said",
        role: "manager",
        employee_id: "E1000",
        description: "Manager demo user",
      },
    ],
    active_user_id: "demo_manager_meryem",
  }),
  fetchLocalModels: vi.fn().mockResolvedValue({
    backend: "mock",
    active_model: "mock",
    items: [{ name: "mock", modified_at: null, size: null, family: null, parameter_size: null, quantization_level: null }],
  }),
  fetchRequests: vi.fn().mockResolvedValue({ items: [] }),
  fetchAudit: vi.fn().mockResolvedValue({ items: [] }),
  fetchRequest: vi.fn(),
  sendChat: vi.fn(),
  switchLocalModel: vi.fn(),
  switchDemoUser: vi.fn(),
}));

describe("App", () => {
  it("renders sample prompts and trust indicators", async () => {
    render(<App />);

    expect(await screen.findByText(/SuccessFactors HR Assistant MVP/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Model inference: local/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/External AI calls: none/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/How many absences did Sara Bennani have between 2026-01-01 and 2026-03-31/i)).toBeInTheDocument();
  });
});
