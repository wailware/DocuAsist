import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { loginUsuario, registrarUsuario } from '../api/client'
import {
  FileText,
  LogIn,
  UserPlus,
  User,
  Mail,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
  ArrowRight,
  Loader,
} from 'lucide-react'
import './Login.css'

export default function Login() {
  const { login } = useAuth()
  const [modo, setModo] = useState('login') // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [cargando, setCargando] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setCargando(true)

    try {
      let data
      if (modo === 'login') {
        data = await loginUsuario(username, password)
      } else {
        data = await registrarUsuario(username, email, password)
      }
      login(data.token, data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="login-page">
      {/* Animated background elements */}
      <div className="login-bg">
        <div className="login-bg__orb login-bg__orb--1" />
        <div className="login-bg__orb login-bg__orb--2" />
        <div className="login-bg__orb login-bg__orb--3" />
        <div className="login-bg__grid" />
      </div>

      <div className="login-card">
        {/* Logo with glow */}
        <div className="login-logo">
          <div className="login-logo__icon">
            <FileText size={26} />
          </div>
          <h1 className="login-logo__name">DocuAsist</h1>
          <p className="login-logo__tag">Asistente Documental Corporativo</p>
        </div>

        {/* Tabs */}
        <div className="login-tabs">
          <button
            className={`login-tab ${modo === 'login' ? 'login-tab--active' : ''}`}
            onClick={() => { setModo('login'); setError(null) }}
          >
            <LogIn size={14} />
            Iniciar sesión
          </button>
          <button
            className={`login-tab ${modo === 'register' ? 'login-tab--active' : ''}`}
            onClick={() => { setModo('register'); setError(null) }}
          >
            <UserPlus size={14} />
            Registrarse
          </button>
        </div>

        {/* Form */}
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field animate-fade-in">
            <label htmlFor="username">Usuario</label>
            <div className="login-field__input-wrap">
              <User size={16} className="login-field__icon" />
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Tu nombre de usuario"
                required
                autoFocus
              />
            </div>
          </div>

          {modo === 'register' && (
            <div className="login-field animate-fade-in" key="email-field">
              <label htmlFor="email">Email</label>
              <div className="login-field__input-wrap">
                <Mail size={16} className="login-field__icon" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@email.com"
                  required
                />
              </div>
            </div>
          )}

          <div className="login-field animate-fade-in">
            <label htmlFor="password">Contraseña</label>
            <div className="login-field__input-wrap">
              <Lock size={16} className="login-field__icon" />
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
              <button
                type="button"
                className="login-field__toggle"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {error && (
            <div className="login-error animate-fade-in">
              <AlertCircle size={14} />
              <span>{error}</span>
            </div>
          )}

          <button className="login-submit" type="submit" disabled={cargando}>
            {cargando ? (
              <>
                <Loader size={16} className="login-submit__spinner" />
                <span>Procesando...</span>
              </>
            ) : (
              <>
                <span>{modo === 'login' ? 'Iniciar sesión' : 'Crear cuenta'}</span>
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
