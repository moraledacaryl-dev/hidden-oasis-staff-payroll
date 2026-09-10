"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="page"><section className="card" role="alert"><h1>This page could not be loaded</h1><p>Please try again. If the problem continues, return to your workspace and contact an administrator.</p><div className="action-row"><button className="button" type="button" onClick={reset}>Try again</button><button className="button secondary" type="button" onClick={() => window.history.back()}>Go back</button></div></section></main>;
}
