"use client";

import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

const KEY = "hidden-oasis-sidebar-collapsed";

export function SidebarToggle() {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(KEY) === "1";
    setCollapsed(stored);
    document.documentElement.dataset.sidebar = stored ? "collapsed" : "expanded";
  }, []);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    window.localStorage.setItem(KEY, next ? "1" : "0");
    document.documentElement.dataset.sidebar = next ? "collapsed" : "expanded";
  }

  return (
    <button className="sidebar-toggle" type="button" onClick={toggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
      {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
    </button>
  );
}
