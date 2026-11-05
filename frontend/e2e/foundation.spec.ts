import { test, expect } from "@playwright/test";
import { randomBytes } from "node:crypto";
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
  await login(password);
  await expect(page.getByRole("heading", { name: "Przegląd" })).toBeVisible();
  await expect(page.getByText("Silnik monitoringu")).toBeVisible();
  await page.getByLabel("Motyw").selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Przegląd" })).toBeVisible();
  await page.getByRole("link", { name: "Ustawienia", exact: true }).click();
  await page.getByLabel("Obecne hasło").fill(password);
  await page.getByLabel("Nowe hasło").fill(password + "changed");
  await page
    .getByRole("button", { name: "Zmień hasło i zakończ sesje" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się" }),
  ).toBeVisible();
  await login(password + "changed");
  await expect(page.getByRole("heading", { name: "Przegląd" })).toBeVisible();
  if (process.env.MONIVEX_TEST_WORKER === "1") {
    await page
      .getByRole("link", { name: "Monitory", exact: true })
      .first()
      .click();
    await page.getByRole("button", { name: "Dodaj monitor" }).click();
    await page.getByLabel("Nazwa monitora").fill("Heartbeat testowy");
    await page.getByRole("combobox", { name: "Typ", exact: true }).selectOption("heartbeat");
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
    const list = await request.get("/api/monitors");
    expect(list.status()).toBe(401);
    await page.getByRole("button", { name: "Ukryj token" }).click();
    const row = page.getByRole("row").filter({ hasText: "Heartbeat testowy" });
    await expect(row.getByText("Działa", { exact: true })).toBeVisible();
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
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Zwiń lub rozwiń menu" }).click();
  await expect(
    page.getByRole("link", { name: "Ustawienia", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Wyloguj", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się" }),
  ).toBeVisible();
  // No screenshots or traces: they could retain setup secrets and passwords.
});
