import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Monitors } from "./Monitoring";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
function mount(canEdit = true) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <Monitors canEdit={canEdit} />
    </QueryClientProvider>,
  );
}
test("heartbeat pokazuje token tylko po utworzeniu i pozwala go ukryć", async () => {
  const token = "test-only-heartbeat-token";
  let created = false;
  const fetcher = vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === "POST") {
      created = true;
      return new Response(JSON.stringify({ id: 1, heartbeat_token: token }), {
        status: 201,
      });
    }
    return new Response(
      JSON.stringify(
        created
          ? [
              {
                id: 1,
                name: "Cron",
                kind: "heartbeat",
                state: "UNKNOWN",
                recorded_state: "UNKNOWN",
                stale: true,
                paused: false,
                interval: 60,
                last_checked_at: null,
              },
            ]
          : [],
      ),
    );
  });
  vi.stubGlobal("fetch", fetcher);
  mount();
  await screen.findByText("Dodaj pierwszy monitor");
  fireEvent.click(screen.getByRole("button", { name: "Dodaj monitor" }));
  fireEvent.change(screen.getByLabelText("Nazwa monitora"), {
    target: { value: "Cron" },
  });
  fireEvent.change(screen.getByLabelText("Typ"), {
    target: { value: "heartbeat" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz monitor" }));
  await screen.findByDisplayValue(token);
  expect(sessionStorage.length).toBe(0);
  const call = fetcher.mock.calls.find(([, opts]) => opts?.method === "POST")!;
  expect(JSON.parse(call[1]?.body as string)).toMatchObject({
    kind: "heartbeat",
    name: "Cron",
  });
  fireEvent.click(screen.getByRole("button", { name: "Ukryj token" }));
  await waitFor(() =>
    expect(screen.queryByDisplayValue(token)).not.toBeInTheDocument(),
  );
});
test("podgląd nie udostępnia połączeń ani edycji; stary zielony stan jest oznaczony jako brak danych", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify([
            {
              id: 1,
              name: "Usługa",
              kind: "tcp",
              state: "UNKNOWN",
              recorded_state: "UP",
              stale: true,
              paused: false,
              interval: 60,
              last_checked_at: null,
            },
          ]),
        ),
    ),
  );
  mount(false);
  await screen.findByText("Usługa");
  expect(screen.getByText("Brak danych")).toBeInTheDocument();
  expect(screen.queryByText("Działa")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Wykonaj test" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Dodaj monitor" }),
  ).not.toBeInTheDocument();
});
