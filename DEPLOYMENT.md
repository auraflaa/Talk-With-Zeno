# Deployment Guide for Talk With Zeno

This guide covers deploying both the frontend and backend to make the app live.

## Quick Deploy Options

### Option 1: Vercel (Frontend) + Railway (Backend) - Recommended

#### Frontend on Vercel:
1. Push code to GitHub
2. Go to [vercel.com](https://vercel.com)
3. Import your GitHub repository
4. Configure:
   - Framework Preset: Vite
   - Root Directory: `./` (or leave default)
   - Build Command: `npm run build`
   - Output Directory: `dist`
5. Add Environment Variables:
   - `VITE_API_BASE_URL` = Your backend URL (e.g., `https://your-backend.railway.app`)
6. Deploy!

#### Backend on Railway:
1. Go to [railway.app](https://railway.app)
2. New Project → Deploy from GitHub
3. Select your repository
4. Add Environment Variables:
   - `GEMINI_API_KEY` = Your Gemini API key
   - `GROQ_API_KEY` = Your Groq API key (optional, for TTS)
   - `GOOGLE_APPLICATION_CREDENTIALS` = Path to service account JSON (or use Railway secrets)
   - `DATABASE_PATH` = `./data/zeno.db`
   - `PORT` = `5000`
   - `HOST` = `0.0.0.0`
5. Deploy!

### Option 2: Netlify (Frontend) + Render (Backend)

#### Frontend on Netlify:
1. Push code to GitHub
2. Go to [netlify.com](https://netlify.com)
3. New site from Git → Select repository
4. Build settings:
   - Build command: `npm run build`
   - Publish directory: `dist`
5. Add Environment Variables:
   - `VITE_API_BASE_URL` = Your backend URL
6. Deploy!

#### Backend on Render:
1. Go to [render.com](https://render.com)
2. New Web Service → Connect GitHub
3. Configure:
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `python backend/run.py`
4. Add Environment Variables (same as Railway)
5. Deploy!

## Environment Variables Setup

### Frontend (.env.production or Vercel/Netlify settings):
```env
VITE_API_BASE_URL=https://your-backend-url.com
VITE_GOOGLE_CLIENT_ID=your_google_oauth_client_id
```

### Backend (Railway/Render settings):
```env
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
GOOGLE_APPLICATION_CREDENTIALS=./service-account-key.json
DATABASE_PATH=./data/zeno.db
PORT=5000
HOST=0.0.0.0
FLASK_DEBUG=False
```

## Important Notes

1. **CORS**: The backend already has CORS enabled for all origins. For production, you may want to restrict it to your frontend domain.

2. **Google Cloud Credentials**: 
   - Upload your service account JSON file to Railway/Render as a secret
   - Or use environment variable with base64 encoded content

3. **Database**: The SQLite database will be created automatically in the `data/` directory

4. **File Storage**: Chat history and personalization files are stored in `data/` directory. Make sure this persists (Railway/Render handle this automatically)

5. **Update Frontend API URL**: After deploying backend, update `VITE_API_BASE_URL` in frontend deployment settings

## Testing Deployment

1. Check backend health: `https://your-backend-url.com/api/health`
2. Test frontend: Visit your frontend URL
3. Check browser console for any CORS or connection errors

## Troubleshooting

- **CORS Errors**: Update `CORS(app)` in `backend/app.py` to allow your frontend domain
- **Backend Not Starting**: Check logs in Railway/Render dashboard
- **Environment Variables**: Make sure all required variables are set
- **Build Errors**: Check build logs in deployment platform

