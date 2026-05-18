/**
 * Configuración de animaciones Lottie.
 * 
 * Cada animación referencia un JSON en /public/lottie/.
 * Para añadir animaciones: descargar el JSON desde LottieFiles
 * y colocarlo en public/lottie/ con el nombre indicado aquí.
 * 
 * Recomendaciones de LottieFiles (buscar por estos términos):
 *   - welcome:    "robot assistant" o "friendly bot"
 *   - thinking:   "loading globe" o "earth spinning"
 *   - typing:     "typing dots" o "writing"
 *   - empty:      "empty box" o "no results"
 *   - success:    "success checkmark" o "done"
 *   - error:      "error warning" o "connection lost"
 *   - upload:     "file upload" o "cloud upload"
 *   - legal:      "scales justice" o "legal balance"
 *   - search:     "document search" o "magnifying glass"
 *   - delete:     "trash" o "delete file"
 */

export const LOTTIE_ANIMATIONS = {
  welcome: {
    path: '/lottie/welcome.json',
    width: 280,
    height: 280,
    loop: true,
    label: 'Bienvenida',
  },
  thinking: {
    path: '/lottie/thinking.json',
    width: 120,
    height: 120,
    loop: true,
    label: 'Procesando consulta RAG',
  },
  typing: {
    path: '/lottie/typing.json',
    width: 60,
    height: 40,
    loop: true,
    label: 'Escribiendo respuesta',
  },
  empty: {
    path: '/lottie/empty.json',
    width: 200,
    height: 200,
    loop: true,
    label: 'Sin resultados',
  },
  success: {
    path: '/lottie/success.json',
    width: 80,
    height: 80,
    loop: false,
    label: 'Operación exitosa',
  },
  error: {
    path: '/lottie/error.json',
    width: 160,
    height: 160,
    loop: true,
    label: 'Error de conexión',
  },
  upload: {
    path: '/lottie/upload.json',
    width: 160,
    height: 160,
    loop: true,
    label: 'Subiendo documento',
  },
  legal: {
    path: '/lottie/legal.json',
    width: 100,
    height: 100,
    loop: true,
    label: 'Modo legal activo',
  },
  search: {
    path: '/lottie/search.json',
    width: 100,
    height: 100,
    loop: true,
    label: 'Buscando en documentos',
  },
  delete: {
    path: '/lottie/delete.json',
    width: 80,
    height: 80,
    loop: false,
    label: 'Eliminando documento',
  },
}
