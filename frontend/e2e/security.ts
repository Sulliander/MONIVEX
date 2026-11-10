import { expect, type Page } from "@playwright/test";
import { createHmac } from "node:crypto";
import { capture } from "./evidence";

function totp(secret: string, offset = 0) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...secret.replace(/=+$/, "")]
    .map((c) => alphabet.indexOf(c).toString(2).padStart(5, "0"))
    .join("");
  const bytes = Buffer.from(
    (bits.match(/.{8}/g) || []).map((b) => parseInt(b, 2)),
  );
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000) + offset));
  const mac = createHmac("sha1", bytes).update(counter).digest();
  const start = mac[mac.length - 1] & 15;
  return String((mac.readUInt32BE(start) & 0x7fffffff) % 1000000).padStart(
    6,
    "0",
  );
}
export async function securityFlow(page: Page, password: string) {
  const origin = new URL(page.url()).origin;
  await page.getByRole("link", { name: "Ustawienia", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Bezpieczeństwo konta" }),
  ).toBeVisible();
  await expect(page.getByText("2FA wyłączone", { exact: true })).toBeVisible();
  await capture(page, "11-bezpieczenstwo-konta");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await capture(page, "18-konto-mobilne");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("button", { name: "Skonfiguruj 2FA", exact: true })
    .click();
  const action = page.locator(".account-action");
  await action.getByLabel("Hasło do potwierdzenia").fill(password);
  await action
    .getByRole("button", { name: "Skonfiguruj 2FA", exact: true })
    .click();
  await expect(page.getByAltText("Kod QR konfiguracji 2FA")).toBeVisible();
  const secret = await page
    .getByLabel("Sekret do ręcznego wpisania")
    .inputValue();
  await capture(page, "12-konfiguracja-2fa-bez-sekretow");
  await action.getByLabel("Kod potwierdzający").fill(totp(secret));
  await action.getByRole("button", { name: "Potwierdź i włącz 2FA" }).click();
  const codesRegion = page.getByRole("region", {
    name: "Nowe kody odzyskiwania",
  });
  await expect(codesRegion).toBeVisible();
  const codes = await codesRegion.locator("code").allTextContents();
  expect(codes).toHaveLength(10);
  await capture(page, "13-kody-odzyskiwania-zamaskowane");
  const downloaded = page.waitForEvent("download");
  await codesRegion.getByRole("button", { name: "Pobierz kody" }).click();
  expect((await downloaded).suggestedFilename()).toBe(
    "monivex-kody-odzyskiwania.txt",
  );
  await codesRegion
    .getByLabel("Kody są zapisane w bezpiecznym miejscu")
    .check();
  await codesRegion
    .getByRole("button", { name: "Ukryj kody odzyskiwania" })
    .click();
  await expect(page.getByText("2FA aktywne", { exact: true })).toBeVisible();

  // A second real browser context, authenticated with a new TOTP interval.
  const otherContext = await page
    .context()
    .browser()!
    .newContext({ baseURL: origin });
  const other = await otherContext.newPage();
  await other.goto("/");
  await other.getByLabel("Nazwa użytkownika").fill("owner");
  await other.getByLabel("Hasło", { exact: true }).fill(password);
  await other.getByRole("button", { name: "Zaloguj się", exact: true }).click();
  await expect(
    other.getByRole("heading", { name: "Potwierdź swoją tożsamość" }),
  ).toBeVisible();
  const usedTotp = totp(secret, 1);
  await other.getByLabel("Kod z aplikacji").fill(usedTotp);
  await other.getByRole("button", { name: "Potwierdź logowanie" }).click();
  await expect(
    other.getByRole("heading", { name: "Przegląd", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator(".session-row")).toHaveCount(2);
  await capture(page, "14-aktywne-sesje");
  await page
    .locator(".session-row")
    .filter({ hasText: "Inne urządzenie" })
    .getByRole("button", { name: "Zakończ sesję" })
    .click();
  await page.getByRole("button", { name: "Potwierdź wylogowanie" }).click();
  await expect(page.locator(".session-row")).toHaveCount(1);
  await other.reload();
  await expect(
    other.getByRole("heading", { name: "Zaloguj się", exact: true }),
  ).toBeVisible();
  await otherContext.close();

  await page.getByRole("button", { name: "Wyloguj", exact: true }).click();
  async function firstStep(value = password) {
    await page.getByLabel("Nazwa użytkownika").fill("owner");
    await page.getByLabel("Hasło", { exact: true }).fill(value);
    await page
      .getByRole("button", { name: "Zaloguj się", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Potwierdź swoją tożsamość" }),
    ).toBeVisible();
    const response = await page.request.get("/api/auth/me");
    expect(response.status()).toBe(401); // Password alone never gets a full session.
  }
  async function recover(code: string) {
    await page
      .getByRole("button", { name: "Użyj kodu odzyskiwania", exact: true })
      .click();
    await page.getByLabel("Kod odzyskiwania", { exact: true }).fill(code);
    await page.getByRole("button", { name: "Potwierdź logowanie" }).click();
    await expect(
      page.getByRole("heading", { name: "Przegląd", exact: true }),
    ).toBeVisible();
  }
  await firstStep();
  await capture(page, "15-drugi-etap-logowania");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await capture(page, "19-logowanie-2fa-mobilne");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel("Kod z aplikacji").fill(usedTotp);
  await page.getByRole("button", { name: "Potwierdź logowanie" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Nieprawidłowy lub już użyty kod",
  );
  await recover(codes[0]);
  await page.getByRole("link", { name: "Ustawienia", exact: true }).click();
  await expect(page.getByText("Pozostałe kody odzyskiwania:")).toContainText(
    "9",
  );
  await page.getByRole("button", { name: "Odnów kody odzyskiwania" }).click();
  await action.getByLabel("Hasło do potwierdzenia").fill(password);
  await action.getByLabel("Kod potwierdzający").fill(codes[1]);
  await action
    .getByRole("button", { name: "Wygeneruj nowe kody odzyskiwania" })
    .click();
  await expect(codesRegion).toBeVisible();
  const renewed = await codesRegion.locator("code").allTextContents();
  expect(renewed).toHaveLength(10);
  expect(renewed.some((c) => codes.includes(c))).toBe(false);
  await codesRegion
    .getByLabel("Kody są zapisane w bezpiecznym miejscu")
    .check();
  await codesRegion
    .getByRole("button", { name: "Ukryj kody odzyskiwania" })
    .click();
  await page.getByRole("button", { name: "Wyloguj", exact: true }).click();
  await firstStep();
  await page
    .getByRole("button", { name: "Użyj kodu odzyskiwania", exact: true })
    .click();
  await page.getByLabel("Kod odzyskiwania", { exact: true }).fill(codes[2]);
  await page.getByRole("button", { name: "Potwierdź logowanie" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Nieprawidłowy lub już użyty kod",
  );
  await page.getByLabel("Kod odzyskiwania", { exact: true }).fill(renewed[0]);
  await page.getByRole("button", { name: "Potwierdź logowanie" }).click();
  await expect(
    page.getByRole("heading", { name: "Przegląd", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Ustawienia", exact: true }).click();
  async function confirm(label: string, code: string) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await action.getByLabel("Hasło do potwierdzenia").fill(password);
    await action.getByLabel("Kod potwierdzający").fill(code);
    await action.getByRole("button", { name: label, exact: true }).click();
  }
  await confirm("Wymagaj 2FA od administratorów", renewed[1]);
  await expect(
    page.getByText("Wymaganie 2FA dla właściciela i administratorów:"),
  ).toContainText("włączone");
  await confirm("Wyłącz 2FA", renewed[2]);
  await expect(page.getByRole("alert")).toContainText("Instalacja wymaga 2FA");
  await action.getByRole("button", { name: "Anuluj" }).click();
  await confirm("Wyłącz wymóg 2FA administratorów", renewed[2]);
  await expect(
    page.getByText("Wymaganie 2FA dla właściciela i administratorów:"),
  ).toContainText("wyłączone");
  const updated = password + "-secured";
  await page.getByLabel("Obecne hasło", { exact: true }).fill(password);
  await page.getByLabel("Nowe hasło", { exact: true }).fill(updated);
  await page.getByLabel("Powtórz nowe hasło").fill(updated);
  await page
    .getByLabel("Kod uwierzytelniający do zmiany hasła")
    .fill(renewed[3]);
  await page
    .getByRole("button", { name: "Zmień hasło i zakończ sesje" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się", exact: true }),
  ).toBeVisible();
  await firstStep(updated);
  await recover(renewed[4]);
  password = updated;
  await page.getByRole("link", { name: "Ustawienia", exact: true }).click();
  await confirm("Wyłącz 2FA", renewed[5]);
  await expect(page.getByText("2FA wyłączone", { exact: true })).toBeVisible();
  await expect(page.getByText("Wyłączono 2FA", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Starsze zdarzenia", exact: true })
    .click();
  await expect(page.getByText("Włączono 2FA", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Najnowsze zdarzenia", exact: true })
    .click();
  await expect(page.getByText("Wyłączono 2FA", { exact: true })).toBeVisible();
  await capture(page, "16-dziennik-bezpieczenstwa");
  // New tab must recover its CSRF token while retaining the existing session.
  const tab = await page.context().newPage();
  await tab.goto("/settings");
  await expect(
    tab.getByRole("heading", { name: "Bezpieczeństwo konta" }),
  ).toBeVisible();
  await tab
    .getByRole("button", { name: "Wyloguj wszystkie urządzenia" })
    .click();
  await tab.getByRole("button", { name: "Potwierdź wylogowanie" }).click();
  await expect(
    tab.getByRole("heading", { name: "Zaloguj się", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Przegląd", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Zaloguj się", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText("Sesja wygasła");
  await capture(page, "17-sesja-zakonczona");
  await tab.close();
  await page.getByLabel("Nazwa użytkownika").fill("owner");
  await page.getByLabel("Hasło", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Zaloguj się", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Przegląd", exact: true }),
  ).toBeVisible();
}
