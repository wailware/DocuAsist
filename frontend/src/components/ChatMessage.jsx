import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  User,
  Bot,
  AlertTriangle,
  FileText,
  ChevronDown,
  ChevronUp,
  Clock,
  Scale,
} from 'lucide-react'
import './ChatMessage.css'

export default function ChatMessage({ mensaje }) {
  const [trazaVisible, setTrazaVisible] = useState(false)

  if (mensaje.tipo === 'usuario') {
    return (
      <div className="chat-msg chat-msg--user" style={{ animation: 'slideInRight 300ms ease forwards' }}>
        <div className="chat-msg__avatar chat-msg__avatar--user">
          <User size={16} />
        </div>
        <div className="chat-msg__content">
          <p className="chat-msg__text">{mensaje.texto}</p>
        </div>
      </div>
    )
  }

  if (mensaje.tipo === 'error') {
    return (
      <div className="chat-msg chat-msg--error animate-fade-in">
        <div className="chat-msg__avatar chat-msg__avatar--error">
          <AlertTriangle size={16} />
        </div>
        <div className="chat-msg__content">
          <p className="chat-msg__text">{mensaje.texto}</p>
        </div>
      </div>
    )
  }

  // Mensaje del asistente
  const { texto, citas = [], noConsta, traza = [], streaming } = mensaje
  const tieneTraza = traza.length > 0
  const tieneCitas = citas.length > 0
  const esLegal = traza.some((t) => t.sin_normativa)

  return (
    <div className={`chat-msg chat-msg--assistant ${noConsta ? 'chat-msg--no-consta' : ''}`} style={{ animation: 'slideInLeft 300ms ease forwards' }}>
      <div className="chat-msg__avatar chat-msg__avatar--assistant">
        <Bot size={16} />
      </div>
      <div className="chat-msg__content">
        {esLegal && (
          <div className="chat-msg__badge chat-msg__badge--legal">
            <Scale size={12} />
            <span>Modo legal</span>
          </div>
        )}

        {!streaming && noConsta && (
          <div className="chat-msg__badge chat-msg__badge--no-consta">
            <AlertTriangle size={12} />
            <span>No consta en documentos</span>
          </div>
        )}

        <div className="chat-msg__text chat-msg__markdown">
          <ReactMarkdown>{texto}</ReactMarkdown>
          {streaming && <span className="chat-msg__streaming-cursor" />}
        </div>

        {!streaming && tieneCitas && (
          <div className="chat-msg__citas">
            <span className="chat-msg__citas-label">Fuentes consultadas:</span>
            {citas.map((cita, i) => (
              <span key={i} className="chat-msg__cita">
                <FileText size={11} />
                {cita.nombre_trabajador || 'Desconocido'} — Pag. {cita.pagina}
              </span>
            ))}
          </div>
        )}

        {!streaming && tieneTraza && (
          <div className="chat-msg__actions">
            <div className="chat-msg__traza">
              <button
                className="chat-msg__traza-toggle"
                onClick={() => setTrazaVisible(!trazaVisible)}
              >
                <Clock size={12} />
                <span>
                  {traza.reduce((sum, t) => sum + (t.latencia_s || 0), 0).toFixed(2)}s total
                </span>
                {trazaVisible ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </button>
            </div>
          </div>
        )}

        {!streaming && trazaVisible && tieneTraza && (
          <div className="chat-msg__traza-detail">
            {traza.map((t, i) => (
              <div key={i} className="chat-msg__traza-nodo">
                <span className="chat-msg__traza-nombre">{t.nodo}</span>
                <span className="chat-msg__traza-tiempo">{t.latencia_s}s</span>
                {t.fragmentos_recuperados !== undefined && (
                  <span className="chat-msg__traza-info">{t.fragmentos_recuperados} fragmentos</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
