import { test, expect } from "@playwright/test";
import { capture } from "./evidence";
import { securityFlow } from "./security";
import { randomBytes } from "node:crypto";
let heartbeatTimer: ReturnType<typeof setInterval> | undefined;
test.afterEach(() => {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
});
test("pierwsza konfiguracja, sesja, motyw, hasło i ponowne logowanie", async ({
  page,
  request,
}) => {
  const secret = process.env.MONIVEX_TEST_SETUP_TOKEN;
  if (!secret)
    throw new Error(
      "Wymagany MONIVEX_TEST_SETUP_TOKEN oraz nowa testowa baza.",
    );
  const password = randomBytes(24).toString("hex");
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Witaj w MONIVEX" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dalej", exact: true }).click();
  await page.getByLabel("Nazwa użytkownika").fill("owner");
  await page.getByLabel("Hasło", { exact: true }).fill(password);
  await page.getByLabel("Sekret inicjalizacyjny").fill(secret);
  await page.getByRole("button", { name: "Dalej", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Instalacja", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Nazwa instalacji").fill("MONIVEX");
  await page.getByRole("button", { name: "Dalej", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Usługi opcjonalne" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Dalej", exact: true }).click();
  await page.getByRole("button", { name: "Zakończ konfigurację" }).click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się" }),
  ).toBeVisible();
  async function login(value: string) {
    await page.getByLabel("Nazwa użytkownika").fill("owner");
    await page.getByLabel("Hasło", { exact: true }).fill(value);
    await page.getByRole("button", { name: "Zaloguj się" }).click();
  }
  await capture(page, "01-logowanie");
  await login(password);
  await expect(page.getByRole("heading", { name: "Przegląd" })).toBeVisible();
  await expect(page.getByText("Silnik monitoringu")).toBeVisible();
  await capture(page, "02-pulpit-ciemny");
  await page.getByLabel("Motyw").selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Przegląd" })).toBeVisible();
  await page.getByRole("link", { name: "Ustawienia", exact: true }).click();
  await page.getByLabel("Obecne hasło").fill(password);
  await page
    .getByLabel("Nowe hasło", { exact: true })
    .fill(password + "changed");
  await page.getByLabel("Powtórz nowe hasło").fill(password + "changed");
  await page
    .getByRole("button", { name: "Zmień hasło i zakończ sesje" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "Hasło zostało zmienione",
  );
  await login(password + "changed");
  await expect(page.getByRole("heading", { name: "Przegląd" })).toBeVisible();
  if (process.env.MONIVEX_TEST_WORKER === "1") {
    await page
      .getByRole("link", { name: "Monitory", exact: true })
      .first()
      .click();
    await page.getByRole("button", { name: "Dodaj monitor" }).click();
    await page.getByLabel("Nazwa monitora").fill("Heartbeat testowy");
    await page
      .getByRole("group", { name: "Podstawowe" })
      .getByRole("combobox", { name: "Typ", exact: true })
      .selectOption("heartbeat");
    await page.getByLabel("Interwał (s)", { exact: true }).fill("10");
    const created = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/monitors") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Zapisz monitor" }).click();
    const response = await created;
    expect(response.status()).toBe(201);
    const monitor = await response.json();
    const signal = await request.post(`/api/heartbeats/${monitor.id}`, {
      headers: { Authorization: `Bearer ${monitor.heartbeat_token}` },
    });
    expect(signal.status()).toBe(204);
    heartbeatTimer = setInterval(() => {
      void request
        .post(`/api/heartbeats/${monitor.id}`, {
          headers: { Authorization: `Bearer ${monitor.heartbeat_token}` },
        })
        .catch(() => {});
    }, 2000);
    const list = await request.get("/api/monitors");
    expect(list.status()).toBe(401);
    await page.getByRole("button", { name: "Ukryj token" }).click();
    const row = page.getByRole("row").filter({ hasText: "Heartbeat testowy" });
    try {
      await expect(row.getByText("Działa", { exact: true })).toBeVisible();
    } catch (error) {
      const snapshot = await page.request.get("/api/monitors/search");
      const data = await snapshot.json();
      console.error(
        JSON.stringify({
          event: "heartbeat_ui_timeout",
          visibility: await page.evaluate(() => document.visibilityState),
          backend_status: snapshot.status(),
          states: data.items?.map((m: { id: number; state: string }) => ({
            id: m.id,
            state: m.state,
          })),
        }),
      );
      throw error;
    }
    await row.getByRole("button", { name: "Historia wyników" }).click();
    await expect(
      page.getByText("Heartbeat jest aktualny.").first(),
    ).toBeVisible();
    await page.getByRole("button", { name: "Zamknij", exact: true }).click();
    await row.getByRole("button", { name: "Wstrzymaj" }).click();
    await expect(row.getByText("Wstrzymany", { exact: true })).toBeVisible();
    await row.getByRole("button", { name: "Wznów" }).click();
    await expect(row.getByText("Działa", { exact: true })).toBeVisible();
  }

  if (process.env.MONIVEX_TEST_MANAGEMENT === "1") {
    await page.getByRole("link", { name: "Grupy", exact: true }).click();
    await page.getByRole("button", { name: "Dodaj grupę" }).click();
    await page.getByLabel("Nazwa", { exact: true }).fill("Środowisko testowe");
    await page.getByRole("button", { name: "Zapisz", exact: true }).click();
    await expect(
      page.getByRole("cell", { name: "Środowisko testowe", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Dodaj grupę" }).click();
    await page.getByLabel("Nazwa", { exact: true }).fill("Usługi aplikacji");
    await page
      .getByRole("combobox", { name: "Grupa nadrzędna", exact: true })
      .selectOption({ label: "Środowisko testowe" });
    await page.getByRole("button", { name: "Zapisz", exact: true }).click();
    await expect(
      page.getByRole("cell", { name: "Usługi aplikacji", exact: true }),
    ).toBeVisible();
    await capture(page, "03-grupy");
    await page.getByRole("link", { name: "Tagi", exact: true }).click();
    await page.getByRole("button", { name: "Dodaj tag" }).click();
    await page.getByLabel("Nazwa", { exact: true }).fill("ci");
    await page.getByRole("button", { name: "Zapisz", exact: true }).click();
    await expect(
      page.getByRole("cell", { name: "ci", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("link", { name: "Urządzenia i serwery", exact: true })
      .click();
    await page.getByRole("button", { name: "Dodaj urządzenie" }).click();
    await page
      .getByLabel("Nazwa", { exact: true })
      .fill("Instalacja testowa MONIVEX");
    const resourceForm = page.locator("section.editor-card");
    await resourceForm
      .getByRole("combobox", { name: "Grupa", exact: true })
      .selectOption({ label: "Środowisko testowe / Usługi aplikacji" });
    await resourceForm
      .getByRole("listbox", { name: /Tagi/ })
      .selectOption({ label: "ci" });
    await resourceForm.getByLabel("System operacyjny").fill("Linux");
    await resourceForm
      .getByLabel("Środowisko", { exact: true })
      .fill("testowe");
    await page.getByRole("button", { name: "Zapisz", exact: true }).click();
    await expect(
      page.getByRole("cell").filter({
        has: page.getByText("Instalacja testowa MONIVEX", { exact: true }),
      }),
    ).toBeVisible();
    await capture(page, "04-urzadzenia");
    await page
      .getByRole("link", { name: "Monitory", exact: true })
      .first()
      .click();
    let row = page.getByRole("row").filter({ hasText: "Heartbeat testowy" });
    await row.getByRole("button", { name: "Edytuj" }).click();
    const links = page.getByRole("group", { name: "Powiązania", exact: true });
    await links
      .getByRole("combobox", { name: "Urządzenie / serwer", exact: true })
      .selectOption({ label: "Instalacja testowa MONIVEX" });
    await links
      .getByRole("listbox", { name: /Tagi/ })
      .selectOption({ label: "ci" });
    await capture(page, "05-konfigurator");
    await page.getByRole("button", { name: "Zapisz monitor" }).click();
    await expect(
      page.getByRole("heading", { name: "Edytuj monitor" }),
    ).not.toBeVisible();
    row = page.getByRole("row").filter({ hasText: "Heartbeat testowy" });
    await row.getByRole("button", { name: "Duplikuj", exact: true }).click();
    const dialog = page.getByRole("alertdialog");
    await dialog.getByLabel("Nazwa monitora").fill("Heartbeat pomocniczy");
    await dialog.getByRole("button", { name: "Duplikuj", exact: true }).click();
    await expect(page.getByRole("alertdialog")).not.toBeVisible();
    await page.getByRole("button", { name: "Ukryj token" }).click();
    await page
      .getByRole("checkbox", { name: "Zaznacz monitory na tej stronie" })
      .check();
    await page.getByRole("button", { name: "Zmień zaznaczone" }).click();
    const bulk = page
      .locator("section.editor-card")
      .filter({ has: page.getByRole("heading", { name: "Zmień zaznaczone" }) });
    await bulk
      .getByRole("combobox", { name: "Priorytet", exact: true })
      .selectOption("high");
    await page.getByRole("button", { name: "Zastosuj zmiany" }).click();
    await expect(
      page.getByText("Zapisano zmiany dla zaznaczonych monitorów."),
    ).toBeVisible();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "Heartbeat pomocniczy" })
        .getByText("Wysoki", { exact: true }),
    ).toBeVisible();
    await capture(page, "06-monitory");
    const copy = page
      .getByRole("row")
      .filter({ hasText: "Heartbeat pomocniczy" });
    await copy.getByRole("button", { name: "Usuń", exact: true }).click();
    await page
      .getByRole("alertdialog")
      .getByRole("button", { name: "Usuń", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "Heartbeat pomocniczy" }),
    ).not.toBeVisible();
    await page
      .getByRole("link", { name: "Urządzenia i serwery", exact: true })
      .click();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "Instalacja testowa MONIVEX" })
        .getByRole("link", { name: /1 · Pokaż monitory/ }),
    ).toBeVisible();
    await capture(page, "07-urzadzenie-z-monitorem");
    await page.getByRole("link", { name: "Przegląd", exact: true }).click();
    await page.getByLabel("Motyw").selectOption("dark");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "Heartbeat testowy" })
        .getByText("Działa", { exact: true }),
    ).toBeVisible();
    await expect(
      page
        .locator(".stats article")
        .filter({ hasText: "Działające" })
        .locator("strong"),
    ).toHaveText("1");
    await capture(page, "08-pulpit-ciemny");
    await page.getByLabel("Motyw").selectOption("light");
    await capture(page, "09-pulpit-jasny");
  }
  await securityFlow(page, password + "changed");
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, "10-mobilny");
  await page.getByRole("button", { name: "Zwiń lub rozwiń menu" }).click();
  await expect(
    page.getByRole("link", { name: "Ustawienia", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Wyloguj", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się" }),
  ).toBeVisible();
  // Only explicitly captured evidence is uploaded; credentials are masked, traces disabled.
});
