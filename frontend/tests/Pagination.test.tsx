import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, render } from "@testing-library/react";
import { Pagination } from "../src/components/Pagination";

describe("Pagination", () => {
  it("is hidden when total <= pageSize", () => {
    const { container } = render(
      <Pagination page={1} pageSize={10} total={5} onPageChange={() => {}} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("is visible when total > pageSize", () => {
    render(<Pagination page={1} pageSize={10} total={25} onPageChange={() => {}} />);
    expect(screen.getByText("Prev")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  it("shows correct range text", () => {
    render(<Pagination page={2} pageSize={10} total={25} onPageChange={() => {}} />);
    expect(screen.getByText(/11–20 of 25/)).toBeInTheDocument();
  });

  it("disables Prev on first page", () => {
    render(<Pagination page={1} pageSize={10} total={25} onPageChange={() => {}} />);
    expect(screen.getByText("Prev")).toBeDisabled();
  });

  it("disables Next on last page", () => {
    render(<Pagination page={3} pageSize={10} total={25} onPageChange={() => {}} />);
    expect(screen.getByText("Next")).toBeDisabled();
  });

  it("calls onPageChange on click", () => {
    const handler = vi.fn();
    render(<Pagination page={2} pageSize={10} total={25} onPageChange={handler} />);
    fireEvent.click(screen.getByText("Prev"));
    expect(handler).toHaveBeenCalledWith(1);
    fireEvent.click(screen.getByText("Next"));
    expect(handler).toHaveBeenCalledWith(3);
  });
});
