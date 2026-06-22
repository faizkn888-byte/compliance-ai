from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# This creates our "restaurant"
app = FastAPI(
    title="Compliance AI API",
    version="0.1.0",
    description="AI-powered DPDP compliance for Indian businesses"
)

# This lets the frontend talk to the backend (like a phone line between kitchen and counter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # The frontend address
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A simple test — when someone visits /health, we say "I'm alive!"
@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}

# Upload a document
@app.post("/api/v1/documents/upload")
async def upload_document():
    return {
        "id": 1,
        "filename": "test.pdf",
        "status": "pending",
        "message": "Document received. Analysis starting soon."
    }

# Analyze a document (mock for now)
@app.post("/api/v1/compliance/analyze/{document_id}")
def analyze_document(document_id: int):
    return {
        "document_id": document_id,
        "score": 72,
        "status": "Needs Improvement",
        "gaps": [
            {
                "id": "gap-1",
                "regulation": "DPDP Act 2023",
                "section": "Section 8",
                "severity": "high",
                "description": "Missing data breach notification mechanism.",
                "suggestion": "Add a section defining breach notification procedures."
            }
        ],
        "passed": ["Consent mechanism properly defined"]
    }

# Get compliance score
@app.get("/api/v1/compliance/score/{document_id}")
def get_score(document_id: int):
    return {
        "document_id": document_id,
        "overall_score": 72,
        "status": "Needs Improvement",
        "breakdown": [
            {"label": "Consent", "status": "pass", "score": 100},
            {"label": "Data Retention", "status": "warning", "score": 50},
            {"label": "Breach Notification", "status": "fail", "score": 0}
        ]
    }