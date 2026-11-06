import { expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { TimezoneContext, useDateFormatter } from "./dates";
function DateView({ timestamp }: { timestamp: number }) {
  const format = useDateFormatter();
  return <output>{format(timestamp)}</output>;
}
test("daty respektują strefę instalacji i zmianę czasu zimowego na letni", () => {
  const winter = Date.parse("2026-01-15T12:00:00Z") / 1000;
  const summer = Date.parse("2026-07-15T12:00:00Z") / 1000;
  const { rerender } = render(
    <TimezoneContext.Provider value="UTC">
      <DateView timestamp={winter} />
    </TimezoneContext.Provider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("12:00:00");
  rerender(
    <TimezoneContext.Provider value="Europe/Warsaw">
      <DateView timestamp={winter} />
    </TimezoneContext.Provider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("13:00:00");
  rerender(
    <TimezoneContext.Provider value="Europe/Warsaw">
      <DateView timestamp={summer} />
    </TimezoneContext.Provider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("14:00:00");
  cleanup();
});
