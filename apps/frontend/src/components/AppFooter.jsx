import { PapiGlyph } from './PapiGlyph'

// Graphite ops panel in both themes (the partner logo artwork is white, and a
// constant dark band anchors the page bottom regardless of theme). The
// certification notice is a contractual honesty requirement — it must stay
// visible in every redesign.
export function AppFooter({ copy, onManageCookies }) {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <div className="footer-brand">
          <span className="footer-mark">
            <PapiGlyph />
            <strong>PAPI Vision</strong>
          </span>
          <p>{copy.footer.description}</p>
          <img
            className="footer-partner-logo"
            src="/intersoft-electronics-logo-white-inverse.svg"
            alt={copy.brand.company}
          />
        </div>
        <div className="footer-column">
          <h2>{copy.footer.project}</h2>
          <p>{copy.footer.notice}</p>
        </div>
        <div className="footer-column footer-partners">
          <span>{copy.footer.academic}</span>
          <span>{copy.footer.partner}</span>
        </div>
      </div>
      <div className="footer-legal">
        <span>{copy.footer.copyright}</span>
        <span>Howest University × Intersoft Electronics Services BV</span>
        {onManageCookies && (
          <button type="button" className="footer-legal__link" onClick={onManageCookies}>
            {copy.cookie.manage}
          </button>
        )}
      </div>
    </footer>
  )
}
