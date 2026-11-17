import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { renderWithProviders } from "@/test/render";
import { ME, json, makeEntry, makePost } from "./fixtures";
import { PostList } from "./post-list";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { PostCard } from "./post-card";
import { useTimeline, usePost } from "./use-posts";
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
  beforeEach(() => {
    vi.clearAllMocks();
  });

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

  it("allows saving an empty body on a quote", async () => {
    mockApi();
    renderWithProviders(
      <PostCard post={makePost({ quote_unavailable: true })} />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Opções do post" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Editar" }),
    );
    await userEvent.clear(screen.getByRole("textbox"));
    expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
  });

  it("still blocks an empty body on a plain post", async () => {
    mockApi();
    renderWithProviders(<PostCard post={makePost()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Opções do post" }),
    );
    await userEvent.click(
      await screen.findByRole("menuitem", { name: "Editar" }),
    );
    await userEvent.clear(screen.getByRole("textbox"));
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
  });

  describe("interactions", () => {
    const bob = {
      username: "bob",
      display_name: "Bob",
      bio: "",
      avatar_url: null,
    };

    function mockToggle(fail = false) {
      const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
        if (path === "/api/v1/auth/me") return json(ME);
        if (path === "/api/v1/posts/p1/like") {
          if (fail) return json({ detail: "boom" }, 500);
          const on = init?.method === "PUT";
          return json(
            makePost({ liked: on, like_count: on ? 1 : 0 }),
          );
        }
        return json({ detail: "post_not_found" }, 404);
      });
      vi.stubGlobal("fetch", fetchMock);
      return fetchMock;
    }

    function LikeHolder() {
      const { data } = usePost("p1");
      return data ? <PostCard post={data} /> : null;
    }

    function likeCalls(fetchMock: ReturnType<typeof mockToggle>) {
      return fetchMock.mock.calls
        .filter(([path]) => path === "/api/v1/posts/p1/like")
        .map(([, init]) => init?.method);
    }

    function deferred() {
      let release: (response: Response) => void = () => {};
      const promise = new Promise<Response>((resolve) => {
        release = resolve;
      });
      return { promise, release };
    }

    it("likes optimistically and unlikes with DELETE", async () => {
      const gate = deferred();
      const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
        if (path === "/api/v1/auth/me") return json(ME);
        if (path === "/api/v1/posts/p1/like") {
          const on = init?.method === "PUT";
          if (on) return gate.promise;
          return json(makePost({ liked: false, like_count: 0 }));
        }
        if (path === "/api/v1/posts/p1") return json(makePost());
        return json({ detail: "post_not_found" }, 404);
      });
      vi.stubGlobal("fetch", fetchMock);
      renderWithProviders(<LikeHolder />);
      const like = await screen.findByRole("button", { name: "Curtir" });
      expect(like).toHaveAttribute("aria-pressed", "false");
      expect(screen.queryByText("0")).not.toBeInTheDocument();

      await userEvent.click(like);
      expect(await screen.findByText("1")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Curtir" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      gate.release(json(makePost({ liked: true, like_count: 1 })));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Curtir" })).toBeEnabled(),
      );
      await userEvent.click(screen.getByRole("button", { name: "Curtir" }));
      await waitFor(() =>
        expect(screen.queryByText("1")).not.toBeInTheDocument(),
      );
      expect(likeCalls(fetchMock)).toEqual(["PUT", "DELETE"]);
    });

    it("rolls the like back on error and shows a toast", async () => {
      const gate = deferred();
      vi.stubGlobal(
        "fetch",
        vi.fn(async (path: string) => {
          if (path === "/api/v1/auth/me") return json(ME);
          if (path === "/api/v1/posts/p1/like") return gate.promise;
          if (path === "/api/v1/posts/p1") {
            return json(makePost({ like_count: 2 }));
          }
          return json({ detail: "post_not_found" }, 404);
        }),
      );
      renderWithProviders(<LikeHolder />);
      await userEvent.click(
        await screen.findByRole("button", { name: "Curtir" }),
      );
      expect(await screen.findByText("3")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Curtir" })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      gate.release(json({ detail: "boom" }, 500));
      await waitFor(() =>
        expect(screen.getByRole("button", { name: "Curtir" })).toHaveAttribute(
          "aria-pressed",
          "false",
        ),
      );
      expect(screen.getByText("2")).toBeInTheDocument();
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          "Não foi possível concluir a ação.",
        ),
      );
    });

    it("reverts only the failed post when another toggle succeeds", async () => {
      const gate = deferred();
      vi.stubGlobal(
        "fetch",
        vi.fn(async (path: string, init?: RequestInit) => {
          if (path === "/api/v1/auth/me") return json(ME);
          if (path.startsWith("/api/v1/timeline")) {
            return json({
              items: [
                makeEntry(makePost({ id: "x", body: "post x" })),
                makeEntry(makePost({ id: "y", body: "post y" })),
              ],
              next_cursor: null,
            });
          }
          if (path === "/api/v1/posts/x/like") return gate.promise;
          if (path === "/api/v1/posts/y/bookmark" && init?.method === "PUT") {
            return json(makePost({ id: "y", bookmarked: true }));
          }
          return json({ detail: "post_not_found" }, 404);
        }),
      );
      function Timeline() {
        return <PostList query={useTimeline()} />;
      }
      renderWithProviders(<Timeline />);
      await screen.findByText("post x");
      const [cardX, cardY] = screen.getAllByRole("article");
      await userEvent.click(
        within(cardX).getByRole("button", { name: "Curtir" }),
      );
      await userEvent.click(
        within(cardY).getByRole("button", { name: "Salvar post" }),
      );
      await waitFor(() =>
        expect(
          within(cardY).getByRole("button", { name: "Salvar post" }),
        ).toBeEnabled(),
      );
      gate.release(json({ detail: "boom" }, 500));
      await waitFor(() =>
        expect(
          within(cardX).getByRole("button", { name: "Curtir" }),
        ).toHaveAttribute("aria-pressed", "false"),
      );
      expect(
        within(cardY).getByRole("button", { name: "Salvar post" }),
      ).toHaveAttribute("aria-pressed", "true");
    });

    it("marks embeds as unavailable when the quoted post is deleted", async () => {
      const bobQuote = {
        id: "a",
        author: bob,
        body: "original text",
        media: [],
        created_at: new Date().toISOString(),
        edited_at: null,
        is_quote: false,
      };
      vi.stubGlobal(
        "fetch",
        vi.fn(async (path: string, init?: RequestInit) => {
          if (path === "/api/v1/auth/me") return json(ME);
          if (path.startsWith("/api/v1/timeline")) {
            return json({
              items: [
                makeEntry(
                  makePost({ id: "q", author: bob, body: "my take", quote: bobQuote }),
                ),
                makeEntry(makePost({ id: "a", body: "original text" })),
              ],
              next_cursor: null,
            });
          }
          if (path === "/api/v1/posts/a" && init?.method === "DELETE") {
            return new Response(null, { status: 204 });
          }
          return json({ detail: "post_not_found" }, 404);
        }),
      );
      function Timeline() {
        return <PostList query={useTimeline()} />;
      }
      renderWithProviders(<Timeline />);
      await screen.findByText("my take");
      await userEvent.click(
        await screen.findByRole("button", { name: "Opções do post" }),
      );
      await userEvent.click(
        await screen.findByRole("menuitem", { name: "Excluir" }),
      );
      await userEvent.click(
        await screen.findByRole("button", { name: "Excluir" }),
      );
      expect(await screen.findByText("Post indisponível")).toBeInTheDocument();
      expect(screen.queryByText("original text")).not.toBeInTheDocument();
    });

    it("reflects the viewer state in aria-pressed", async () => {
      mockToggle();
      renderWithProviders(
        <PostCard
          post={makePost({ liked: true, reposted: true, bookmarked: true })}
        />,
      );
      await userEvent.click(
        await screen.findByRole("button", { name: "Compartilhar" }),
      );
      expect(
        await screen.findByRole("menuitem", { name: "Desfazer repost" }),
      ).toBeInTheDocument();
      await userEvent.keyboard("{Escape}");
      for (const name of ["Compartilhar", "Curtir", "Salvar post"]) {
        expect(await screen.findByRole("button", { name })).toHaveAttribute(
          "aria-pressed",
          "true",
        );
      }
    });

    it("toggles the repost from the menu", async () => {
      const fetchMock = mockToggle();
      renderWithProviders(<PostCard post={makePost({ reposted: true })} />);
      await userEvent.click(
        await screen.findByRole("button", { name: "Compartilhar" }),
      );
      await userEvent.click(
        await screen.findByRole("menuitem", { name: "Desfazer repost" }),
      );
      await waitFor(() =>
        expect(
          fetchMock.mock.calls.some(
            ([path, init]) =>
              path === "/api/v1/posts/p1/repost" && init?.method === "DELETE",
          ),
        ).toBe(true),
      );
    });

    it("offers to repost a post that is not reposted", async () => {
      mockToggle();
      renderWithProviders(<PostCard post={makePost()} />);
      const trigger = await screen.findByRole("button", {
        name: "Compartilhar",
      });
      expect(trigger).toHaveAttribute("aria-pressed", "false");
      await userEvent.click(trigger);
      expect(
        await screen.findByRole("menuitem", { name: "Repostar" }),
      ).toBeInTheDocument();
    });

    it("bookmarks with PUT", async () => {
      const fetchMock = mockToggle();
      renderWithProviders(<PostCard post={makePost()} />);
      await userEvent.click(
        await screen.findByRole("button", { name: "Salvar post" }),
      );
      await waitFor(() =>
        expect(
          fetchMock.mock.calls.some(
            ([path, init]) =>
              path === "/api/v1/posts/p1/bookmark" && init?.method === "PUT",
          ),
        ).toBe(true),
      );
    });

    it("renders the reposted header", async () => {
      mockToggle();
      renderWithProviders(<PostCard post={makePost()} repostedBy={bob} />);
      expect(await screen.findByText("@bob repostou")).toBeInTheDocument();
    });

    it("renders a quote embed linking to the quoted post", async () => {
      mockToggle();
      const quote = {
        id: "q1",
        author: bob,
        body: "<i>original</i>",
        media: [],
        created_at: new Date().toISOString(),
        edited_at: null,
        is_quote: false,
      };
      renderWithProviders(<PostCard post={makePost({ quote })} />);
      const text = await screen.findByText("<i>original</i>");
      expect(text.closest("a")).toHaveAttribute("href", "/post/q1");
      expect(document.querySelector("i")).toBeNull();
    });

    it("renders the unavailable quote state", async () => {
      mockToggle();
      renderWithProviders(
        <PostCard post={makePost({ quote_unavailable: true })} />,
      );
      expect(await screen.findByText("Post indisponível")).toBeInTheDocument();
    });

    it("copies the absolute post link and shows a toast", async () => {
      mockToggle();
      const user = userEvent.setup();
      const writeText = vi
        .spyOn(navigator.clipboard, "writeText")
        .mockResolvedValue();
      renderWithProviders(<PostCard post={makePost()} />);
      await user.click(
        await screen.findByRole("button", { name: "Compartilhar" }),
      );
      await user.click(
        await screen.findByRole("menuitem", { name: "Copiar link" }),
      );
      expect(writeText).toHaveBeenCalledWith(
        `${location.origin}/post/p1`,
      );
      await waitFor(() =>
        expect(toast.success).toHaveBeenCalledWith("Link copiado"),
      );
    });

    it("shows an error toast when the clipboard is unavailable", async () => {
      mockToggle();
      const user = userEvent.setup();
      Object.defineProperty(navigator, "clipboard", {
        value: undefined,
        configurable: true,
      });
      renderWithProviders(<PostCard post={makePost()} />);
      await user.click(
        await screen.findByRole("button", { name: "Compartilhar" }),
      );
      await user.click(
        await screen.findByRole("menuitem", { name: "Copiar link" }),
      );
      await waitFor(() =>
        expect(toast.error).toHaveBeenCalledWith(
          "Não foi possível copiar o link",
        ),
      );
    });

    it("shows an error toast when the clipboard fails", async () => {
      mockToggle();
      const user = userEvent.setup();
      vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
        new Error("denied"),
      );
      renderWithProviders(<PostCard post={makePost()} />);
      await user.click(
        await screen.findByRole("button", { name: "Compartilhar" }),
      );
      await user.click(
        await screen.findByRole("menuitem", { name: "Copiar link" }),
      );
      await waitFor(() => expect(toast.error).toHaveBeenCalled());
    });
  });
});
