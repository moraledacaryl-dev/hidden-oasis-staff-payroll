import type { Metadata } from "next";
import { ScheduleAddShiftBridge } from "@/components/ScheduleAddShiftBridge";
import "./globals.css";
import "./auth.css";
import "./print-payslips.css";
import "./responsive-quality.css";
import "./cutoff-review.css";
import "./pass1-theme.css";
import "./prototype-foundation.css";
import "./pass1-surfaces.css";
import "./schedule-drawer.css";

export const metadata: Metadata = {
  title: "Hidden Oasis Staff Payroll",
  description: "Hidden Oasis staff and payroll system.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><ScheduleAddShiftBridge />{children}</body>
    </html>
  );
}
