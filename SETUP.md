# ARIA AI Interview System — Setup Guide

## 1. Environment Variables (.env)

Create a `.env` file in the project root (or copy `.env.example`). Example values for local development:

```
# --- Backend ---
SECRET_KEY=dev-secret-key
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
REDIS_URL=redis://localhost:6379/0
BCRYPT_ROUNDS=12

# Recruiter credentials (JSON: username:plaintext_password)
RECRUITER_CREDENTIALS={"recruiter1": "supersecret1", "recruiter2": "supersecret2"}

# Tavily API
TAVILY_API_KEY=your-tavily-api-key

# ElevenLabs API
ELEVENLABS_API_KEY=your-elevenlabs-api-key
ELEVENLABS_VOICE_ID=your-elevenlabs-voice-id

# Gemini LLM (Google AI Studio)
GEMINI_API_KEY=your-gemini-api-key

# Whisper (if using OpenAI Whisper)
OPENAI_API_KEY=your-openai-api-key

# --- Frontend ---
VITE_API_URL=http://localhost:8000
VITE_WEBSOCKET_URL=ws://localhost:8000/ws

# --- Misc ---
ENV=development
```

## 2. Backend Setup

```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## 3. Frontend Setup

```
cd frontend
npm install
npm run dev
```

## 4. First Login Credentials

- **Username:** recruiter1
- **Password:** supersecret1

## 5. End-to-End Test Flow

1. Go to http://localhost:5173/login
2. Login as recruiter1 / supersecret1
3. Upload a Job Description PDF
4. Generate an invite link for the applicant
5. Open the invite link in a new browser (incognito or different browser)
6. Start the interview as the applicant

## 6. Required External API Keys

- **Gemini API key:**  
  Get free at https://aistudio.google.com/app/apikey  
  Set `GEMINI_API_KEY` in your .env
- **Tavily API key:**  
  Get free at https://app.tavily.com/api-keys  
  Set `TAVILY_API_KEY` in your .env
- **ElevenLabs API key:**  
  Get free at https://elevenlabs.io/  
  Set `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` in your .env
