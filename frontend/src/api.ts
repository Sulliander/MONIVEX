import i18n from "./i18n";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfter?: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  extra: Record<string, string> = {},
  recoverCsrf = true,
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
  if (
    response.status === 401 &&
    path !== "/auth/me" &&
    !path.startsWith("/auth/login")
  ) {
    window.dispatchEvent(new Event("monivex:session-expired"));
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (
      response.status === 403 &&
      recoverCsrf &&
      path !== "/auth/csrf" &&
      data.detail ===
        "Nieprawidłowy token bezpieczeństwa. Zaloguj się ponownie."
    ) {
      const csrf = await api<{ csrf_token: string }>("/auth/csrf", "POST");
      sessionStorage.setItem("csrf", csrf.csrf_token);
      return api<T>(path, method, body, extra, false);
    }
    throw new ApiError(
      typeof data.detail === "string" ? data.detail : i18n.t("apiError"),
      response.status,
      Number(response.headers.get("Retry-After")) || undefined,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
