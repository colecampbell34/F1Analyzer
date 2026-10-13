import os

from dotenv import load_dotenv


load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
AI_ENABLED = bool(GEMINI_API_KEY)

GEMINI_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.6-flash',
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite',
]
