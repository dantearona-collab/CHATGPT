// config.js
const CONFIG = {
    // Cambia esta URL por la de tu app en Render
    API_URL: 'https://tu-app-en-render.onrender.com/chat',
    
    // Para desarrollo local
    // API_URL: 'http://127.0.0.1:8000/chat'
};

// En tu chat.js
async function sendMessage(message) {
    try {
        const response = await fetch(CONFIG.API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                channel: 'web'
            })
        });
        
        const data = await response.json();
        return data.respuesta_bot || "Sin respuesta";
    } catch (error) {
        console.error('Error:', error);
        return "Error de conexión con el servidor";
    }
}