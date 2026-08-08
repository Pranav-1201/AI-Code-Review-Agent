import React from "react";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full">
        {/* Skip link (WCAG 2.4.1 Bypass Blocks): lets keyboard / screen-reader
            users jump past the sidebar nav straight to page content. Visually
            hidden until it receives focus. */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:text-primary-foreground focus:shadow-lg"
        >
          Skip to main content
        </a>
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-12 flex items-center border-b border-border/50 bg-background/80 backdrop-blur-sm sticky top-0 z-10">
            <SidebarTrigger className="ml-3" />
            <div className="ml-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-primary animate-pulse-glow" aria-hidden="true" />
              <span className="text-xs text-muted-foreground font-mono">SYSTEM ONLINE</span>
            </div>
          </header>
          <main
            id="main-content"
            tabIndex={-1}
            className="flex-1 overflow-auto p-6 focus:outline-none"
          >
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
