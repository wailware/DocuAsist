import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ChatProvider } from './contexts/ChatContext'
import { ThemeProvider } from './contexts/ThemeContext'
import Layout from './components/Layout'
import Chat from './pages/Chat'
import Documentos from './pages/Documentos'
import Login from './pages/Login'

function AppRoutes() {
  const { user, cargando } = useAuth()

  if (cargando) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100dvh', color: 'var(--color-text-muted)',
      }}>
        Cargando...
      </div>
    )
  }

  if (!user) {
    return <Login />
  }

  return (
    <ChatProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Chat />} />
          <Route path="documentos" element={<Documentos />} />
        </Route>
      </Routes>
    </ChatProvider>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  )
}
