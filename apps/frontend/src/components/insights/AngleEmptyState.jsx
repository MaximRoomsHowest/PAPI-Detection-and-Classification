// Shared honest empty-state for charts that have no real data yet. Used in
// place of any synthetic/illustrative fallback so a panel is never mistaken for
// live model output.
export function AngleEmptyState({ icon, title, message }) {
  return (
    <div className="chart-empty" role="status">
      {icon}
      {title ? <strong>{title}</strong> : null}
      <p>{message}</p>
    </div>
  )
}
