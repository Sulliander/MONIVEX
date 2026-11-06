import i18n from "./i18n";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  extra: Record<string, string> = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": sessionStorage.getItem("csrf") || "",
        ...extra,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(i18n.t("networkError"), 0);
  }
  if (response.status === 401 && !["/auth/me", "/auth/login"].includes(path)) {
    window.dispatchEvent(new Event("monivex:session-expired"));
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof data.detail === "string" ? data.detail : i18n.t("apiError"),
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
