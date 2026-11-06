import { createContext, useContext } from "react";
export const TimezoneContext = createContext("UTC");
export function useDateFormatter() {
  const timezone = useContext(TimezoneContext);
  return (timestamp: number) =>
    new Date(timestamp * 1000).toLocaleString("pl-PL", { timeZone: timezone });
}
