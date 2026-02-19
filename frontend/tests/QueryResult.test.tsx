import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { QueryResult } from "../src/components/QueryResult";
import { renderWithProviders, mockFetch } from "./helpers";

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch({}));
});

function SuccessWrapper() {
  const query = useQuery({
    queryKey: ["test-success"],
    queryFn: () => Promise.resolve(["item1", "item2"]),
  });
  return (
    <QueryResult query={query}>
      {(data) => (
        <ul>
          {data.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </QueryResult>
  );
}

function ErrorWrapper() {
  const query = useQuery({
    queryKey: ["test-error"],
    queryFn: () => Promise.reject(new Error("API is down")),
    retry: false,
  });
  return (
    <QueryResult query={query}>
      {(data) => <div>{JSON.stringify(data)}</div>}
    </QueryResult>
  );
}

function InlineLoadingWrapper() {
  const query = useQuery({
    queryKey: ["test-inline"],
    queryFn: () => new Promise(() => {}), // never resolves
  });
  return (
    <QueryResult query={query} inline>
      {(data) => <div>{JSON.stringify(data)}</div>}
    </QueryResult>
  );
}

describe("QueryResult", () => {
  it("shows loading state then data", async () => {
    renderWithProviders(<SuccessWrapper />);
    // Initially loading
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    // Then data appears
    await waitFor(() => {
      expect(screen.getByText("item1")).toBeInTheDocument();
    });
    expect(screen.getByText("item2")).toBeInTheDocument();
  });

  it("shows error state with retry button", async () => {
    renderWithProviders(<ErrorWrapper />);
    await waitFor(() => {
      expect(screen.getByText("API is down")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows inline loading text", () => {
    renderWithProviders(<InlineLoadingWrapper />);
    const loading = screen.getByText("Loading...");
    expect(loading.tagName).toBe("SPAN");
  });
});
