import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  localStorage.clear();
});
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
test("kreator waliduje dane i wysyła sekret wyłącznie w nagłówku", async () => {
  const fetcher = vi.fn(async (path: string, _options?: RequestInit) => {
    void _options;
    return path === "/api/setup/status"
      ? json({ initialized: false })
      : path === "/api/setup"
        ? json({}, 201)
        : json({}, 401);
  });
  vi.stubGlobal("fetch", fetcher);
  mount();
  await screen.findByText("Witaj w MONIVEX");
  fireEvent.click(screen.getByText("Dalej"));
  await screen.findByRole("heading", { name: "Właściciel" });
  fireEvent.click(screen.getByText("Dalej"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sprawdź dane");
  fireEvent.change(screen.getByLabelText("Nazwa użytkownika"), {
    target: { value: "owner" },
  });
  fireEvent.change(screen.getByLabelText("Hasło"), {
    target: { value: "very-long-password" },
  });
  fireEvent.change(screen.getByLabelText("Sekret inicjalizacyjny"), {
    target: { value: "s".repeat(48) },
  });
  fireEvent.click(screen.getByText("Dalej"));
  await waitFor(() =>
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByText("Dalej"));
  await screen.findByText(
    "Pierwszy monitor dodasz po zalogowaniu. Konfiguracja SMTP będzie dostępna w etapie powiadomień.",
  );
  fireEvent.click(screen.getByText("Dalej"));
  await screen.findByText("Podsumowanie");
  fireEvent.click(screen.getByText("Zakończ konfigurację"));
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([path]) => path === "/api/setup")).toBe(
      true,
    ),
  );
  const call = fetcher.mock.calls.find(([path]) => path === "/api/setup")!;
  expect((call[1]?.headers as Record<string, string>)["X-Setup-Token"]).toBe(
    "s".repeat(48),
  );
  expect(call[1]?.body).not.toContain("token");
});
test("logowanie przedstawia błąd backendu", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      path === "/api/setup/status"
        ? json({ initialized: true })
        : json({ detail: "Nieprawidłowy login lub hasło." }, 401),
    ),
  );
  mount();
  await screen.findByRole("heading", { name: "Zaloguj się" });
  fireEvent.change(screen.getByLabelText("Nazwa użytkownika"), {
    target: { value: "owner" },
  });
  fireEvent.change(screen.getByLabelText("Hasło"), {
    target: { value: "wrong" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zaloguj się" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Nieprawidłowy login lub hasło.",
  );
});
test("panel pokazuje jawnie brak silnika zamiast fikcyjnych wyników", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      json(
        path === "/api/setup/status"
          ? { initialized: true }
          : path === "/api/auth/me"
            ? { id: 1, username: "owner", role: "owner" }
            : path === "/api/installation"
              ? { name: "MONIVEX", timezone: "UTC", version: "0.1.0" }
              : {
                  monitoring_available: true,
                  worker_status: "stale",
                  last_cycle_at: null,
                  monitors: [],
                  incidents: [],
                },
      ),
    ),
  );
  mount();
  expect(
    await screen.findByText(
      "Brak aktualnego sygnału workera. Stany monitorów mogą być nieaktualne.",
    ),
  ).toBeInTheDocument();
  expect(screen.getAllByText("0")).toHaveLength(5);
});
