import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ME, json, makePost } from "./fixtures";
import { PostList } from "./post-list";
import { useTimeline } from "./use-posts";

function Timeline() {
  return <PostList query={useTimeline()} />;
}

describe("PostList", () => {
  it("loads more with the next cursor and appends", async () => {
    const fetchMock = vi.fn(async (path: string) => {
      if (path === "/api/v1/auth/me") return json(ME);
      if (path.includes("cursor=c1")) {
        return json({
          items: [makePost({ id: "p2", body: "second" })],
          next_cursor: null,
        });
      }
      return json({
        items: [makePost({ id: "p1", body: "first" })],
        next_cursor: "c1",
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<Timeline />);

    expect(await screen.findByText("first")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Carregar mais" }),
    );
    expect(await screen.findByText("second")).toBeInTheDocument();
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Carregar mais" }),
    ).not.toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        path === "/api/v1/auth/me"
          ? json(ME)
          : json({ items: [], next_cursor: null }),
      ),
    );
    renderWithProviders(<Timeline />);
    expect(await screen.findByText("Nenhum post ainda")).toBeInTheDocument();
  });
});
