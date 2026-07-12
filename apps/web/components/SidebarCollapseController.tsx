"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "hidden-oasis-sidebar-collapsed";

export function SidebarCollapseController() {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY) === "1";
    setCollapsed(saved);
    document.documentElement.toggleAttribute("data-sidebar-collapsed", saved);
    return () => document.documentElement.removeAttribute("data-sidebar-collapsed");
  }, []);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    document.documentElement.toggleAttribute("data-sidebar-collapsed", next);
  }

  return (
    <button
      aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      aria-pressed={collapsed}
      className="sidebar-collapse-control"
      onClick={toggle}
      title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      type="button"
    >
      <span aria-hidden="true">{collapsed ? "›" : "‹"}</span>
    </button>
  );
}
