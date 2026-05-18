import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('docuasist_token'))
  const [cargando, setCargando] = useState(!!localStorage.getItem('docuasist_token'))

  // Verificar token al montar
  useEffect(() => {
    if (!token) return
    fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error()
        return res.json()
      })
      .then(setUser)
      .catch(() => {
        localStorage.removeItem('docuasist_token')
        setToken(null)
        setUser(null)
      })
      .finally(() => setCargando(false))
  }, [token])

  const login = useCallback((tokenStr, userData) => {
    localStorage.setItem('docuasist_token', tokenStr)
    setToken(tokenStr)
    setUser(userData)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('docuasist_token')
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, cargando, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider')
  return ctx
}
