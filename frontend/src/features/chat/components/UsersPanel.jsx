export function UsersPanel({ connected, availableTargets, targetUser, onTargetChange }) {
  return (
    <aside className="panel users">
      <h2>Usuarios</h2>
      <p>{availableTargets.length} disponibles</p>
      <select
        value={targetUser}
        onChange={(e) => onTargetChange(e.target.value)}
        disabled={!connected || !availableTargets.length}
      >
        {availableTargets.length === 0 ? (
          <option value="">No hay usuarios disponibles</option>
        ) : (
          availableTargets.map((user) => (
            <option key={user} value={user}>
              {user}
            </option>
          ))
        )}
      </select>
    </aside>
  )
}
