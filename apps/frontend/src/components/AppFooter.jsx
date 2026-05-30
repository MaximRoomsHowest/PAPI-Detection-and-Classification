export function AppFooter({ copy }) {
  return (
    <footer className="site-footer">
      <div className="footer-main">
        <div className="footer-brand">
          <img src="/intersoft-electronics-logo-white-inverse.svg" alt="Intersoft Electronics" />
          <p>{copy.footer.description}</p>
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
      </div>
    </footer>
  )
}
