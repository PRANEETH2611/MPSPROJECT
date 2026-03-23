# AIOps Dashboard - Architecture Guide

## Two Approaches Available

### 1. **Streamlit (Monolithic) - Current `dashboard/app.py`**
   - **Frontend + Backend**: Combined in one Python file
   - **Pros**: Quick to develop, no separate frontend needed
   - **Cons**: Less flexible, harder to customize UI
   - **Run**: `streamlit run dashboard/app.py`

### 2. **Separated Frontend/Backend - NEW!**

#### **Backend** (`backend/app.py`)
   - **Technology**: Flask REST API
   - **Port**: 5000
   - **Endpoints**:
     - `GET /api/health` - Health check
     - `POST /api/login` - User authentication
     - `GET /api/data` - Get filtered dashboard data
     - `GET /api/kpi` - Get KPI metrics
     - `GET /api/analytics` - Get analytics data
     - `GET /api/insights` - Get AI insights
     - `GET /api/options` - Get filter options
   - **Run**: `python backend/app.py`

#### **Frontend** (`frontend/`)
   - **Technology**: HTML5 + CSS3 + JavaScript (Vanilla JS)
   - **Charts**: Plotly.js (CDN)
   - **Files**:
     - `index.html` - Main HTML structure
     - `styles.css` - Modern CSS styling
     - `app.js` - JavaScript logic and API calls
   - **Run**: Open `frontend/index.html` in browser (or use a local server)
   - **Launcher**: `python run_all.py`

## How to Run Separated Version

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start Backend
```bash
python backend/app.py
```
Backend will run on `http://localhost:5000`

### Optional: Start Backend + Frontend Together
```bash
python run_all.py
```
This starts the Flask backend and a lightweight static file server for `frontend/`.

### Step 3: Open Frontend
Option A: Direct file open
- Open `frontend/index.html` in your browser

Option B: Using Python HTTP server (recommended)
```bash
cd frontend
python -m http.server 8000
```
Then open `http://localhost:8000` in browser

## Architecture Comparison

| Feature | Streamlit | Separated F/B |
|---------|-----------|---------------|
| Development Speed | ⚡ Fast | 🐢 Slower |
| UI Customization | ⚠️ Limited | ✅ Full Control |
| Scalability | ⚠️ Limited | ✅ Better |
| Frontend Skills Needed | ❌ No | ✅ Yes |
| Backend Skills Needed | ✅ Python Only | ✅ Python + JS |
| Deployment | ✅ Easy | ⚠️ More Complex |
| API Access | ❌ No | ✅ Yes |

## Which Should You Use?

- **Use Streamlit** if:
  - Quick prototyping
  - Python-only team
  - Simple dashboard needs
  - Internal tools

- **Use Separated F/B** if:
  - Need custom UI/UX
  - Want to integrate with other systems
  - Need API access
  - Professional production app
  - Frontend/Backend separation required

## API Documentation

### Login
```javascript
POST /api/login
Body: { "username": "admin", "password": "admin123" }
Response: { "success": true, "username": "admin", "role": "ADMIN" }
```

### Get Data
```javascript
GET /api/data?alert_status=ALL&root_cause=ALL&window=250&start_date=2025-01-01&end_date=2025-01-31
Response: { "success": true, "data": [...], "latest": {...}, "statistics": {...} }
```

### Get KPIs
```javascript
GET /api/kpi?window=250
Response: { "success": true, "kpi": {...} }
```

## Notes

- Both versions use the same data source: `data/processed/final_decision_output.csv`
- Backend CORS is enabled for frontend access
- Frontend uses localStorage for session management
- Charts use Plotly.js for interactive visualizations
