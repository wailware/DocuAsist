import { useState, useEffect } from 'react'
import Lottie from 'lottie-react'
import { LOTTIE_ANIMATIONS } from '../constants/lottie'
import './LottieAnimation.css'

/**
 * Componente que renderiza una animación Lottie con fallback visual.
 * Si el JSON no existe en /public/lottie/, muestra un fallback CSS animado.
 *
 * @param {string} name - Clave de la animación (ver constants/lottie.js)
 * @param {number} width - Ancho en px (sobreescribe el default)
 * @param {number} height - Alto en px (sobreescribe el default)
 * @param {boolean} loop - Loop de la animación (sobreescribe el default)
 * @param {string} className - Clase CSS adicional
 */
export default function LottieAnimation({ name, width, height, loop, className = '' }) {
  const [animationData, setAnimationData] = useState(null)
  const [hasError, setHasError] = useState(false)

  const config = LOTTIE_ANIMATIONS[name]
  if (!config) {
    console.warn(`[LottieAnimation] Animación "${name}" no encontrada en la configuración.`)
    return null
  }

  const finalWidth = width || config.width
  const finalHeight = height || config.height
  const finalLoop = loop !== undefined ? loop : config.loop

  useEffect(() => {
    let cancelled = false

    fetch(config.path)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data) => {
        if (!cancelled) setAnimationData(data)
      })
      .catch(() => {
        if (!cancelled) setHasError(true)
      })

    return () => { cancelled = true }
  }, [config.path])

  // Fallback CSS mientras carga o si no existe el JSON
  if (hasError || !animationData) {
    return (
      <div
        className={`lottie-fallback lottie-fallback--${name} ${className}`}
        style={{ width: finalWidth, height: finalHeight }}
        role="img"
        aria-label={config.label}
      >
        <FallbackIcon name={name} />
      </div>
    )
  }

  return (
    <div className={`lottie-wrapper ${className}`} style={{ width: finalWidth, height: finalHeight }}>
      <Lottie
        animationData={animationData}
        loop={finalLoop}
        style={{ width: '100%', height: '100%' }}
        aria-label={config.label}
      />
    </div>
  )
}


/**
 * Iconos SVG animados como fallback cuando no hay JSON de Lottie.
 */
function FallbackIcon({ name }) {
  switch (name) {
    case 'welcome':
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--pulse">
          <circle cx="50" cy="40" r="18" fill="var(--color-accent)" opacity="0.8" />
          <rect x="30" y="62" width="40" height="24" rx="6" fill="var(--color-accent)" opacity="0.6" />
          <circle cx="43" cy="37" r="3" fill="var(--color-bg)" />
          <circle cx="57" cy="37" r="3" fill="var(--color-bg)" />
          <path d="M43 46 Q50 52 57 46" stroke="var(--color-bg)" strokeWidth="2" fill="none" strokeLinecap="round" />
        </svg>
      )

    case 'thinking':
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--spin">
          <circle cx="50" cy="50" r="35" fill="none" stroke="var(--color-accent)" strokeWidth="3" opacity="0.2" />
          <path d="M50 15 A35 35 0 0 1 85 50" fill="none" stroke="var(--color-accent)" strokeWidth="3" strokeLinecap="round" />
        </svg>
      )

    case 'typing':
      return (
        <svg viewBox="0 0 60 30" className="fallback-svg">
          <circle cx="12" cy="15" r="4" fill="var(--color-text-muted)" className="dot dot-1" />
          <circle cx="30" cy="15" r="4" fill="var(--color-text-muted)" className="dot dot-2" />
          <circle cx="48" cy="15" r="4" fill="var(--color-text-muted)" className="dot dot-3" />
        </svg>
      )

    case 'empty':
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--float">
          <rect x="25" y="20" width="50" height="60" rx="4" fill="none" stroke="var(--color-text-muted)" strokeWidth="2" />
          <line x1="35" y1="38" x2="65" y2="38" stroke="var(--color-text-muted)" strokeWidth="2" opacity="0.5" />
          <line x1="35" y1="48" x2="55" y2="48" stroke="var(--color-text-muted)" strokeWidth="2" opacity="0.3" />
          <circle cx="50" cy="68" r="6" fill="none" stroke="var(--color-text-muted)" strokeWidth="2" opacity="0.4" />
          <line x1="47" y1="65" x2="53" y2="71" stroke="var(--color-text-muted)" strokeWidth="2" opacity="0.4" />
        </svg>
      )

    case 'error':
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--pulse">
          <circle cx="50" cy="50" r="35" fill="var(--color-error-soft)" />
          <line x1="38" y1="38" x2="62" y2="62" stroke="var(--color-error)" strokeWidth="4" strokeLinecap="round" />
          <line x1="62" y1="38" x2="38" y2="62" stroke="var(--color-error)" strokeWidth="4" strokeLinecap="round" />
        </svg>
      )

    case 'upload':
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--float">
          <path d="M30 60 L50 40 L70 60" fill="none" stroke="var(--color-accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          <line x1="50" y1="40" x2="50" y2="75" stroke="var(--color-accent)" strokeWidth="3" strokeLinecap="round" />
          <path d="M25 50 A30 30 0 0 1 75 50" fill="none" stroke="var(--color-text-muted)" strokeWidth="2" opacity="0.4" />
        </svg>
      )

    case 'search':
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--pulse">
          <circle cx="42" cy="42" r="20" fill="none" stroke="var(--color-accent)" strokeWidth="3" />
          <line x1="57" y1="57" x2="75" y2="75" stroke="var(--color-accent)" strokeWidth="4" strokeLinecap="round" />
        </svg>
      )

    default:
      return (
        <svg viewBox="0 0 100 100" className="fallback-svg fallback-svg--pulse">
          <circle cx="50" cy="50" r="30" fill="var(--color-accent-soft)" />
          <circle cx="50" cy="50" r="8" fill="var(--color-accent)" />
        </svg>
      )
  }
}
