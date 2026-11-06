import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
  focusManager,
} from "@tanstack/react-query";
import { Monitors, type Monitor } from "./Monitoring";
import MonitorForm from "./MonitorForm";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  focusManager.setFocused(undefined);
});
const row: Monitor = {
  id: 1,
  name: "Usługa",
  kind: "tcp",
  state: "UNKNOWN",
  recorded_state: "UP",
  stale: true,
  paused: false,
  interval: 60,
  last_checked_at: null,
  timeout: 5,
  failure_threshold: 3,
  recovery_threshold: 2,
  revision: 1,
  config: { host: "127.0.0.1", port: 443 },
  tag_ids: [],
  group_id: null,
  resource_id: null,
  priority: "normal",
  has_credentials: false,
};
function mount(canEdit = true) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Monitors canEdit={canEdit} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status });
}
test("heartbeat pokazuje token tylko po utworzeniu i pozwala go ukryć", async () => {
  const token = "test-only-heartbeat-token";
  let created = false;
  const fetcher = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === "POST") {
      created = true;
      return response({ id: 1, heartbeat_token: token }, 201);
    }
    return response(
      path.startsWith("/api/monitors/search")
        ? {
            items: created ? [{ ...row, name: "Cron", kind: "heartbeat" }] : [],
            total: created ? 1 : 0,
          }
        : [],
    );
  });
  vi.stubGlobal("fetch", fetcher);
  mount();
  await screen.findByText("Dodaj pierwszy monitor");
  fireEvent.click(screen.getByRole("button", { name: "Dodaj monitor" }));
  fireEvent.change(screen.getByLabelText("Nazwa monitora"), {
    target: { value: "Cron" },
  });
  const basic = screen.getByRole("group", { name: "Podstawowe" });
  fireEvent.change(within(basic).getByRole("combobox", { name: "Typ" }), {
    target: { value: "heartbeat" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz monitor" }));
  await screen.findByDisplayValue(token);
  expect(sessionStorage.length).toBe(0);
  const call = fetcher.mock.calls.find(([, opts]) => opts?.method === "POST")!;
  expect(JSON.parse(call[1]?.body as string)).toMatchObject({
    name: "Cron",
    kind: "heartbeat",
  });
  fireEvent.click(screen.getByRole("button", { name: "Ukryj token" }));
  await waitFor(() =>
    expect(screen.queryByDisplayValue(token)).not.toBeInTheDocument(),
  );
});
test("podgląd nie udostępnia połączeń ani edycji; stary stan nie jest zielony", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) =>
      response(
        path.startsWith("/api/monitors/search")
          ? { items: [row], total: 1 }
          : [],
      ),
    ),
  );
  mount(false);
  await screen.findByText("Usługa");
  const current = screen.getByRole("row", { name: /Usługa/ });
  expect(within(current).getByText("Brak danych")).toBeInTheDocument();
  expect(within(current).queryByText("Działa")).not.toBeInTheDocument();
  for (const name of ["Wykonaj test", "Dodaj monitor", "Edytuj", "Usuń"])
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
});
test("edycja zachowuje sekrety bez odsyłania ich lub maski jako nowych danych", async () => {
  const fetcher = vi.fn(async () =>
    response({ ...row, kind: "http", has_credentials: true }),
  );
  vi.stubGlobal("fetch", fetcher);
  const done = vi.fn(async () => {});
  render(
    <MonitorForm
      initial={{
        ...row,
        kind: "http",
        has_credentials: true,
        config: { url: "https://example.org/", method: "GET" },
      }}
      groups={[]}
      tags={[]}
      resources={[]}
      onCancel={() => {}}
      onSaved={done}
    />,
  );
  expect(screen.queryByLabelText("Hasło HTTP")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Zapisz monitor" }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  const options = fetcher.mock.calls[0] as unknown as [string, RequestInit];
  const body = JSON.parse(options[1].body as string);
  expect(body.revision).toBe(1);
  expect(body).not.toHaveProperty("secrets");
  expect(body).not.toHaveProperty("clear_credentials");
});
test("usuwanie monitora wymaga potwierdzenia i wysyła rewizję", async () => {
  let removed = false;
  const fetcher = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === "DELETE") {
      removed = true;
      return new Response(null, { status: 204 });
    }
    return response(
      path.startsWith("/api/monitors/search")
        ? { items: removed ? [] : [row], total: removed ? 0 : 1 }
        : [],
    );
  });
  vi.stubGlobal("fetch", fetcher);
  mount();
  await screen.findByText("Usługa");
  fireEvent.click(screen.getByRole("button", { name: "Usuń" }));
  expect(
    fetcher.mock.calls.filter(([, o]) => o?.method === "DELETE"),
  ).toHaveLength(0);
  const dialog = screen.getByRole("alertdialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Usuń" }));
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(
        ([p, o]) =>
          p === "/api/monitors/1?revision=1" && o?.method === "DELETE",
      ),
    ).toBe(true),
  );
});

test("monitor odświeża stan również przy braku aktywności okna", async () => {
  focusManager.setFocused(false);
  let calls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      if (!path.startsWith("/api/monitors/search")) return response([]);
      calls++;
      return response({
        items: [
          { ...row, state: calls > 1 ? "UP" : "UNKNOWN", stale: calls === 1 },
        ],
        total: 1,
      });
    }),
  );
  mount(false);
  await screen.findByText("Usługa");
  await waitFor(
    () =>
      expect(
        within(screen.getByRole("row", { name: /Usługa/ })).getByText(
          "Działa",
          { exact: true },
        ),
      ).toBeInTheDocument(),
    { timeout: 8500 },
  );
}, 12000);
