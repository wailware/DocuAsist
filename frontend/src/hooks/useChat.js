import { useState, useCallback, useRef, useEffect } from 'react'
import { enviarPreguntaStream, obtenerHistorial, listarSesiones, eliminarSesion, renombrarSesion as apiRenombrar } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

function generarSessionId() {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).substring(2, 8)
  return `s_${ts}_${rand}`
}

export default function useChat() {
  const { user } = useAuth()
  const userId = user?.username || 'anonimo'

  const [sesiones, setSesiones] = useState([])
  const [sessionId, setSessionId] = useState(generarSessionId)
  const [mensajes, setMensajes] = useState([])
  const [cargando, setCargando] = useState(false)
  const [faseActual, setFaseActual] = useState(null) // {fase, nodo, latencia_s}
  const [cargandoHistorial, setCargandoHistorial] = useState(false)
  const [error, setError] = useState(null)
  const contadorRef = useRef(0)

  const _cargarSesiones = async () => {
    try {
      const data = await listarSesiones(userId)
      setSesiones(data.sesiones || [])
    } catch {
      // No bloquear la UI si falla la carga inicial
    }
  }

  useEffect(() => {
    _cargarSesiones()
  }, [userId])

  const enviar = useCallback(async (texto) => {
    if (!texto.trim() || cargando) return

    setError(null)
    const id = ++contadorRef.current

    const msgUsuario = {
      id: `user-${id}`,
      tipo: 'usuario',
      texto: texto.trim(),
      timestamp: new Date(),
    }

    // Mensaje placeholder para streaming
    const msgStreamId = `asist-${id}`
    const msgStream = {
      id: msgStreamId,
      tipo: 'asistente',
      texto: '',
      citas: [],
      noConsta: false,
      traza: [],
      consultaId: 0,
      streaming: true,
      timestamp: new Date(),
    }

    setMensajes((prev) => [...prev, msgUsuario, msgStream])
    setCargando(true)
    setFaseActual(null)

    try {
      const resultado = await enviarPreguntaStream(
        texto.trim(), sessionId, userId,
        (fase) => setFaseActual(fase),
        // onToken: actualizar el mensaje en streaming
        (token) => {
          setMensajes((prev) =>
            prev.map((m) =>
              m.id === msgStreamId
                ? { ...m, texto: m.texto + token }
                : m
            )
          )
        },
      )

      setFaseActual(null)

      if (resultado) {
        // Reemplazar el mensaje de streaming con el resultado final completo
        setMensajes((prev) =>
          prev.map((m) =>
            m.id === msgStreamId
              ? {
                  ...m,
                  texto: resultado.respuesta,
                  citas: resultado.citas || [],
                  noConsta: resultado.no_consta || false,
                  traza: resultado.traza || [],
                  consultaId: resultado.consulta_id || 0,
                  streaming: false,
                }
              : m
          )
        )
      } else {
        // Si no hubo resultado, eliminar el mensaje placeholder
        setMensajes((prev) => prev.filter((m) => m.id !== msgStreamId))
      }
      _cargarSesiones()
    } catch (err) {
      setFaseActual(null)
      setError(err.message || 'Error al comunicarse con el agente.')
      // Reemplazar el placeholder con el error
      setMensajes((prev) =>
        prev.map((m) =>
          m.id === msgStreamId
            ? {
                id: `error-${id}`,
                tipo: 'error',
                texto: err.message || 'Error de conexion con el servidor.',
                timestamp: new Date(),
              }
            : m
        )
      )
    } finally {
      setCargando(false)
    }
  }, [sessionId, userId])

  const cambiarSesion = useCallback(async (nuevoSessionId) => {
    if (nuevoSessionId === sessionId) return

    setCargandoHistorial(true)
    setSessionId(nuevoSessionId)
    setMensajes([])
    setError(null)
    contadorRef.current = 0

    try {
      const data = await obtenerHistorial(nuevoSessionId)
      const historial = data.mensajes || []

      const mensajesVisuales = []
      let contador = 0

      for (const msg of historial) {
        contador++
        if (msg.role === 'user') {
          mensajesVisuales.push({
            id: `hist-user-${contador}`,
            tipo: 'usuario',
            texto: msg.content,
            timestamp: new Date(),
          })
        } else {
          mensajesVisuales.push({
            id: `hist-asist-${contador}`,
            tipo: 'asistente',
            texto: msg.content,
            citas: [],
            noConsta: false,
            traza: [],
            consultaId: 0,
            timestamp: new Date(),
          })
        }
      }

      contadorRef.current = contador
      setMensajes(mensajesVisuales)
    } catch {
      // Si falla, empezar vacio
    } finally {
      setCargandoHistorial(false)
    }
  }, [sessionId])

  const nuevaSesion = useCallback(() => {
    const nuevo = generarSessionId()
    setSessionId(nuevo)
    setMensajes([])
    setError(null)
    contadorRef.current = 0
  }, [])

  const borrarSesion = useCallback(async (idABorrar) => {
    try {
      await eliminarSesion(idABorrar)
      setSesiones((prev) => prev.filter((s) => s.session_id !== idABorrar))

      if (idABorrar === sessionId) {
        nuevaSesion()
      }
    } catch (err) {
      setError(err.message || 'Error al eliminar la conversación.')
    }
  }, [sessionId, nuevaSesion])

  const renombrarSesionLocal = useCallback(async (sid, titulo) => {
    try {
      await apiRenombrar(sid, titulo)
      setSesiones((prev) =>
        prev.map((s) => (s.session_id === sid ? { ...s, titulo } : s))
      )
    } catch (err) {
      setError(err.message || 'Error al renombrar la conversación.')
    }
  }, [])

  return {
    sesiones,
    sessionId,
    mensajes,
    cargando,
    faseActual,
    cargandoHistorial,
    error,
    enviar,
    cambiarSesion,
    nuevaSesion,
    borrarSesion,
    renombrarSesion: renombrarSesionLocal,
  }
}
