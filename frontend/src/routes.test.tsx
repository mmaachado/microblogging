import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ProtectedRoute } from "./routes";

describe("ProtectedRoute", () => {
  it("shows an error state with retry on a server error", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ProtectedRoute />);

    expect(
      await screen.findByText("Não foi possível carregar sua sessão."),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Tentar novamente" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
