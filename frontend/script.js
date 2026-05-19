const chatMessages = document.getElementById('chat-messages');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const clearChatBtn = document.getElementById('clear-chat');
const apiStatus = document.getElementById('api-status');

// Configuración de la API
const API_URL = 'https://b07dwngt-8000.use2.devtunnels.ms';

// Ajuste automático de altura del textarea
userInput.addEventListener('input', () => {
    userInput.style.height = 'auto';
    userInput.style.height = userInput.scrollHeight + 'px';
});

// Enviar con Enter (sin Shift)
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

// Verificar estado de la API al cargar
async function checkHealth() {
    try {
        const response = await fetch(`${API_URL}/health`);
        if (response.ok) {
            apiStatus.textContent = 'En línea';
            apiStatus.parentElement.querySelector('.pulse').style.backgroundColor = '#10b981';
        } else {
            throw new Error();
        }
    } catch (err) {
        apiStatus.textContent = 'Fuera de línea';
        apiStatus.parentElement.querySelector('.pulse').style.backgroundColor = '#ef4444';
        apiStatus.parentElement.querySelector('.pulse').style.animation = 'none';
    }
}

checkHealth();

// Función para agregar mensajes al chat
function appendMessage(role, content, context = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const icon = role === 'user' ? 'user' : 'bot';
    
    let contextHtml = '';
    if (context && context.length > 0) {
        contextHtml = `<div class="context-pill">Contexto: ${context.length} fragmentos recuperados</div>`;
    }

    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i data-lucide="${icon}"></i>
        </div>
        <div class="message-content">
            ${content}
            ${contextHtml}
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    lucide.createIcons();
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Función para mostrar indicador de escritura
function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message assistant typing-indicator-wrapper';
    indicator.id = 'typing-indicator';
    indicator.innerHTML = `
        <div class="message-avatar">
            <i data-lucide="bot"></i>
        </div>
        <div class="message-content">
            <div class="typing-indicator">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(indicator);
    lucide.createIcons();
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
}

// Manejo del formulario
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const question = userInput.value.trim();
    if (!question) return;

    // Limpiar input
    userInput.value = '';
    userInput.style.height = 'auto';
    
    // Agregar mensaje del usuario
    appendMessage('user', question);
    
    // Deshabilitar botón y mostrar cargando
    sendButton.disabled = true;
    showTypingIndicator();

    try {
        const response = await fetch(`${API_URL}/ask`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question })
        });

        const data = await response.json();
        removeTypingIndicator();

        if (response.ok) {
            appendMessage('assistant', data.answer, data.context_used);
        } else {
            appendMessage('assistant', `Error: ${data.detail || 'No se pudo obtener respuesta'}`);
        }
    } catch (error) {
        removeTypingIndicator();
        appendMessage('assistant', `Error de conexión: Asegúrate de que el servidor API esté corriendo en el puerto 8000. Error: ${error.message}`);
        console.error('Error:', error);
    } finally {
        sendButton.disabled = false;
        userInput.focus();
    }
});

// Limpiar chat
clearChatBtn.addEventListener('click', () => {
    if (confirm('¿Estás seguro de que quieres limpiar el historial del chat?')) {
        const firstMessage = chatMessages.firstElementChild;
        chatMessages.innerHTML = '';
        chatMessages.appendChild(firstMessage);
    }
});
