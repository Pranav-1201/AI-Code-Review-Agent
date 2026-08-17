import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time throws below it and shows a recoverable fallback.
 *
 * Mounted INSIDE DashboardLayout, wrapping <Routes> — not at the root. That
 * placement is the point: at the root, one page's throw takes the sidebar and
 * header with it and the user's only recourse is the browser back button. Here,
 * the chrome survives and the user can navigate away from the broken page.
 *
 * React offers no hook equivalent, so this stays a class component.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="max-w-xl mx-auto mt-12 rounded-lg border border-destructive/40 bg-destructive/10 p-6 space-y-4"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-destructive shrink-0" aria-hidden="true" />
          <h2 className="text-lg font-semibold">This page hit an error</h2>
        </div>

        <p className="text-sm text-muted-foreground">
          The rest of the app is still working — use the sidebar to go somewhere else,
          or try rendering this page again.
        </p>

        <p className="font-mono text-xs break-words opacity-80">{error.message}</p>

        <div className="flex gap-3">
          <Button onClick={this.handleReset}>Try again</Button>
          <Button variant="outline" asChild>
            <a href="/">Back to scanner</a>
          </Button>
        </div>
      </div>
    );
  }
}
