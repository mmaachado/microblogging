export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(
  path: string,
  init: Omit<RequestInit, "body"> & { body?: unknown } = {},
): Promise<T> {
  const { body, headers, ...rest } = init;
  const isForm = body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...rest,
      headers: {
        Accept: "application/json",
        ...(body === undefined || isForm
          ? {}
          : { "Content-Type": "application/json" }),
        ...headers,
      },
      body:
        body === undefined || isForm
          ? (body as BodyInit)
          : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error");
  }
  if (!response.ok) {
    let detail = "unknown_error";
    try {
      const data = await response.json();
      detail =
        typeof data.detail === "string" ? data.detail : "validation_error";
    } catch {
      // body is not JSON; keep the generic code
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
