"use client";

import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

const KEY = "hidden-oasis-sidebar-collapsed";

export function SidebarToggle() {
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    const stored = window.localStorage.getItem(KEY);
    const mobile = window.matchMedia("(max-width: 980px)").matches;
    const next = stored == null ? mobile : stored === "1";
    setCollapsed(next);
    document.documentElement.dataset.sidebar = next ? "collapsed" : "expanded";
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
