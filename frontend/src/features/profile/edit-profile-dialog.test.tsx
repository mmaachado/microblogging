import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Me } from "@/features/auth/use-auth";
import { renderWithProviders } from "@/test/render";
import { EditProfileDialog } from "./edit-profile-dialog";

const ME: Me = {
  id: "1",
  email: "ana@example.com",
  username: "ana",
  display_name: "Ana",
  bio: "hello",
  avatar_url: null,
  birthday: null,
  phone: null,
  created_at: "2026-01-01T00:00:00Z",
};

function renderDialog() {
  renderWithProviders(
    <EditProfileDialog me={ME} open onOpenChange={() => {}} />,
  );
}

describe("EditProfileDialog", () => {
  it("shows counters and disables save when the bio is too long", async () => {
    const user = userEvent.setup();
    renderDialog();

    expect(screen.getByText("3/50")).toBeInTheDocument();
    expect(screen.getByText("5/160")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Salvar" });
    expect(save).toBeEnabled();

    await user.type(screen.getByLabelText("Bio"), "x".repeat(156));
    expect(screen.getByText("161/160")).toBeInTheDocument();
    expect(save).toBeDisabled();
  });

  it("shows the username_taken message on the username field", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "username_taken" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderDialog();

    const username = screen.getByLabelText("Nome de usuário");
    await user.clear(username);
    await user.type(username, "bob");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(
        screen.getByText("Este nome de usuário já está em uso."),
      ).toBeInTheDocument(),
    );
    expect(username).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/me",
      expect.objectContaining({ method: "PATCH" }),
    );
  });

  it("explains that the private section is visible only to you", () => {
    renderDialog();
    expect(screen.getByText("Informações privadas")).toBeInTheDocument();
    expect(screen.getByText("Só você vê isso")).toBeInTheDocument();
    expect(screen.getByLabelText("Data de nascimento")).toHaveAttribute(
      "type",
      "date",
    );
  });

  it("counts code points, so 160 emoji are still allowed", () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText("Bio"), {
      target: { value: "😀".repeat(160) },
    });
    expect(screen.getByText("160/160")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
  });

  it("accepts only the four supported image types", () => {
    renderDialog();
    expect(screen.getByTestId("avatar-input")).toHaveAttribute(
      "accept",
      "image/jpeg,image/png,image/webp,image/gif",
    );
  });
});
