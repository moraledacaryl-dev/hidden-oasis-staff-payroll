import type { Metadata } from "next";
import "./globals.css";
import "./auth.css";
import "./print-payslips.css";
import "./responsive-quality.css";

export const metadata: Metadata = {
  title: "Hidden Oasis Staff Payroll",
  description: "Hidden Oasis staff and payroll system.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
