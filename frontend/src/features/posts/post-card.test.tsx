import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ME, json, makePost } from "./fixtures";
import { PostCard } from "./post-card";
import { usePost } from "./use-posts";
import { useMe } from "@/features/auth/use-auth";

function MeProbe() {
  const { data } = useMe();
  return data ? <span>session:{data.username}</span> : null;
}

function Holder() {
  const { data } = usePost("p1");
  return data ? <PostCard post={data} /> : null;
}

function mockApi() {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/v1/auth/me") return json(ME);
    if (path === "/api/v1/posts/p1" && init?.method === "PATCH") {
      const { body } = JSON.parse(init.body as string);
      return json(makePost({ body, edited_at: new Date().toISOString() }));
    }
    if (path === "/api/v1/posts/p1" && init?.method === "DELETE") {
      return new Response(null, { status: 204 });
    }
    if (path === "/api/v1/posts/p1") return json(makePost());
    return json({ detail: "post_not_found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("PostCard", () => {
  it("renders the body as text", async () => {
    mockApi();
    renderWithProviders(<PostCard post={makePost({ body: "<b>x</b>" })} />);
    expect(await screen.findByText("<b>x</b>")).toBeInTheDocument();
    expect(document.querySelector("b")).toBeNull();
  });

  it("shows the edited marker", async () => {
    mockApi();
    renderWithProviders(
      <PostCard post={makePost({ edited_at: new Date().toISOString() })} />,
    );
    expect(await screen.findByText("editado")).toBeInTheDocument();
  });

  it("shows the menu only to the author", async () => {
    mockApi();
    const other = makePost({
      author: {
        username: "bob",
        display_name: "Bob",
        bio: "",
        avatar_url: null,
      },
    });
    renderWithProviders(
      <>
        <MeProbe />
        <PostCard post={other} />
      </>,
    );
    await screen.findByText("@bob");
    await screen.findByText("session:ana");
    expect(
      screen.queryByRole("button", { name: "Opções do post" }),
    ).not.toBeInTheDocument();
  });

  it("labels the video", async () => {
    mockApi();
    const media = [{ kind: "video" as const, url: "/media/v.mp4", mime: "video/mp4" }];
    renderWithProviders(<PostCard post={makePost({ media })} />);
    expect(await screen.findByLabelText("Vídeo do post")).toBeInTheDocument();
  });

  it("shows the menu to the author", async () => {
    mockApi();
    renderWithProviders(<PostCard post={makePost()} />);
    expect(
      await screen.findByRole("button", { name: "Opções do post" }),
    ).toBeInTheDocument();
  });

  it("edits the body through PATCH", async () => {
    const fetchMock = mockApi();
    renderWithProviders(<Holder />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Opções do post" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Editar" }),
    );
    const box = screen.getByRole("textbox");
    await userEvent.clear(box);
    await userEvent.type(box, "new text");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByText("new text")).toBeInTheDocument();
    expect(await screen.findByText("editado")).toBeInTheDocument();
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH");
    expect(JSON.parse(patch?.[1]?.body as string)).toEqual({
      body: "new text",
    });
  });

  it("deletes after confirmation", async () => {
    const fetchMock = mockApi();
    renderWithProviders(<PostCard post={makePost()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Opções do post" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Excluir" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Excluir" }),
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(
        true,
      ),
    );
  });
});
