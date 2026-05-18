# DocuAsist — Frontend

Frontend del asistente documental corporativo. React + Vite con animaciones Lottie.

## Requisitos

- Node.js 18+
- Backend corriendo en `http://localhost:8080`

## Instalación

```bash
cd frontend
npm install
npm run dev
```

La aplicación se abrirá en `http://localhost:5173`.

## Estructura

```
frontend/
├── public/
│   └── lottie/                        # JSONs de animaciones Lottie
│       ├── welcome.json
│       ├── thinking.json
│       ├── typing.json
│       ├── empty.json
│       ├── success.json
│       ├── error.json
│       ├── upload.json
│       ├── legal.json
│       ├── search.json
│       └── delete.json
├── src/
│   ├── api/
│   │   ├── client.js                  # Cliente HTTP para la API del agente
│   │   └── index.js                   # Barrel export
│   ├── components/
│   │   ├── ChatInput.jsx              # Textarea autoexpandible
│   │   ├── ChatInput.css
│   │   ├── ChatMessage.jsx            # Burbuja de mensaje con citas y traza
│   │   ├── ChatMessage.css
│   │   ├── Layout.jsx                 # Sidebar + contenido principal
│   │   ├── Layout.css
│   │   ├── LottieAnimation.jsx        # Wrapper de Lottie con fallback SVG
│   │   └── LottieAnimation.css
│   ├── constants/
│   │   └── lottie.js                  # Configuración de animaciones
│   ├── hooks/
│   │   └── useChat.js                 # Lógica del chat (estado, envío, historial)
│   ├── pages/
│   │   ├── Chat.jsx                   # Página principal del chat
│   │   ├── Chat.css
│   │   ├── Documentos.jsx             # Gestión de documentos indexados
│   │   ├── Documentos.css
│   │   ├── Auditoria.jsx              # Historial de consultas
│   │   └── Auditoria.css
│   ├── App.jsx                        # Router
│   ├── main.jsx                       # Punto de entrada
│   └── index.css                      # Estilos globales y variables CSS
├── .env                               # Variables de entorno
├── .env.example
├── index.html
├── vite.config.js
├── package.json
└── README.md
```

## Animaciones Lottie

El sistema usa animaciones Lottie para dar vida a la interfaz. Si un JSON no existe,
se muestra un fallback SVG animado con CSS.

### Cómo añadir animaciones

1. Ir a [LottieFiles](https://lottiefiles.com)
2. Buscar la animación (ver sugerencias en `src/constants/lottie.js`)
3. Descargar como "Lottie JSON"
4. Colocar el fichero en `public/lottie/` con el nombre correcto

### Búsquedas sugeridas en LottieFiles

| Animación   | Buscar en LottieFiles                        |
|-------------|----------------------------------------------|
| welcome     | "robot assistant", "friendly bot"            |
| thinking    | "loading globe", "earth spinning"            |
| typing      | "typing dots", "chat loading"                |
| empty       | "empty box", "no results", "empty state"     |
| success     | "success checkmark", "check done"            |
| error       | "error warning", "connection lost"           |
| upload      | "file upload", "cloud upload"                |
| legal       | "scales justice", "legal balance"            |
| search      | "document search", "magnifying glass"        |
| delete      | "trash delete", "remove file"                |

## Proxy de desarrollo

Vite redirige `/api/*` al backend en `http://localhost:8080`. Esto evita problemas
de CORS durante desarrollo. En producción, configurar el proxy en nginx o similar.

## Build de producción

```bash
npm run build
```

Los ficheros estáticos se generan en `dist/`.