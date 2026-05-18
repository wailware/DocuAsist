import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  MessageSquare,
  FolderOpen,
  FileText,
  LogOut,
  User,
  Plus,
  Sun,
  Moon,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useChatContext } from '../contexts/ChatContext'
import { useTheme } from '../contexts/ThemeContext'
import SidebarSessions from './SidebarSessions'
import './Layout.css'

const NAV_ITEMS = [
  { to: '/', icon: MessageSquare, label: 'Chat' },
  { to: '/documentos', icon: FolderOpen, label: 'Documentos' },
]

export default function Layout() {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const location = useLocation()
  const isChat = location.pathname === '/'

  const {
    sesiones,
    sessionId,
    nuevaSesion,
    cambiarSesion,
    borrarSesion,
    renombrarSesion,
  } = useChatContext()

  return (
    <div className="layout">
      <aside className="sidebar">
        {/* Logo */}
        <div className="sidebar__logo">
          <div className="sidebar__logo-icon">
            <FileText size={20} />
          </div>
          <div className="sidebar__logo-text">
            <span className="sidebar__logo-name">DocuAsist</span>
            <span className="sidebar__logo-tag">Asistente Documental</span>
          </div>
        </div>

        {/* Nueva conversación + lista de sesiones (solo en Chat) */}
        {isChat && (
          <div className="sidebar__sessions">
            <button className="sidebar__new-chat" onClick={nuevaSesion}>
              <Plus size={16} />
              <span>Nueva conversación</span>
            </button>
            <SidebarSessions
              sesiones={sesiones}
              sessionIdActivo={sessionId}
              onCambiarSesion={cambiarSesion}
              onBorrarSesion={borrarSesion}
              onRenombrarSesion={renombrarSesion}
            />
          </div>
        )}

        {/* Navegación */}
        <nav className="sidebar__nav">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Usuario + ajustes */}
        <div className="sidebar__footer">
          {user && (
            <div className="sidebar__user">
              <div className="sidebar__user-info">
                <User size={14} />
                <span className="sidebar__user-name">{user.username}</span>
                <span className="sidebar__user-rol">{user.rol}</span>
              </div>
              <button className="sidebar__theme-toggle" onClick={toggleTheme} title={theme === 'dark' ? 'Modo claro' : 'Modo oscuro'}>
                {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
              </button>
              <button className="sidebar__logout" onClick={logout} title="Cerrar sesión">
                <LogOut size={14} />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Contenido principal */}
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  )
}
