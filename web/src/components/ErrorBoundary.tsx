import { Component, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Shows a readable message instead of a blank page if a screen crashes. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="progress-wrap">
        <div className="card progress-card" role="alert">
          <span className="chip rejected" style={{ justifySelf: "start" }}>Something broke</span>
          <h1>This screen hit an error</h1>
          <p className="muted">{this.state.error.message}</p>
          <button className="btn" onClick={() => window.location.reload()}>Reload the page</button>
        </div>
      </div>
    );
  }
}
