import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ErrorBoundary } from "../src/components/ErrorBoundary";
import { renderWithProviders } from "./helpers";

// Suppress React error boundary console.error in test output
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test render error");
  return <div>Content rendered</div>;
}

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    renderWithProviders(
      <ErrorBoundary>
        <div>Safe content</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Safe content")).toBeInTheDocument();
  });

  it("renders error fallback when child throws", () => {
    renderWithProviders(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Test render error")).toBeInTheDocument();
  });

  it("renders custom fallback when provided", () => {
    renderWithProviders(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Custom fallback")).toBeInTheDocument();
  });

  it("shows try again button that resets error state", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Try Again" });
    expect(button).toBeInTheDocument();
    // Clicking try again resets — but child will throw again
    await user.click(button);
    // Error boundary re-renders child which throws again
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });
});
