import { useRef, useEffect, useState } from 'react'
import {
  Download,
  Plus,
  Search,
  Scale,
  GitCompare,
  Calendar,
  BarChart3,
  MessageSquare,
  FileText,
  Sparkles,
} from 'lucide-react'
import { useChatContext } from '../contexts/ChatContext'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import LottieAnimation from '../components/LottieAnimation'
import { exportarSesion } from '../api/client'
import './Chat.css'

export default function Chat() {
  const {
    sessionId,
    mensajes,
    cargando,
    faseActual,
    cargandoHistorial,
    enviar,
    nuevaSesion,
  } = useChatContext()

  const scrollRef = useRef(null)
  const [exportando, setExportando] = useState(false)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      })
    }
  }, [mensajes, cargando])

  const handleExport = async () => {
    if (exportando) return
    setExportando(true)
    try {
      const md = await exportarSesion(sessionId)
      const blob = new Blob([md], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `sesion_${sessionId}.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // Silenciar
    } finally {
      setExportando(false)
    }
  }

  const sinMensajes = mensajes.length === 0

  return (
    <div className="chat-page">
      <header className="chat-page__header">
        <div>
          <h1 className="chat-page__title">Chat</h1>
          <p className="chat-page__subtitle">Consulta informacion de contratos laborales</p>
        </div>
        <div className="chat-page__header-actions">
          {!sinMensajes && (
            <>
              <button
                className="chat-page__action-btn"
                onClick={handleExport}
                disabled={exportando}
                title="Exportar como Markdown"
              >
                <Download size={16} />
                <span>Exportar</span>
              </button>
              <button className="chat-page__action-btn chat-page__action-btn--new" onClick={nuevaSesion} title="Nueva conversación">
                <Plus size={16} />
                <span>Nueva</span>
              </button>
            </>
          )}
        </div>
      </header>

      <div className="chat-page__messages" ref={scrollRef}>
        {cargandoHistorial ? (
          <div className="chat-page__loading-history">
            <LottieAnimation name="search" width={60} height={60} />
            <span>Cargando conversación...</span>
          </div>
        ) : sinMensajes ? (
          <WelcomeScreen onSugerencia={enviar} />
        ) : (
          <div className="chat-page__conversation">
            {mensajes.map((msg) => (
              <ChatMessage key={msg.id} mensaje={msg} sessionId={sessionId} />
            ))}

            {cargando && (
              <div className="chat-page__thinking animate-fade-in">
                <div className="chat-page__thinking-dots">
                  <span /><span /><span />
                </div>
                <div className="chat-page__thinking-text">
                  <span className="chat-page__thinking-label">
                    {faseActual?.fase || 'Procesando consulta'}
                  </span>
                  <span className="chat-page__thinking-sub">
                    {faseActual?.latencia_s
                      ? `Completado en ${faseActual.latencia_s.toFixed(1)}s`
                      : 'RAG · Embeddings · Análisis'}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <ChatInput onEnviar={enviar} cargando={cargando} />
    </div>
  )
}

const SUGERENCIAS = [
  { texto: '¿Cuál es el salario de Santiago Campos?', icon: Search, color: 'accent' },
  { texto: 'Compara la jornada de Mario Blanco con la de Yolanda Fuentes', icon: GitCompare, color: 'legal' },
  { texto: 'Hazme un resumen del contrato de Sara Mora', icon: FileText, color: 'success' },
  { texto: '¿Es legal el contrato de Ricardo Mendoza?', icon: Scale, color: 'error' },
  { texto: '¿Cuál es el salario medio de todos los contratos?', icon: BarChart3, color: 'accent' },
  { texto: '¿Cuándo finaliza el contrato de Rubén Torres López?', icon: Calendar, color: 'legal' },
]

function WelcomeScreen({ onSugerencia }) {
  return (
    <div className="welcome">
      <div className="welcome__hero">
        <div className="welcome__icon-ring">
          <Sparkles size={32} />
        </div>
        <h2 className="welcome__title">¿En qué puedo ayudarte?</h2>
        <p className="welcome__desc">
          Consulta, compara y analiza contratos laborales.
          Respuestas con citas verificables de los documentos originales.
        </p>
      </div>

      <div className="welcome__grid">
        {SUGERENCIAS.map((s, i) => {
          const Icon = s.icon
          return (
            <button
              key={i}
              className={`welcome__card welcome__card--${s.color}`}
              onClick={() => onSugerencia(s.texto)}
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <div className="welcome__card-icon">
                <Icon size={16} />
              </div>
              <span className="welcome__card-text">{s.texto}</span>
            </button>
          )
        })}
      </div>

      <div className="welcome__footer">
        <MessageSquare size={13} />
        <span>Escribe tu pregunta o selecciona una sugerencia</span>
      </div>
    </div>
  )
}
