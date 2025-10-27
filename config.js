// config.js - Configuración para el Chatbot Dante Propiedades

const CONFIG = {
    // ⚠️ REEMPLAZA CON TU URL REAL DE RENDER
    API_URL: 'https://chatgpt-eio1.onrender.com/chat',
    
    // Configuración de la UI
    UI: {
        botName: 'Asistente Dante Propiedades',
        botAvatar: '🏠',
        userAvatar: '👤',
        placeholder: 'Escribe tu mensaje sobre propiedades...',
        thinkingMessage: '🤖 Pensando...',
        errorMessage: '⚠️ Servicio no disponible. Intenta nuevamente.'
    },
    
    // Timeouts y reintentos
    NETWORK: {
        timeout: 30000, // 30 segundos
        maxRetries: 2,
        retryDelay: 2000 // 2 segundos
    },
    
    // Mensajes predefinidos
    MESSAGES: {
        welcome: '¡Hola! Soy tu asistente de Dante Propiedades. ¿En qué puedo ayudarte?',
        error: 'Lo siento, hubo un error. Por favor, intenta nuevamente.',
        timeout: 'La respuesta está tardando más de lo esperado. ¿Podrías intentar con una pregunta más específica?'
    }
};

// Exportar para usar en otros archivos
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG; // Para Node.js/Pruebas
} else {
    window.CONFIG = CONFIG; // Para navegador
}