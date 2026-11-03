import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ME, json, makePost } from "./fixtures";
import { PostPage } from "./post-page";

function renderPage(id: string) {
  renderWithProviders(
    <Routes>
      <Route path="/post/:id" element={<PostPage />} />
    </Routes>,
    `/post/${id}`,
  );
}

describe("PostPage", () => {
  it("shows the not-found state on a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        path === "/api/v1/auth/me"
          ? json(ME)
          : json({ detail: "post_not_found" }, 404),
      ),
    );
    renderPage("nope");
    expect(await screen.findByText("Este post não existe")).toBeInTheDocument();
  });

  it("renders the post", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        path === "/api/v1/auth/me"
          ? json(ME)
          : json(makePost({ body: "found me" })),
      ),
    );
    renderPage("p1");
    expect(await screen.findByText("found me")).toBeInTheDocument();
  });
});
