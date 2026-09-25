import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { GenerationNotice } from "./page";


afterEach(cleanup);

describe("GenerationNotice", () => {
  test("shows a non-blocking grounded fallback notice", () => {
    render(<GenerationNotice generation={{
      provider_attempted: ["gemini-3.8-flash", "gemini-3.7-flash"],
      provider_selected: "deterministic-grounded",
      provider_label: "RepoMind grounded fallback",
      mode: "deterministic",
      fallback_occurred: true,
      failures: [
        { provider: "gemini-3.8-flash", category: "temporarily_unavailable", transient: true },
        { provider: "gemini-3.7-flash", category: "timeout", transient: true },
      ],
      latency_ms: 12,
      notice: "Gemini 3.8 Flash and Gemini 3.7 Flash are temporarily unavailable. This response uses RepoMind's grounded fallback mode.",
    }} />);

    const notice = screen.getByRole("status");
    expect(notice).toHaveAttribute("data-generation-mode", "deterministic");
    expect(notice).toHaveTextContent("GROUNDED FALLBACK");
    expect(notice).toHaveTextContent("RepoMind's grounded fallback mode");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("labels an insufficient-evidence response", () => {
    render(<GenerationNotice generation={{
      provider_attempted: [],
      provider_selected: null,
      provider_label: "Evidence gate",
      mode: "insufficient_evidence",
      fallback_occurred: false,
      failures: [],
      latency_ms: 0,
      notice: "Insufficient evidence in this repository to answer the question.",
    }} />);

    expect(screen.getByRole("status")).toHaveTextContent("EVIDENCE GATE");
    expect(screen.getByRole("status")).toHaveTextContent("Insufficient evidence");
  });
});
