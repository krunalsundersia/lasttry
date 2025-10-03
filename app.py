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
# IMPORTANT: For Vercel, the redirect URI will be your production URL
# We will handle this in the Vercel settings later. For local testing, this is fine.
REDIRECT_URI = os.environ.get('REDIRECT_URI', 'http://127.0.0.1:5000/callback')

SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile']

client_config = {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET, "redirect_uris": [REDIRECT_URI], "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}
with open(CLIENT_SECRETS_FILE, 'w') as f:
    json.dump(client_config, f)

flow = Flow.from_client_secrets_file(client_secrets_file=CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)

# --- App Configuration ---
enc = tiktoken.get_encoding("cl100k_base")
KEY = os.getenv("OPENROUTER_API_KEY")
if not KEY:
    logging.error("FATAL: OPENROUTER_API_KEY missing.")
    sys.exit(1)
UPLOAD_FOLDER = '/tmp/uploads' # Use /tmp for Vercel's temporary filesystem
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
    "logic": "deepseek/deepseek-chat-v3.1:free", "creative": "deepseek/deepseek-chat-v3.1:free", "technical": "deepseek/deepseek-chat-v3.1:free",
    "philosophical": "deepseek/deepseek-chat-v3.1:free", "humorous": "deepseek/deepseek-chat-v3.1:free", "asklurk": "deepseek/deepseek-chat-v3.1:free"
}

# --- Helper Functions ---
def extract_text_from_pdf(file_content):
    try:
        pdf_file = BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        return "".join(page.extract_text() + "\n" for page in pdf_reader.pages).strip()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return None

def generate(bot_name: str, system: str, user: str, file_contents: list = None):
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=KEY, timeout=60.0)
    full_user_prompt = f"{user}\n\nAttached files content:\n{''.join(file_contents)}" if file_contents else user
    try:
        stream = client.chat.completions.create(
            extra_headers={"HTTP-Referer": "YOUR_VERCEL_URL", "X-Title": "Pentad-Chat"}, # Update with your Vercel URL
            model=OPENROUTER_MODELS.get(bot_name), messages=[{"role": "system", "content": system}, {"role": "user", "content": full_user_prompt}], stream=True)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield f"data: {json.dumps({'bot': bot_name, 'text': chunk.choices[0].delta.content})}\n\n"
        yield f"data: {json.dumps({'bot': bot_name, 'done': True})}\n\n"
    except Exception as e:
        logger.error(f"Error for {bot_name}: {e}")
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
        session["google_id"] = flow.credentials.to_json() # Storing credentials
        user_info_service = build('oauth2', 'v2', credentials=flow.credentials)
        user_info = user_info_service.userinfo().get().execute()
        session["name"] = user_info.get("name")
        session["picture"] = user_info.get("picture")
        return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return redirect(url_for('login_page'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# --- Main App Routes ---
@app.route("/")
@login_is_required
def index():
    return render_template("index.html", user_name=session.get('name'), user_picture=session.get('picture'))

@app.route("/chat", methods=["POST"])
@login_is_required
def chat():
    # ... (code for chat, same as before)
    pass

@app.route("/upload", methods=["POST"])
@login_is_required
def upload():
    # ... (code for upload, same as before)
    pass
    
@app.route("/asklurk", methods=["POST"])
@login_is_required
def asklurk():
    # ... (code for asklurk, same as before)
    pass
