import { useState } from 'react'
import { Trash2, MessageSquare, Pencil, Check, X } from 'lucide-react'

export default function SidebarSessions({
  sesiones,
  sessionIdActivo,
  onCambiarSesion,
  onBorrarSesion,
  onRenombrarSesion,
}) {
  const [editandoId, setEditandoId] = useState(null)
  const [editTitulo, setEditTitulo] = useState('')

  const formatearFecha = (iso) => {
    if (!iso) return ''
    const fecha = new Date(iso)
    const ahora = new Date()
    const diff = ahora - fecha
    const minutos = Math.floor(diff / 60000)
    const horas = Math.floor(diff / 3600000)
    const dias = Math.floor(diff / 86400000)

    if (minutos < 1) return 'Ahora'
    if (minutos < 60) return `hace ${minutos}m`
    if (horas < 24) return `hace ${horas}h`
    if (dias < 7) return `hace ${dias}d`
    return fecha.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
  }

  const startRename = (e, sesion) => {
    e.stopPropagation()
    setEditandoId(sesion.session_id)
    setEditTitulo(sesion.titulo)
  }

  const confirmRename = (e) => {
    e.stopPropagation()
    if (editTitulo.trim() && onRenombrarSesion) {
      onRenombrarSesion(editandoId, editTitulo.trim())
    }
    setEditandoId(null)
  }

  const cancelRename = (e) => {
    e.stopPropagation()
    setEditandoId(null)
  }

  if (sesiones.length === 0) {
    return (
      <div className="sidebar-sessions__empty">
        <MessageSquare size={14} />
        <span>Sin conversaciones</span>
      </div>
    )
  }

  return (
    <div className="sidebar-sessions__list">
      {sesiones.map((sesion) => {
        const esActiva = sesion.session_id === sessionIdActivo
        const esEditando = sesion.session_id === editandoId

        return (
          <div
            key={sesion.session_id}
            className={`sidebar-sessions__item ${esActiva ? 'sidebar-sessions__item--active' : ''}`}
            onClick={() => !esEditando && onCambiarSesion(sesion.session_id)}
          >
            <div className="sidebar-sessions__item-content">
              {esEditando ? (
                <div className="sidebar-sessions__rename" onClick={(e) => e.stopPropagation()}>
                  <input
                    className="sidebar-sessions__rename-input"
                    value={editTitulo}
                    onChange={(e) => setEditTitulo(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') confirmRename(e)
                      if (e.key === 'Escape') cancelRename(e)
                    }}
                    autoFocus
                  />
                  <button className="sidebar-sessions__rename-ok" onClick={confirmRename}>
                    <Check size={12} />
                  </button>
                  <button className="sidebar-sessions__rename-cancel" onClick={cancelRename}>
                    <X size={12} />
                  </button>
                </div>
              ) : (
                <>
                  <span className="sidebar-sessions__item-titulo" title={sesion.titulo}>
                    {sesion.titulo}
                  </span>
                  <span className="sidebar-sessions__item-fecha">
                    {formatearFecha(sesion.actualizada_en)}
                  </span>
                </>
              )}
            </div>

            {!esEditando && (
              <div className="sidebar-sessions__item-actions">
                <button
                  className="sidebar-sessions__item-btn"
                  onClick={(e) => startRename(e, sesion)}
                  title="Renombrar"
                >
                  <Pencil size={12} />
                </button>
                <button
                  className="sidebar-sessions__item-btn sidebar-sessions__item-btn--delete"
                  onClick={(e) => {
                    e.stopPropagation()
                    onBorrarSesion(sesion.session_id)
                  }}
                  title="Eliminar conversación"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
