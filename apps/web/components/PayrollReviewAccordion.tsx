"use client";

import { createContext, useContext, useState } from "react";

const PayrollReviewAccordionContext = createContext<{
  openId: string | null;
  setOpenId: (id: string | null) => void;
} | null>(null);

export function PayrollReviewAccordion({ children }: { children: React.ReactNode }) {
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <PayrollReviewAccordionContext.Provider value={{ openId, setOpenId }}>
      {children}
    </PayrollReviewAccordionContext.Provider>
  );
}

export function usePayrollReviewAccordion() {
  return useContext(PayrollReviewAccordionContext);
}

export function ReviewAccordionDetails({
  id,
  className,
  children,
}: {
  id: string;
  className?: string;
  children: React.ReactNode;
}) {
  const context = usePayrollReviewAccordion();

  if (!context) {
    return <details className={className}>{children}</details>;
  }

  const open = context.openId === id;

  return (
    <details
      className={className}
      open={open}
      onToggle={(event) => {
        if (event.currentTarget.open) {
          context.setOpenId(id);
        } else if (context.openId === id) {
          context.setOpenId(null);
        }
      }}
    >
      {children}
    </details>
  );
}
