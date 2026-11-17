import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ME, json, makeEntry, makePost } from "@/features/posts/fixtures";
import { renderWithProviders } from "@/test/render";
import { BookmarksPage } from "./bookmarks-page";

function mockApi(items: ReturnType<typeof makeEntry>[]) {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/v1/auth/me") return json(ME);
    if (path.startsWith("/api/v1/me/bookmarks")) {
      return json({ items, next_cursor: null });
    }
    if (path === "/api/v1/posts/p1/bookmark" && init?.method === "DELETE") {
      return json(makePost({ id: "p1", bookmarked: false }));
    }
    return json({ detail: "post_not_found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("BookmarksPage", () => {
  it("lists the saved posts under the title", async () => {
    mockApi([
      makeEntry(makePost({ id: "p1", body: "first", bookmarked: true })),
      makeEntry(makePost({ id: "p2", body: "second", bookmarked: true })),
    ]);
    renderWithProviders(<BookmarksPage />);
    expect(await screen.findByText("first")).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Salvos" })).toBeInTheDocument();
  });

  it("removes the entry when unbookmarking", async () => {
    const fetchMock = mockApi([
      makeEntry(makePost({ id: "p1", body: "first", bookmarked: true })),
      makeEntry(makePost({ id: "p2", body: "second", bookmarked: true })),
    ]);
    renderWithProviders(<BookmarksPage />);
    await screen.findByText("first");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Salvar post" })[0],
    );
    await waitFor(() =>
      expect(screen.queryByText("first")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("second")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([path, init]) =>
          path === "/api/v1/posts/p1/bookmark" && init?.method === "DELETE",
      ),
    ).toBe(true);
  });

  it("shows the empty state", async () => {
    mockApi([]);
    renderWithProviders(<BookmarksPage />);
    expect(
      await screen.findByText("Você ainda não salvou nada"),
    ).toBeInTheDocument();
  });
});
