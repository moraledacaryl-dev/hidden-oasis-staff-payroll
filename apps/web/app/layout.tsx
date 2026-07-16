import type { Metadata } from "next";
import { CutoffReviewWheelBridge } from "@/components/CutoffReviewWheelBridge";
import { SidebarScrollMemory } from "@/components/SidebarScrollMemory";
import { ViewportScrollRecovery } from "@/components/ViewportScrollRecovery";
import "./globals.css";
import "./auth.css";
import "./print-payslips.css";
import "./responsive-quality.css";
import "./cutoff-review.css";
import "./pass1-theme.css";
import "./prototype-foundation.css";
import "./pass1-surfaces.css";
import "./schedule-drawer.css";
import "./schedule-ux-fixes.css";
import "./core-operations.css";
import "./pass3-people.css";
import "./payroll-workflow.css";
import "./payroll-run-pass4.css";
import "./pass5-system.css";
import "./staff-portal.css";
import "./pass7-integration.css";

export const metadata: Metadata = {
  title: "Hidden Oasis Staff Payroll",
  description: "Hidden Oasis staff and payroll system.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><SidebarScrollMemory /><ViewportScrollRecovery /><CutoffReviewWheelBridge />{children}</body>
    </html>
  );
}
