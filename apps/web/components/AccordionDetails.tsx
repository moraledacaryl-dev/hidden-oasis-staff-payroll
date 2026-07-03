"use client";

import { createContext, useContext, useState } from "react";

const AccordionContext = createContext<{
  openId: string | null;
  setOpenId: (id: string | null) => void;
} | null>(null);

export function AccordionGroup({ children, defaultOpenId = null }: {
  children: React.ReactNode;
  defaultOpenId?: string | null;
}) {
  const [openId, setOpenId] = useState<string | null>(defaultOpenId);
  return (
    <AccordionContext.Provider value={{ openId, setOpenId }}>
      {children}
    </AccordionContext.Provider>
  );
}

export function AccordionDetails({
  id,
  className,
  children,
}: {
  id: string;
  className?: string;
  children: React.ReactNode;
}) {
  const context = useContext(AccordionContext);

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
