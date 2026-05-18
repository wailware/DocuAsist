/**
 * Cliente HTTP para la API de DocuAsist.
 * Todas las llamadas pasan por el proxy de Vite (/api → localhost:8080).
 */

const BASE = '/api'

function getAuthHeaders() {
  const token = localStorage.getItem('docuasist_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(endpoint, options = {}) {
  const url = `${BASE}${endpoint}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders(), ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Error ${res.status}: ${res.statusText}`)
  }
  return res.json()
}

// --- Auth ---

export async function loginUsuario(username, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function registrarUsuario(username, email, password) {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  })
}

// --- Chat ---

export async function enviarPregunta(pregunta, sessionId = 'default', userId = 'anonimo') {
  return request('/chat', {
    method: 'POST',
    body: JSON.stringify({
      pregunta,
      user_id: userId,
      session_id: sessionId,
    }),
  })
}

/**
 * Envía una pregunta con streaming SSE.
 * Llama a onFase({fase, nodo, latencia_s}) por cada nodo completado.
 * Devuelve la respuesta final completa.
 */
/**
 * Envía una pregunta con streaming SSE.
 * Callbacks:
 *   onFase({fase, nodo, latencia_s}) — por cada nodo completado
 *   onToken(texto) — cada token de la respuesta en tiempo real
 * Devuelve la respuesta final completa.
 */
export async function enviarPreguntaStream(pregunta, sessionId, userId, onFase, onToken) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ pregunta, user_id: userId, session_id: sessionId }),
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Error ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let resultado = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let eventType = null
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim()
      } else if (line.startsWith('data: ') && eventType) {
        try {
          const data = JSON.parse(line.slice(6))
          if (eventType === 'fase' && onFase) {
            onFase(data)
          } else if (eventType === 'token' && onToken) {
            onToken(data.token)
          } else if (eventType === 'done') {
            resultado = data
          }
        } catch { /* ignore parse errors */ }
        eventType = null
      }
    }
  }

  return resultado
}

// --- Sesiones ---

export async function listarSesiones(userId = null, limite = 30) {
  const params = new URLSearchParams({ limite: String(limite) })
  if (userId) params.set('user_id', userId)
  return request(`/sessions?${params}`)
}

export async function obtenerHistorial(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}/history`)
}

export async function renombrarSesion(sessionId, titulo) {
  return request(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ titulo }),
  })
}

export async function eliminarSesion(sessionId) {
  return request(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}

export async function exportarSesion(sessionId) {
  const url = `${BASE}/sessions/${encodeURIComponent(sessionId)}/export`
  const res = await fetch(url, { headers: getAuthHeaders() })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Error ${res.status}`)
  }
  return res.text()
}

// --- Documentos ---

export async function listarDocumentos() {
  return request('/documents')
}

export async function subirDocumento(fichero) {
  const formData = new FormData()
  formData.append('fichero', fichero)
  const res = await fetch(`${BASE}/documents`, {
    method: 'POST',
    body: formData,
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Error ${res.status}`)
  }
  return res.json()
}

export async function descargarAuditoriaPdf(docId) {
  const url = `${BASE}/documents/${encodeURIComponent(docId)}/audit-pdf`
  const res = await fetch(url, { headers: getAuthHeaders() })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Error ${res.status}`)
  }
  return res.blob()
}

export async function eliminarDocumento(nombre) {
  return request(`/documents/${encodeURIComponent(nombre)}`, { method: 'DELETE' })
}

export async function escanearCumplimiento() {
  return request('/documents/scan-compliance', { method: 'POST' })
}

export async function obtenerEstadisticasContratos() {
  return request('/contracts/stats')
}

