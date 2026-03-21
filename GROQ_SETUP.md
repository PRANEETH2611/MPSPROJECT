# 🚀 Groq API Setup Guide

## ✅ Step 1: Get Your FREE Groq API Key

1. Go to: **https://console.groq.com**
2. Sign up (it's FREE - no credit card needed!)
3. Click **"API Keys"** in the left menu
4. Click **"Create API Key"**
5. Copy the key (starts with `gsk_...`)

---

## ✅ Step 2: Add API Key to .env

Open `.env` file and replace:
```
GROQ_API_KEY=your_groq_api_key_here
```

With your actual key:
```
GROQ_API_KEY=gsk_abc123xyz...
```

---

## ✅ Step 3: Install Groq Package

```powershell
pip install groq
```

---

## ✅ Step 4: Test It!

```powershell
python -c "from backend.groq_service import groq_service; print(groq_service.chat('Hello!'))"
```

---

## 🎯 What You Can Do Now:

### **1. Anomaly Analysis**
```python
from backend.groq_service import groq_service

analysis = groq_service.analyze_anomaly(
    metric="cpu_usage",
    value="95%",
    threshold="80%",
    recent_logs="ERROR: OutOfMemoryError"
)

print(analysis['root_cause'])
print(analysis['recommendations'])
```

### **2. Interactive Chat**
```python
response = groq_service.chat("How do I fix high CPU usage?")
print(response)
```

### **3. Generate Runbooks**
```python
runbook = groq_service.generate_runbook("High Memory Usage")
print(runbook)
```

---

## ⚡ Groq vs Gemini

| Feature | Groq | Gemini |
|---------|------|--------|
| **Speed** | ⚡ 10x faster | 🐌 Slow |
| **Free Tier** | ✅ 30 req/min | ❌ Very limited |
| **Models** | Llama 3.1 70B | Gemini 1.5 |
| **Cost** | 🆓 FREE | 💰 Paid after quota |

---

## 🛠️ Next Steps:

Once you have your API key:
1. Add it to `.env`
2. Restart your backend: `python backend\app.py`
3. Look for: `✅ Groq AI Service initialized`
4. Use it in Command Center!

**Questions?** Let me know! 🚀
