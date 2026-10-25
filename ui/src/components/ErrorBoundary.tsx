import { Component, type ErrorInfo, type ReactNode } from 'react';

/** One bad answer from the core must not blank the whole app during a demo. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Screen crashed', error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto max-w-page px-6 pt-16 md:px-12 lg:px-14">
        <div className="text-eyebrow font-semibold uppercase text-ink3">This screen hit a problem</div>
        <h1 className="mt-4 text-hero font-semibold text-ink">Something in the answer didn't fit.</h1>
        <p className="mt-4 max-w-2xl text-xl text-ink2">The rest of the app still works. Pick another screen, or reload this one.</p>
        <pre className="mt-6 max-w-3xl overflow-x-auto rounded-xl bg-rail px-4 py-3 text-[0.8125rem] text-ink2">{this.state.error.message}</pre>
        <button type="button" onClick={() => this.setState({ error: null })} className="mt-6 rounded-xl bg-accent px-5 py-2.5 font-semibold text-white">
          Try again
        </button>
      </div>
    );
  }
}
