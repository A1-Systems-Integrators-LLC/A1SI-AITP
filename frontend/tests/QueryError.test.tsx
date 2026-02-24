import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { QueryError } from "../src/components/QueryError";
import { renderWithProviders } from "./helpers";

describe("QueryError", () => {
  it("renders error message from Error object", () => {
    renderWithProviders(<QueryError error={new Error("Something broke")} />);
    expect(screen.getByText("Something broke")).toBeInTheDocument();
  });

  it("renders custom message over error", () => {
    renderWithProviders(
      <QueryError error={new Error("original")} message="Custom message" />,
    );
    expect(screen.getByText("Custom message")).toBeInTheDocument();
    expect(screen.queryByText("original")).not.toBeInTheDocument();
  });

  it("renders retry button when onRetry is provided", () => {
    renderWithProviders(<QueryError error={null} message="Error" onRetry={() => {}} />);
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("calls onRetry when retry button is clicked", () => {
    const onRetry = vi.fn();
    renderWithProviders(<QueryError error={null} message="Error" onRetry={onRetry} />);
    fireEvent.click(screen.getByText("Retry"));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
