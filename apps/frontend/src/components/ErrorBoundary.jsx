import { Component } from 'react'

// Last-resort boundary: a render error in any page would otherwise blank the
// whole app (white screen) with nothing actionable. This catches it and shows a
// minimal recover-by-reload fallback. Kept standalone (no i18n/theme deps) so it
// still renders even if one of those is what failed.
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    // Surface to the console for diagnosis; a deployment would forward this to an
    // error tracker.
    console.error('Unhandled UI error:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" style={{ padding: '48px 24px', textAlign: 'center', fontFamily: 'inherit' }}>
          <h1 style={{ marginBottom: 8 }}>Something went wrong</h1>
          <p style={{ marginBottom: 20, opacity: 0.8 }}>
            The interface hit an unexpected error. Reloading usually clears it.
          </p>
          <button className="cta-button" type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
