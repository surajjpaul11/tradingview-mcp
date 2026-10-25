const STATUS_LABELS = {
  stale: 'Cached · updating',
  loading: 'Loading…',
  live: 'Live',
  error: 'Error',
};

function StatusBadge({ status }) {
  return (
    <span className="status-badge" data-status={status.state} title={status.message}>
      {STATUS_LABELS[status.state]}
    </span>
  );
}

export default StatusBadge;
