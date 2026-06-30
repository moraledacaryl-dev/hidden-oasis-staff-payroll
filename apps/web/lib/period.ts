function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function todayInManilaIso(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export type PayrollCutoff = {
  month: string;
  half: "first" | "second";
  periodStart: string;
  periodEnd: string;
  payoutDate: string;
};

export function payrollCutoffForMonth(month: string, half: "first" | "second"): PayrollCutoff | null {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return null;
  const year = Number(match[1]);
  const monthNumber = Number(match[2]);
  if (monthNumber < 1 || monthNumber > 12) return null;
  const lastDay = daysInMonth(year, monthNumber);
  const startDay = half === "first" ? 1 : 16;
  const endDay = half === "first" ? 15 : lastDay;
  return {
    month,
    half,
    periodStart: `${month}-${pad(startDay)}`,
    periodEnd: `${month}-${pad(endDay)}`,
    payoutDate: `${month}-${pad(endDay)}`,
  };
}

export function latestCompletedCutoff(today = todayInManilaIso()): PayrollCutoff {
  const [year, month, day] = today.split("-").map(Number);
  if (day >= 16) {
    return payrollCutoffForMonth(`${year}-${pad(month)}`, "first") as PayrollCutoff;
  }
  const previous = new Date(Date.UTC(year, month - 2, 1));
  return payrollCutoffForMonth(
    `${previous.getUTCFullYear()}-${pad(previous.getUTCMonth() + 1)}`,
    "second",
  ) as PayrollCutoff;
}

export function isCompletedCutoff(cutoff: PayrollCutoff, today = todayInManilaIso()): boolean {
  return cutoff.periodEnd < today;
}

export function addIsoDays(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

export function formatIsoDay(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-PH", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function currentCutoff(today = todayInManilaIso()) {
  const [year, month, day] = today.split("-").map(Number);
  const endDay = day <= 15 ? 15 : daysInMonth(year, month);
  const startDay = day <= 15 ? 1 : 16;
  return {
    periodStart: `${year}-${pad(month)}-${pad(startDay)}`,
    periodEnd: `${year}-${pad(month)}-${pad(endDay)}`,
    payoutDate: `${year}-${pad(month)}-${pad(endDay)}`,
  };
}

export function mondayOfWeek(today = todayInManilaIso()): string {
  const [year, month, day] = today.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const weekDay = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() - weekDay + 1);
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}
