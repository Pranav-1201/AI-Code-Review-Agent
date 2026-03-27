import {
  Search, Shield, FileCode, BarChart3, GitBranch,
  Brain, Heart, History, AlertTriangle, Copy,
  PieChart, Download, TestTube, Settings, LayoutDashboard,
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

const scanItems = [
  { title: "Repository Scanner", url: "/", icon: Search },
  { title: "Scan Results", url: "/results", icon: LayoutDashboard },
  { title: "Repository Overview", url: "/overview", icon: GitBranch },
];

const analysisItems = [
  { title: "File Analysis", url: "/file-analysis", icon: FileCode },
  { title: "Security Report", url: "/security", icon: Shield },
  { title: "Code Quality", url: "/quality", icon: BarChart3 },
  { title: "Dependencies", url: "/dependencies", icon: GitBranch },
  { title: "Duplicates", url: "/duplicates", icon: Copy },
];

const aiItems = [
  { title: "AI Suggestions", url: "/ai-suggestions", icon: Brain },
  { title: "Health Score", url: "/health", icon: Heart },
  { title: "Issue Explorer", url: "/issues", icon: AlertTriangle },
  { title: "Visualizations", url: "/visualizations", icon: PieChart },
];

const systemItems = [
  { title: "Scan History", url: "/history", icon: History },
  { title: "Export Report", url: "/export", icon: Download },
  { title: "Test Results", url: "/tests", icon: TestTube },
  { title: "Settings", url: "/settings", icon: Settings },
];

const groups = [
  { label: "Scan", items: scanItems },
  { label: "Analysis", items: analysisItems },
  { label: "Insights", items: aiItems },
  { label: "System", items: systemItems },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  

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
                <h1 className="text-sm font-bold text-foreground">AI Code Review</h1>
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
