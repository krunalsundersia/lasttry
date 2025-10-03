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
    logger.error("FATAL: SESSION_SECRET is not set in the .env file. The application cannot run without it.")
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

# Create a client_secret.json file dynamically for the Flow object
client_config = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uris": [REDIRECT_URI],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
}
with open(CLIENT_SECRETS_FILE, 'w') as f:
    json.dump(client_config, f)

flow = Flow.from_client_secrets_file(
    client_secrets_file=CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

# --- Initialize token encoding ---
enc = tiktoken.get_encoding("cl100k_base")
TOKEN_LIMIT = 300_000
tokens_used = 0

# --- Initialize OpenRouter API key ---
KEY = os.getenv("OPENROUTER_API_KEY")
if not KEY:
    logging.error("FATAL: OPENROUTER_API_KEY missing – export it or add to .env")
    sys.exit(1)

# --- Model Definitions ---
MODELS = {
    "logic": {"name": "Logic AI", "description": "analytical, structured, step-by-step"},
    "creative": {"name": "Creative AI", "description": "poetic, metaphorical, emotional"},
    "technical": {"name": "Technical AI", "description": "precise, technical, detail-oriented"},
    "philosophical": {"name": "Philosophical AI", "description": "deep, reflective, abstract"},
    "humorous": {"name": "Humorous AI", "description": "witty, lighthearted, engaging"}
}
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

# --- Create uploads directory ---
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Helper Functions (Your existing functions) ---
def extract_text_from_pdf(file_content):
    # ... (your existing function)
    pass
def process_uploaded_files(files):
    # ... (your existing function)
    pass
def generate(bot_name: str, system: str, user: str, file_contents: list = None):
    # ... (your existing function)
    pass

# --- Decorator to Protect Routes ---
def login_is_required(function):
    def wrapper(*args, **kwargs):
        if "google_id" not in session:
            return redirect(url_for('login_page')) # Redirect to the login page if not logged in
        else:
            return function(*args, **kwargs)
    wrapper.__name__ = function.__name__
    return wrapper

# --- Authentication Routes ---
@app.route("/login")
def login_page():
    # This page is shown to logged-out users
    return render_template("login.html")

@app.route("/auth")
def auth():
    # This route starts the Google login process
    authorization_url, state = flow.authorization_url()
    session["state"] = state
    return redirect(authorization_url)

@app.route("/callback")
def callback():
    # Google redirects here after a successful login
    try:
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        user_info_service = build('oauth2', 'v2', credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()
        
        session["google_id"] = user_info.get("id")
        session["name"] = user_info.get("name")
        session["picture"] = user_info.get("picture")
        
        return redirect(url_for('index')) # Redirect to the main chat app
    except Exception as e:
        logger.error(f"Error during Google callback: {e}")
        return redirect(url_for('login_page'))

@app.route("/logout")
def logout():
    session.clear() # Clear the user's session
    return redirect(url_for('login_page'))

# --- Main App Routes (Now Protected) ---
@app.route("/")
@login_is_required # Decorator protects this page
def index():
    # Now only logged-in users can see this. Pass user info to the template.
    return render_template("index.html", user_name=session.get('name'), user_picture=session.get('picture'))

@app.route("/chat", methods=["POST"])
@login_is_required # Protect this endpoint
def chat():
    # ... (your existing function)
    pass

@app.route("/asklurk", methods=["POST"])
@login_is_required # Protect this endpoint
def asklurk():
    # ... (your existing function)
    pass

@app.route("/upload", methods=["POST"])
@login_is_required # Protect this endpoint
def upload():
    # ... (your existing function)
    pass

# --- Public Routes (No login required) ---
@app.route("/tokens", methods=["GET"])
def get_tokens():
    # ... (your existing function)
    pass

@app.route("/reset-tokens", methods=["POST"])
def reset_tokens():
    # ... (your existing function)
    pass

@app.route("/health", methods=["GET"])
def health():
    # ... (your existing function)
    pass

# --- Main Execution ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    print("Starting Pentad Chat Server...")
    print(f"OpenRouter API Key: {'✓ Configured' if KEY else '✗ Missing'}")
    # ... (rest of your startup prints)
    app.run(host='0.0.0.0', port=port, debug=debug)
