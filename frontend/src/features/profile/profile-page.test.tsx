import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ProfilePage } from "./profile-page";

const ME = {
  id: "1",
  email: "ana@example.com",
  username: "ana",
  display_name: "Ana",
  bio: "",
  avatar_url: null,
  birthday: null,
  phone: null,
  created_at: "2026-01-01T00:00:00Z",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(profiles: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      if (path === "/api/v1/auth/me") return json(ME);
      const username = path.split("/").pop() ?? "";
      return username in profiles
        ? json(profiles[username])
        : json({ detail: "user_not_found" }, 404);
    }),
  );
}

function renderProfile(username: string) {
  renderWithProviders(
    <Routes>
      <Route path="/:username" element={<ProfilePage />} />
    </Routes>,
    `/${username}`,
  );
}

const BOB = {
  username: "bob",
  display_name: "Bob Builder",
  bio: "I build things",
  avatar_url: null,
};

describe("ProfilePage", () => {
  it("renders a public profile", async () => {
    mockApi({ bob: BOB });
    renderProfile("bob");

    expect(await screen.findByText("Bob Builder")).toBeInTheDocument();
    expect(screen.getByText("@bob")).toBeInTheDocument();
    expect(screen.getByText("I build things")).toBeInTheDocument();
  });

  it("shows the edit button only on your own profile", async () => {
    mockApi({
      bob: BOB,
      ana: { ...BOB, username: "ana", display_name: "Ana" },
    });
    renderProfile("ana");
    expect(
      await screen.findByRole("button", { name: "Editar perfil" }),
    ).toBeInTheDocument();
  });

  it("hides the edit button on someone else's profile", async () => {
    mockApi({ bob: BOB });
    renderProfile("bob");
    await screen.findByText("Bob Builder");
    expect(
      screen.queryByRole("button", { name: "Editar perfil" }),
    ).not.toBeInTheDocument();
  });

  it("shows the not-found state on a 404", async () => {
    mockApi({});
    renderProfile("ghost");
    expect(
      await screen.findByText("Esta conta não existe"),
    ).toBeInTheDocument();
  });

  it("shows the renamed profile without requesting the old one", async () => {
    const renamed = { ...ME, username: "ana2" };
    const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
      if (path === "/api/v1/auth/me") return json(ME);
      if (path === "/api/v1/me" && init?.method === "PATCH") {
        return json(renamed);
      }
      if (path === "/api/v1/users/ana") {
        return json({ ...BOB, username: "ana", display_name: "Ana" });
      }
      if (path === "/api/v1/users/ana2") {
        return json({ ...BOB, username: "ana2", display_name: "Ana" });
      }
      return json({ detail: "user_not_found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderProfile("ana");

    await user.click(
      await screen.findByRole("button", { name: "Editar perfil" }),
    );
    const field = screen.getByLabelText("Nome de usuário");
    await user.clear(field);
    await user.type(field, "ana2");
    await user.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("@ana2")).toBeInTheDocument();
    expect(screen.queryByText("Carregando...")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([p]) => p === "/api/v1/users/ana"),
      ).toHaveLength(1),
    );
  });
});
