export function InlineMetric({ label, value, suffix }) {
  return (
    <div className="inline-metric">
      <span>{label}</span>
      <strong>
        {value}
        <small>{suffix}</small>
      </strong>
    </div>
  )
}
