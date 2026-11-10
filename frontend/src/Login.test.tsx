import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Login from "./Login";
import { api } from "./api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
const json = (body: unknown, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
async function credentials() {
  fireEvent.change(screen.getByLabelText("Nazwa użytkownika"), {
    target: { value: "owner" },
  });
  fireEvent.change(screen.getByLabelText("Hasło", { exact: true }), {
    target: { value: "long-test-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zaloguj się" }));
}
test("sesja i CSRF powstają w interfejsie dopiero po potwierdzeniu 2FA", async () => {
  const done = vi.fn(async () => {});
  const fetcher = vi.fn(async (path: string) =>
    json(
      path.endsWith("/verify")
        ? { csrf_token: "verified-csrf", two_factor_required: false }
        : { two_factor_required: true },
    ),
  );
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter>
      <Login done={done} notice="" />
    </MemoryRouter>,
  );
  await credentials();
  await screen.findByRole("heading", { name: "Potwierdź swoją tożsamość" });
  expect(sessionStorage.getItem("csrf")).toBeNull();
  expect(done).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Kod z aplikacji"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź logowanie" }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(sessionStorage.getItem("csrf")).toBe("verified-csrf");
});
test("wygaśnięcie wyzwania wraca do hasła i nie zachowuje kodu", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      path.endsWith("/verify")
        ? json(
            { detail: "Etap weryfikacji wygasł. Zaloguj się ponownie." },
            401,
          )
        : json({ two_factor_required: true }),
    ),
  );
  render(
    <MemoryRouter>
      <Login done={async () => {}} notice="" />
    </MemoryRouter>,
  );
  await credentials();
  await screen.findByLabelText("Kod z aplikacji");
  fireEvent.change(screen.getByLabelText("Kod z aplikacji"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Potwierdź logowanie" }));
  await screen.findByRole("heading", { name: "Zaloguj się" });
  expect(screen.getByLabelText("Hasło", { exact: true })).toHaveValue("");
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Etap weryfikacji wygasł",
  );
});
test("blokada logowania respektuje Retry-After i pokazuje komunikat", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      json({ detail: "Zbyt wiele prób." }, 429, { "Retry-After": "90" }),
    ),
  );
  render(
    <MemoryRouter>
      <Login done={async () => {}} notice="" />
    </MemoryRouter>,
  );
  await credentials();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Blokada bezpieczeństwa",
  );
  expect(screen.getByRole("button", { name: "Zaloguj się" })).toBeDisabled();
});
test("kod odzyskiwania zastępuje TOTP i nie jest zapisywany w przeglądarce", async () => {
  const fetcher = vi.fn(async () => json({ two_factor_required: true }));
  vi.stubGlobal("fetch", fetcher);
  render(
    <MemoryRouter>
      <Login done={async () => {}} notice="" />
    </MemoryRouter>,
  );
  await credentials();
  await screen.findByLabelText("Kod z aplikacji");
  fireEvent.click(
    screen.getByRole("button", { name: "Użyj kodu odzyskiwania" }),
  );
  const input = screen.getByLabelText("Kod odzyskiwania");
  expect(input).toHaveAttribute("data-private");
  fireEvent.change(input, { target: { value: "recovery-test-value" } });
  expect(sessionStorage.length).toBe(0);
  fireEvent.click(
    screen.getByRole("button", { name: "Użyj aplikacji uwierzytelniającej" }),
  );
  expect(screen.getByLabelText("Kod z aplikacji")).toHaveValue("");
});
test("odświeżenie CSRF po otwarciu nowej karty ponawia operację tylko raz", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      json(
        { detail: "Nieprawidłowy token bezpieczeństwa. Zaloguj się ponownie." },
        403,
      ),
    )
    .mockResolvedValueOnce(json({ csrf_token: "new-csrf" }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetcher);
  await api("/auth/logout", "POST");
  expect(fetcher.mock.calls.map((c) => c[0])).toEqual([
    "/api/auth/logout",
    "/api/auth/csrf",
    "/api/auth/logout",
  ]);
  expect(fetcher.mock.calls[2][1].headers["X-CSRF-Token"]).toBe("new-csrf");
});
