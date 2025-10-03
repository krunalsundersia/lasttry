import os
import json
import logging
import sys
import uuid
from flask import Flask, request, Response, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import tiktoken
import PyPDF2
from io import BytesIO

# --- Imports for Google OAuth ---
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
CORS(app)

# --- Check for missing SECRET_KEY ---
if not app.secret_key:
    logger.error("FATAL: SESSION_SECRET is not set in the .env file.")
    sys.exit(1)

# --- Google OAuth 2.0 Configuration ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.error("FATAL: GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set in the .env file.")
    sys.exit(1)

CLIENT_SECRETS_FILE = 'client_secret.json'
REDIRECT_URI = 'http://127.0.0.1:5000/callback'
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']

client_config = {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "redirect_uris": [REDIRECT_URI], "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
with open(CLIENT_SECRETS_FILE, 'w') as f:
    json.dump(client_config, f)

flow = Flow.from_client_secrets_file(client_secrets_file=CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)

# --- App Configuration ---
enc = tiktoken.get_encoding("cl100k_base")
TOKEN_LIMIT = 300_000
tokens_used = 0
KEY = os.getenv("OPENROUTER_API_KEY")
if not KEY:
    logging.error("FATAL: OPENROUTER_API_KEY missing.")
    sys.exit(1)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Model Definitions ---
MODELS = { "logic": {"name": "Logic AI"}, "creative": {"name": "Creative AI"}, "technical": {"name": "Technical AI"}, "philosophical": {"name": "Philosophical AI"}, "humorous": {"name": "Humorous AI"}}
SYSTEM_PROMPTS = {
    "logic": "You are Logic AI — analytical, structured, step-by-step...",
    "creative": "You are Creative AI — poetic, metaphorical, emotional...",
    "technical": "You are Technical AI — precise, technical, detail-oriented...",
    "philosophical": "You are Philosophical AI — deep, reflective, abstract...",
    "humorous": "You are Humorous AI — witty, lighthearted, engaging..."
}
OPENROUTER_MODELS = {
    "logic": "deepseek/deepseek-chat-v3.1:free",
    "creative": "deepseek/deepseek-chat-v3.1:free",
    "technical": "deepseek/deepseek-chat-v3.1:free",
    "philosophical": "deepseek/deepseek-chat-v3.1:free",
    "humorous": "deepseek/deepseek-chat-v3.1:free",
    "asklurk": "deepseek/deepseek-chat-v3.1:free"
}

# --- Helper Functions ---
def extract_text_from_pdf(file_content):
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "".join(page.extract_text() + "\n" for page in pdf_reader.pages)
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return None

def generate(bot_name: str, system: str, user: str, file_contents: list = None):
    global tokens_used
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=KEY, timeout=60.0)
    full_user_prompt = user
    if file_contents:
        file_context = "\n\n".join(file_contents)
        full_user_prompt = f"{user}\n\nAttached files content:\n{file_context}"
    
    try:
        stream = client.chat.completions.create(
            extra_headers={"HTTP-Referer": "http://localhost:5000", "X-Title": "Pentad-Chat"},
            model=OPENROUTER_MODELS.get(bot_name, "deepseek/deepseek-chat-v3.1:free"),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": full_user_prompt}],
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield f"data: {json.dumps({'bot': bot_name, 'text': chunk.choices[0].delta.content})}\n\n"
        yield f"data: {json.dumps({'bot': bot_name, 'done': True})}\n\n"
    except Exception as e:
        logger.error(f"Error generating response for {bot_name}: {e}")
        yield f"data: {json.dumps({'bot': bot_name, 'error': str(e)})}\n\n"

# --- Decorator to Protect Routes ---
def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return redirect(url_for('login_page'))
        return function(*args, **kwargs)
    wrapper.__name__ = function.__name__
    return wrapper

# --- Authentication Routes ---
@app.route("/login")
def login_page():
    return render_template("login.html")

@app.route("/auth")
def auth():
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    try:
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        session["google_id"] = user_info.get("id")
        session["name"] = user_info.get("name")
        session["picture"] = user_info.get("picture")
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error during Google callback: {e}")
        return redirect(url_for('login_page'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# --- Main App Routes (Now Protected) ---
@app.route("/")
@login_is_required
def index():
    return render_template("index.html", user_name=session.get('name'), user_picture=session.get('picture'))

@app.route("/chat", methods=["POST"])
@login_is_required
def chat():
    data = request.json or {}
    prompt = data.get("prompt", "").strip()
    fileUrls = data.get("fileUrls", [])

    file_contents = []
    if fileUrls:
        for file_url in fileUrls:
            try:
                file_path = file_url.replace('/static/uploads/', '')
                full_path = os.path.join(UPLOAD_FOLDER, file_path)
                if os.path.exists(full_path):
                    with open(full_path, 'rb') as f:
                        file_content = f.read()
                        filename = file_path.lower()
                        if filename.endswith('.pdf'):
                            text_content = extract_text_from_pdf(file_content)
                            if text_content:
                                file_contents.append(f"PDF Content from '{file_path}':\n{text_content}\n")
                        elif filename.endswith('.txt'):
                            text_content = file_content.decode('utf-8')
                            file_contents.append(f"Text Content from '{file_path}':\n{text_content}\n")
            except Exception as e:
                logger.error(f"Error processing file {file_url}: {e}")

    def event_stream():
        generators = {key: generate(key, SYSTEM_PROMPTS[key], prompt, file_contents) for key in MODELS.keys()}
        active_bots = list(MODELS.keys())
        while active_bots:
            for bot_name in active_bots[:]:
                try:
                    chunk = next(generators[bot_name])
                    yield chunk
                    try:
                        chunk_data = json.loads(chunk.split('data: ')[1])
                        if chunk_data.get('done') or chunk_data.get('error'):
                            active_bots.remove(bot_name)
                    except (json.JSONDecodeError, IndexError):
                        pass
                except StopIteration:
                    active_bots.remove(bot_name)
        yield f"data: {json.dumps({'all_done': True})}\n\n"
    
    return Response(event_stream(), mimetype="text/event-stream")

@app.route("/upload", methods=["POST"])
@login_is_required
def upload():
    urls = []
    if 'files' not in request.files:
        return jsonify(urls=[], error="No files provided"), 400
    for file in request.files.getlist('files'):
        if file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            name = f"{uuid.uuid4().hex}{ext}"
            path = os.path.join(UPLOAD_FOLDER, name)
            file.save(path)
            urls.append(f"/static/uploads/{name}")
    return jsonify(urls=urls)

@app.route("/asklurk", methods=["POST"])
@login_is_required
def asklurk():
    data = request.json or {}
    answers = data.get("answers", {})
    prompt = data.get("prompt", "")
    if not answers:
        return jsonify(best="", error="No responses to analyze"), 400
    
    merged_content = f"Original question: {prompt}\n\n" + "".join(f"## {MODELS[key]['name']}:\n{response}\n\n" for key, response in answers.items() if key in MODELS)
    
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=KEY, timeout=30.0)
    response = client.chat.completions.create(
        model=OPENROUTER_MODELS["asklurk"],
        messages=[
            {"role": "system", "content": "You are AskLurk, an expert AI synthesizer..."},
            {"role": "user", "content": f"Analyze these AI responses to '{prompt}':\n{merged_content}\nProvide the best synthesized answer."}
        ]
    )
    best_answer = response.choices[0].message.content
    return jsonify(best=best_answer)

# --- Public Routes ---
@app.route("/health")
def health():
    return jsonify({"status": "ok", "api_key_configured": bool(KEY)})

# --- Main Execution ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
