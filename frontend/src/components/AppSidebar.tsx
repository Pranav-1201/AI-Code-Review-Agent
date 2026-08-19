import type { LucideIcon } from "lucide-react";
import {
  Search, Shield, FileCode, BarChart3, GitBranch,
  Brain, Heart, History, AlertTriangle, Copy,
  PieChart, Download, Settings, LayoutDashboard,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { ROUTES, SITE_NAME, type NavGroup } from "@/lib/routes";

/**
 * Icons are the one thing the nav owns.
 *
 * The paths, titles and grouping all come from routes.ts, which the Caddyfile,
 * the sitemap generator and the head manager also read. Icons cannot live
 * there: routes.ts must import nothing at all so vite.config.ts can load it in
 * Node at build time, and lucide-react is very much an import.
 */
const ICONS: Record<string, LucideIcon> = {
  "/": Search,
  "/results": LayoutDashboard,
  "/overview": GitBranch,
  "/file-analysis": FileCode,
  "/security": Shield,
  "/quality": BarChart3,
  "/dependencies": GitBranch,
  "/duplicates": Copy,
  "/ai-suggestions": Brain,
  "/health": Heart,
  "/issues": AlertTriangle,
  "/visualizations": PieChart,
  "/history": History,
  "/export": Download,
  "/settings": Settings,
};

/**
 * Group the routes for the nav, preserving first-appearance order for the
 * groups and array order within each — so the order of ROUTES *is* the order
 * of the sidebar.
 */
const groups: { label: NavGroup; items: { url: string; title: string; icon: LucideIcon }[] }[] =
  ROUTES.reduce<{ label: NavGroup; items: { url: string; title: string; icon: LucideIcon }[] }[]>(
    (accumulated, route) => {
      if (!route.navGroup) return accumulated;

      const existing = accumulated.find((group) => group.label === route.navGroup);
      const item = { url: route.path, title: route.title, icon: ICONS[route.path] };

      if (existing) {
        existing.items.push(item);
      } else {
        accumulated.push({ label: route.navGroup, items: [item] });
      }

      return accumulated;
    },
    [],
  );

export function AppSidebar() {
  const { state, isMobile, setOpenMobile } = useSidebar();
  const collapsed = state === "collapsed";

  // Below 768px the sidebar is a Sheet, and nothing closed it on navigation —
  // so tapping a link left the drawer sitting on top of the page it had just
  // navigated to, to be dismissed by hand every time. It also marks the rest of
  // the page aria-hidden while open, which hides the whole app from assistive
  // technology after every tap.
  const handleNavigate = () => {
    if (isMobile) setOpenMobile(false);
  };


  return (
    <Sidebar collapsible="icon">
      <SidebarContent>
        <div className={`p-4 ${collapsed ? "px-2" : ""}`}>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
              <Brain className="w-4 h-4 text-primary" />
            </div>
            {!collapsed && (
              <div>
                <h1 className="text-sm font-bold text-foreground">{SITE_NAME}</h1>
                <p className="text-[10px] text-muted-foreground">Agent Dashboard</p>
              </div>
            )}
          </div>
        </div>

        {groups.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
              {group.label}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild>
                      <NavLink
                        to={item.url}
                        end={item.url === "/"}
                        onClick={handleNavigate}
                        className="hover:bg-sidebar-accent/50 transition-colors"
                        activeClassName="bg-primary/10 text-primary font-medium border-l-2 border-primary"
                      >
                        <item.icon className="mr-2 h-4 w-4 shrink-0" />
                        {!collapsed && <span className="text-sm">{item.title}</span>}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}
