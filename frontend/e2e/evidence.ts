import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import type { Page } from "@playwright/test";
export async function capture(page: Page, name: string) {
  if (process.env.MONIVEX_SCREENSHOTS !== "1") return;
  const directory = join(process.cwd(), "artifacts", "screenshots");
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: join(directory, name + ".png"),
    fullPage: true,
    animations: "disabled",
    mask: [
      page.locator("[data-private]"),
      page.locator('input[type="password"]'),
      page.locator('textarea[name="body"]'),
    ],
    maskColor: "#334155",
  });
}
