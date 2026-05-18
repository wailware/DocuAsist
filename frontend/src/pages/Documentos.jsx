import { useState, useEffect, useCallback } from 'react'
import {
  Upload,
  Trash2,
  FileText,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Calendar,
  Hash,
  ShieldAlert,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  FileDown,
} from 'lucide-react'
import { listarDocumentos, subirDocumento, eliminarDocumento, escanearCumplimiento, descargarAuditoriaPdf } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import LottieAnimation from '../components/LottieAnimation'
import './Documentos.css'

/**
 * Página de gestión documental.
 * Permite subir, listar y eliminar documentos indexados en ChromaDB.
 */
export default function Documentos() {
  const { user } = useAuth()
  const esAdmin = user?.rol === 'admin'
  const [documentos, setDocumentos] = useState([])
  const [cargando, setCargando] = useState(true)
  const [subiendo, setSubiendo] = useState(false)
  const [eliminando, setEliminando] = useState(null)
  const [escaneando, setEscaneando] = useState(false)
  const [mensaje, setMensaje] = useState(null)
  const [dragOver, setDragOver] = useState(false)

  const cargarDocumentos = useCallback(async () => {
    setCargando(true)
    try {
      const data = await listarDocumentos()
      // Documentos con alertas primero
      const docs = data.documentos || []
      docs.sort((a, b) => {
        const aAlertas = Array.isArray(a.alertas) ? a.alertas.length : 0
        const bAlertas = Array.isArray(b.alertas) ? b.alertas.length : 0
        if (bAlertas !== aAlertas) return bAlertas - aAlertas
        return 0 // mantener orden original para el resto
      })
      setDocumentos(docs)
    } catch (err) {
      setMensaje({ tipo: 'error', texto: `Error al cargar documentos: ${err.message}` })
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    cargarDocumentos()
  }, [cargarDocumentos])

  // Limpiando mensajes automáticamente
  useEffect(() => {
    if (!mensaje) return
    const timer = setTimeout(() => setMensaje(null), 5000)
    return () => clearTimeout(timer)
  }, [mensaje])

  const handleSubir = async (ficheros) => {
    if (!ficheros || ficheros.length === 0) return

    setSubiendo(true)
    setMensaje(null)

    for (const fichero of ficheros) {
      try {
        const resultado = await subirDocumento(fichero)
        setMensaje({
          tipo: 'ok',
          texto: `"${fichero.name}" indexado: ${resultado.num_chunks} chunks, ${resultado.num_paginas} páginas.`,
        })
      } catch (err) {
        setMensaje({ tipo: 'error', texto: `Error con "${fichero.name}": ${err.message}` })
      }
    }

    setSubiendo(false)
    cargarDocumentos()
  }

  const handleEliminar = async (nombre) => {
    if (!window.confirm(`¿Eliminar "${nombre}" del índice?`)) return

    setEliminando(nombre)
    try {
      await eliminarDocumento(nombre)
      setMensaje({ tipo: 'ok', texto: `"${nombre}" eliminado correctamente.` })
      cargarDocumentos()
    } catch (err) {
      setMensaje({ tipo: 'error', texto: `Error al eliminar: ${err.message}` })
    } finally {
      setEliminando(null)
    }
  }

  const handleScan = async () => {
    if (escaneando) return
    setEscaneando(true)
    try {
      const res = await escanearCumplimiento()
      setMensaje({
        tipo: 'ok',
        texto: `Escaneo completado: ${res.documentos_escaneados} documentos, ${res.con_alertas} con alertas.`,
      })
      cargarDocumentos()
    } catch (err) {
      setMensaje({ tipo: 'error', texto: `Error al escanear: ${err.message}` })
    } finally {
      setEscaneando(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleSubir(e.dataTransfer.files)
  }

  return (
    <div className="docs-page">
      {/* Header */}
      <header className="docs-page__header">
        <div>
          <h1 className="docs-page__title">Documentos</h1>
          <p className="docs-page__subtitle">
            Gestiona los contratos indexados en el sistema
          </p>
        </div>
        <div className="docs-page__header-actions">
          {esAdmin && (
            <button className="docs-page__refresh docs-page__scan-btn" onClick={handleScan} disabled={escaneando}>
              <ShieldAlert size={16} className={escaneando ? 'spinning' : ''} />
              <span>{escaneando ? 'Escaneando...' : 'Escanear legalidad'}</span>
            </button>
          )}
          <button className="docs-page__refresh" onClick={cargarDocumentos} disabled={cargando}>
            <RefreshCw size={16} className={cargando ? 'spinning' : ''} />
            <span>Actualizar</span>
          </button>
        </div>
      </header>

      {/* Notificación de estado (subida, borrado, etc.) */}
      {mensaje && (
        <div className={`docs-page__toast docs-page__toast--${mensaje.tipo} animate-fade-in`}>
          {mensaje.tipo === 'ok' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          <span>{mensaje.texto}</span>
        </div>
      )}

      {/* Zona de subida */}
      <div
        className={`docs-page__dropzone ${dragOver ? 'docs-page__dropzone--active' : ''} ${subiendo ? 'docs-page__dropzone--uploading' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {subiendo ? (
          <LottieAnimation name="upload" width={100} height={100} />
        ) : (
          <LottieAnimation name="upload" width={80} height={80} />
        )}

        <div className="docs-page__dropzone-text">
          <span className="docs-page__dropzone-main">
            {subiendo ? 'Indexando documento...' : 'Arrastra documentos aquí'}
          </span>
          <span className="docs-page__dropzone-sub">PDF, DOCX o HTML</span>
        </div>

        {!subiendo && (
          <label className="docs-page__upload-btn">
            <Upload size={16} />
            <span>Seleccionar archivo</span>
            <input
              type="file"
              accept=".pdf,.docx,.html,.htm"
              multiple
              onChange={(e) => handleSubir(e.target.files)}
              hidden
            />
          </label>
        )}
      </div>

      {/* Lista de documentos */}
      <div className="docs-page__list">
        <div className="docs-page__list-header">
          <span className="docs-page__list-count">
            {documentos.length} documento{documentos.length !== 1 ? 's' : ''} indexado{documentos.length !== 1 ? 's' : ''}
          </span>
        </div>

        {cargando && documentos.length === 0 ? (
          <div className="docs-page__loading">
            <LottieAnimation name="search" width={80} height={80} />
            <span>Cargando documentos...</span>
          </div>
        ) : documentos.length === 0 ? (
          <div className="docs-page__empty">
            <LottieAnimation name="empty" width={140} height={140} />
            <span>No hay documentos indexados</span>
            <span className="docs-page__empty-sub">Sube un contrato para empezar</span>
          </div>
        ) : (
          <div className="docs-page__grid">
            {documentos.map((doc, i) => (
              <DocumentCard
                key={doc.doc_id}
                doc={doc}
                eliminando={eliminando === doc.nombre}
                onEliminar={() => handleEliminar(doc.nombre)}
                delay={i < 20 ? i * 40 : 0}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


/**
 * Tarjeta individual de documento con metadatos, alertas y acciones.
 */
function DocumentCard({ doc, eliminando, onEliminar, delay }) {
  const [alertasAbiertas, setAlertasAbiertas] = useState(false)

  const fecha = doc.indexado_en ? new Date(doc.indexado_en).toLocaleDateString('es-ES', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }) : '—'

  const alertas = Array.isArray(doc.alertas) ? doc.alertas : []
  const tieneAlertas = alertas.length > 0
  const alertasAltas = alertas.filter((a) => a.severidad === 'alta').length

  return (
    <div
      className={`doc-card ${tieneAlertas ? 'doc-card--has-alerts' : ''}`}
    >
      <div className={`doc-card__icon ${tieneAlertas ? 'doc-card__icon--alert' : ''}`}>
        {tieneAlertas ? <ShieldAlert size={20} /> : <FileText size={20} />}
      </div>

      <div className="doc-card__info">
        <span className="doc-card__name" title={doc.nombre}>{doc.nombre}</span>
        {doc.resumen && (
          <p className="doc-card__resumen">{doc.resumen}</p>
        )}
        <div className="doc-card__meta">
          <span className="doc-card__meta-item">
            <Hash size={11} />
            {doc.num_chunks} chunks
          </span>
          <span className="doc-card__meta-item">
            <Calendar size={11} />
            {fecha}
          </span>
          {doc.tipo_contrato && (
            <span className="doc-card__meta-item doc-card__meta-item--badge">
              {doc.tipo_contrato}
            </span>
          )}
          {tieneAlertas ? (
            <button
              className="doc-card__alert-badge doc-card__alert-badge--warn"
              onClick={() => setAlertasAbiertas(!alertasAbiertas)}
            >
              <ShieldAlert size={11} />
              {alertasAltas > 0
                ? `${alertasAltas} alerta${alertasAltas > 1 ? 's' : ''}`
                : `${alertas.length} aviso${alertas.length > 1 ? 's' : ''}`}
              {alertasAbiertas ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
            </button>
          ) : (
            <span className="doc-card__alert-badge doc-card__alert-badge--ok">
              <ShieldCheck size={11} />
              Conforme
            </span>
          )}
        </div>

        {alertasAbiertas && tieneAlertas && (
          <div className="doc-card__alertas animate-fade-in">
            {alertas.map((a, i) => (
              <div key={i} className={`doc-card__alerta doc-card__alerta--${a.severidad}`}>
                <span className="doc-card__alerta-ref">{a.articulo}</span>
                <span className="doc-card__alerta-msg">{a.mensaje}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="doc-card__actions">
        <button
          className="doc-card__action-btn"
          onClick={async () => {
            try {
              const blob = await descargarAuditoriaPdf(doc.doc_id)
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `auditoria_${doc.nombre.replace(/\.[^.]+$/, '')}.pdf`
              a.click()
              URL.revokeObjectURL(url)
            } catch { /* silenciar */ }
          }}
          title="Descargar informe PDF"
        >
          <FileDown size={15} />
        </button>
        <button
          className="doc-card__delete"
          onClick={onEliminar}
          disabled={eliminando}
          title="Eliminar del índice"
        >
          {eliminando ? (
            <LottieAnimation name="delete" width={20} height={20} />
          ) : (
            <Trash2 size={15} />
          )}
        </button>
      </div>
    </div>
  )
}
