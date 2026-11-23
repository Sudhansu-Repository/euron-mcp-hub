import {
  FlaskConical,
  KeyRound,
  LayoutDashboard,
  ScrollText,
  Server,
  Settings,
  ShieldCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  /** The path under the app root. */
  href: string;
  label: string;
  icon: LucideIcon;
};

export type NavGroup = { label: string | null; items: NavItem[] };

/** The sidebar, in the order of the dashboard route map. */
export const NAV_GROUPS: NavGroup[] = [
  { label: null, items: [{ href: "/overview", label: "Overview", icon: LayoutDashboard }] },
  {
    label: "Catalog",
    items: [
      { href: "/servers", label: "Servers", icon: Server },
      { href: "/tools", label: "Tools", icon: Wrench },
    ],
  },
  {
    label: "Access",
    items: [
      { href: "/clients", label: "Clients", icon: ShieldCheck },
      { href: "/keys", label: "API keys", icon: KeyRound },
    ],
  },
  {
    label: "Operate",
    items: [
      { href: "/playground", label: "Tool tester", icon: FlaskConical },
      { href: "/calls", label: "Audit log", icon: ScrollText },
    ],
  },
  { label: null, items: [{ href: "/settings", label: "Settings", icon: Settings }] },
];

/** Whether a nav item covers the current path (detail pages keep their section highlighted). */
export function isNavActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
