from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import SocketIO, emit
import nltk
from nltk.chat.util import Chat, reflections
import re
import uuid

# ===== TAVILY =====
try:
    from tavily import TavilyClient
    tavily_client = TavilyClient(api_key="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")  
    print("✅ Tavily ready")
except:
    tavily_client = None
    print("❌ Tavily not working")

nltk.download('punkt', quiet=True)

# ===== APP =====
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123'
socketio = SocketIO(app, cors_allowed_origins="*")

# ===== GLOBAL CHAT STORE =====
chat_history_store = {}

# ===== ROUTES =====

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']

    if (role == "admin" and username == "admin" and password == "admin123") or \
       (role == "user" and username == "user" and password == "user123"):

        session['user'] = username
        session['role'] = role

        # initialize user chats
        chat_history_store.setdefault(username, {})

        return redirect(url_for('chatbot_page'))

    return "Invalid Credentials"


@app.route('/chatbot')
def chatbot_page():
    if 'user' not in session:
        return redirect(url_for('home'))

    user = session['user']
    user_chats = chat_history_store.get(user, {})

    chat_id = request.args.get('chat_id')

    # Create new chat if none exists
    if not chat_id or chat_id not in user_chats:
        chat_id = str(uuid.uuid4())
        user_chats[chat_id] = []

    chat_history_store[user] = user_chats

    return render_template(
        'chatbot.html',
        chats=user_chats,
        current_chat=chat_id,
        history=user_chats[chat_id]
    )


@app.route('/new_chat')
def new_chat():
    if 'user' in session:
        user = session['user']
        chat_id = str(uuid.uuid4())

        chat_history_store.setdefault(user, {})[chat_id] = []

        return redirect(url_for('chatbot_page', chat_id=chat_id))

    return redirect(url_for('home'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


# ===== TEXT CLEANING =====
def clean_text(text):
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[#*•|]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def make_paragraph(text):
    sentences = re.split(r'(?<=[.!?]) +', text)
    sentences = [s for s in sentences if len(s) > 40]
    return " ".join(sentences[:3]) if sentences else "No clear answer found."


# ===== SEARCH =====
def search_web(query):
    if not tavily_client:
        return "Search not available."

    try:
        response = tavily_client.search(query=query, max_results=5)

        if response.get("answer"):
            return make_paragraph(clean_text(response["answer"]))

        combined = " ".join([r.get("content", "") for r in response.get("results", [])])
        return make_paragraph(clean_text(combined))

    except Exception as e:
        print("Search error:", e)
        return "Unable to fetch answer."


# ===== CHATBOT =====
pairs = [
    [r"hi|hello|hey", ["Hello!", "Hi there!"]],
    [r"how are you", ["I'm great!", "Doing well!"]],
    [r"your name", ["I'm AI ChatBot"]],
    [r"bye", ["Goodbye!"]],
]

chatbot = Chat(pairs, reflections)


def get_reply(msg):
    if any(word in msg.lower() for word in ['who','what','when','where','why','how','latest','news']):
        return search_web(msg)

    reply = chatbot.respond(msg.lower())
    return reply if reply else search_web(msg)


# ===== SOCKET =====
@socketio.on('send_message')
def handle_message(data):
    msg = data.get('message')
    chat_id = data.get('chat_id')
    user = session.get('user')

    if not user or not msg:
        return

    user_chats = chat_history_store.get(user, {})

    if chat_id not in user_chats:
        user_chats[chat_id] = []

    history = user_chats[chat_id]

    # Save user message
    history.append({"sender": "user", "message": msg})

    # Get reply
    reply = get_reply(msg)

    # Save bot message
    history.append({"sender": "bot", "message": reply})

    chat_history_store[user] = user_chats

    emit('bot_response', {'message': reply})


# ===== RUN =====
if __name__ == '__main__':
    print("🚀 Server running at http://127.0.0.1:5000")
    socketio.run(app, debug=True)