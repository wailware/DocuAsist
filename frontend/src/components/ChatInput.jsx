import { useState, useRef, useEffect } from 'react'
import { Loader, ArrowUp } from 'lucide-react'
import './ChatInput.css'

export default function ChatInput({ onEnviar, cargando = false }) {
  const [texto, setTexto] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`
  }, [texto])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!cargando) textareaRef.current?.focus()
  }, [cargando])

  const handleEnviar = () => {
    if (!texto.trim() || cargando) return
    onEnviar(texto.trim())
    setTexto('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleEnviar()
    }
  }

  const activo = texto.trim() && !cargando

  return (
    <div className="chat-input">
      <div className={`chat-input__container ${activo ? 'chat-input__container--active' : ''}`}>
        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          placeholder={cargando ? 'El agente esta procesando...' : 'Escribe tu pregunta sobre los contratos...'}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={cargando}
          rows={1}
        />
        <button
          className={`chat-input__send ${activo ? 'chat-input__send--active' : ''}`}
          onClick={handleEnviar}
          disabled={!activo}
          aria-label="Enviar pregunta"
        >
          {cargando ? (
            <Loader size={16} className="chat-input__spinner" />
          ) : (
            <ArrowUp size={16} />
          )}
        </button>
      </div>
      <span className="chat-input__hint">
        Enter para enviar · Shift+Enter para nueva linea
      </span>
    </div>
  )
}
