import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";
import "./i18n";
Object.defineProperty(window, "matchMedia", {
  value: vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })),
});
