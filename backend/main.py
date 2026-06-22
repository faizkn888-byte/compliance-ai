from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import io
from fastapi import Response
from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
import shutil
import os
from sqlalchemy.orm import Session
from PyPDF2 import PdfReader
import docx

from database import get_db, DocumentDB, ComplianceGapDB

app = FastAPI(
    title="Compliance AI API",
    version="0.2.0",
    description="AI-powered compliance for Indian businesses"
)

app.add_middleware(
    CORSMiddleware,
allow_origins=[
    "http://localhost:3000",
    "https://compliance-3vb2wlt7n-faizkn.vercel.app",  # Your actual Vercel URL
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
@app.post("/api/v1/documents/upload")
async def upload_document(
    file: UploadFile = File(...), 
    doc_type: str = "privacy_policy",
    db: Session = Depends(get_db)
):
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    text = extract_text(file_path)
    
    db_doc = DocumentDB(
        filename=file.filename,
        original_name=file.filename,
        extracted_text=text[:10000],
        status="pending"
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    
    return {
        "id": db_doc.id,
        "filename": file.filename,
        "status": "pending",
        "message": f"Saved {file.filename}. Read {len(text)} characters.",
        "type": doc_type
    }
# ============== REGULATIONS DATABASE ==============

REGULATIONS = {
    "dpdp": {
        "name": "DPDP Act 2023",
        "checks": [
            ("Consent", ["consent", "agree", "opt-in", "permission", "authorize"], "Section 5", "Up to ₹250 crore"),
            ("Notice", ["notice", "inform", "purpose", "collection"], "Section 8", "Up to ₹200 crore"),
            ("Data Retention", ["retain", "retention", "delete", "destroy", "storage period"], "Section 8(5)", "Up to ₹150 crore"),
            ("Breach Notification", ["breach", "notification", "incident", "72 hours", "data protection board"], "Section 8(6)", "Up to ₹250 crore"),
            ("Data Principal Rights", ["access", "correction", "erasure", "delete", "grievance", "rights"], "Section 11", "Up to ₹150 crore"),
            ("Grievance Officer", ["grievance officer", "complaint", "redressal", "contact"], "Section 12", "Up to ₹100 crore"),
            ("Cross-border Transfer", ["cross-border", "foreign", "transfer outside india", "adequate protection"], "Section 16", "Up to ₹250 crore"),
        ]
    },
    "rbi_cyber": {
        "name": "RBI Cyber Security Framework",
        "checks": [
            ("Cyber Security Policy", ["cyber security policy", "information security", "infosec"], "Framework 1.1", "Up to ₹5 crore"),
            ("Incident Response", ["incident response", "cyber incident", "security incident"], "Framework 3.1", "Up to ₹2 crore"),
            ("IT Governance", ["it governance", "board oversight", "risk management"], "Framework 2.1", "Up to ₹3 crore"),
            ("Data Localization", ["data localization", "data within india", "domestic storage"], "Framework 5.2", "Up to ₹5 crore"),
        ]
    },
    "cert_in": {
        "name": "CERT-In Directions",
        "checks": [
            ("Incident Reporting", ["cert-in", "report incident", "incident reporting"], "Direction 1", "Up to ₹1 lakh per incident"),
            ("Log Retention", ["log retention", "preserve logs", "180 days"], "Direction 2", "Up to ₹1 lakh"),
            ("Data Breach Timeline", ["6 hours", "report within 6 hours"], "Direction 3", "Up to ₹1 lakh"),
        ]
    }
}

# ============== TEXT EXTRACTION ==============

def extract_text(file_path: str) -> str:
    if file_path.endswith(".pdf"):
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    elif file_path.endswith(".docx"):
        document = docx.Document(file_path)
        text = ""
        for paragraph in document.paragraphs:
            text += paragraph.text + "\n"
        return text
    elif file_path.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

# ============== SMART ANALYSIS ==============

def analyze_text_smart(text: str, regulation_type: str = "dpdp"):
    text_lower = text.lower()
    reg = REGULATIONS.get(regulation_type, REGULATIONS["dpdp"])
    
    gaps = []
    passed = []
    total_score = 0
    
    for category, keywords, section, penalty in reg["checks"]:
        found = any(kw in text_lower for kw in keywords)
        
        if found:
            passed.append(f"{category} properly addressed")
            total_score += int(100 / len(reg["checks"]))
        else:
            gaps.append({
                "regulation": reg["name"],
                "section": section,
                "severity": "high" if category in ["Consent", "Breach Notification", "Cyber Security Policy"] else "medium",
                "description": f"Missing or insufficient {category.lower()} clauses. {category} is required under {reg['name']}.",
                "suggestion": f"Add a dedicated section covering {category.lower()} with specific procedures, timelines, and responsible personnel."
            })
    
    score = min(100, max(0, total_score))
    
    if score >= 80:
        status = "Compliant"
    elif score >= 60:
        status = "Needs Improvement"
    else:
        status = "Non-Compliant"
    
    breakdown = []
    for category, keywords, section, penalty in reg["checks"]:
        found = any(kw in text_lower for kw in keywords)
        item_score = 100 if found else (0 if category in ["Consent", "Breach Notification", "Cyber Security Policy"] else 30)
        item_status = "pass" if found else ("fail" if category in ["Consent", "Breach Notification", "Cyber Security Policy"] else "warning")
        breakdown.append({
            "label": category,
            "status": item_status,
            "score": item_score
        })
    
    return {
        "overall_score": score,
        "status": status,
        "breakdown": breakdown,
        "gaps": gaps,
        "passed": passed,
        "regulation_type": regulation_type
    }

# ============== FIX GENERATOR ==============

def generate_fix_policy(original_text: str, gaps: list) -> str:
    """Generate a basic fixed privacy policy based on gaps found"""
    
    fixes = {
        "Consent": """
1. CONSENT
By using our services, you provide free, specific, informed, unconditional, and unambiguous consent to the collection and processing of your personal data. You may withdraw consent at any time by contacting us.""",
        "Notice": """
2. NOTICE
We collect your personal data for the following specific purposes: [list purposes]. We inform you of the nature of personal data collected, purpose of processing, and your rights before or at the time of collection.""",
        "Data Retention": """
3. DATA RETENTION
We retain personal data only as long as necessary for the specified purpose. Customer data is retained for 3 years after account closure. Financial records are retained for 7 years as required by law. Data is securely deleted thereafter.""",
        "Breach Notification": """
4. DATA BREACH NOTIFICATION
In the event of a personal data breach, we will:
- Notify the Data Protection Board of India within 72 hours of becoming aware
- Inform affected data principals without undue delay
- Document all breaches including facts, effects, and remedial actions taken""",
        "Data Principal Rights": """
5. DATA PRINCIPAL RIGHTS
You have the following rights under the DPDP Act 2023:
- Right to access your personal data
- Right to correction and erasure
- Right to grievance redressal
- Right to nominate another individual
To exercise these rights, contact our Grievance Officer.""",
        "Grievance Officer": """
6. GRIEVANCE OFFICER
Name: [Insert Name]
Email: grievance@company.com
Phone: [Insert Phone]
Address: [Insert Address]
Response Time: 30 days from date of receipt""",
        "Cross-border Transfer": """
7. CROSS-BORDER DATA TRANSFERS
We ensure that personal data transferred outside India is subject to adequate protection. We rely on:
- Government notifications of adequate countries
- Standard contractual clauses approved by the Data Protection Board
- Your explicit consent for specific transfers"""
    }
    
    fixed_policy = "PRIVACY POLICY\n\nLast Updated: 2024\n\n"
    
    # Add original text sections that don't need fixing
    fixed_policy += original_text[:500] if original_text else ""
    fixed_policy += "\n\n--- COMPLIANCE FIXES ---\n"
    
    # Add fixes for each gap
    for gap in gaps:
        category = gap.get("section", "").split(" ")[0] if "section" in gap else ""
        for fix_name, fix_text in fixes.items():
            if fix_name.lower() in gap.get("description", "").lower():
                fixed_policy += fix_text + "\n\n"
    
    fixed_policy += "\n\n--- END OF POLICY ---\n\nThis is a generated template. Please review with your legal counsel before use."
    
    return fixed_policy
def generate_pdf_report(document_name: str, analysis: dict, gaps: list) -> bytes:
    """Generate a professional PDF compliance report"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    normal_style = styles["Normal"]
    normal_style.fontSize = 10
    normal_style.leading = 14
    
    # Build content
    story = []
    
    # Title
    story.append(Paragraph("DPDP Compliance Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Document info
    story.append(Paragraph(f"<b>Document:</b> {document_name}", normal_style))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}", normal_style))
    story.append(Paragraph(f"<b>Regulation:</b> DPDP Act 2023", normal_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Score section
    score = analysis.get("overall_score", 0)
    score_color = colors.green if score >= 80 else colors.orange if score >= 60 else colors.red
    status = "COMPLIANT" if score >= 80 else "NEEDS IMPROVEMENT" if score >= 60 else "NON-COMPLIANT"
    
    score_data = [
        [Paragraph(f"<b>Compliance Score</b>", normal_style), 
         Paragraph(f"<b>Status</b>", normal_style)],
        [Paragraph(f"<font size=32 color={score_color.hexval()}>{score}%</font>", normal_style),
         Paragraph(f"<font size=16 color={score_color.hexval()}>{status}</font>", normal_style)]
    ]
    
    score_table = Table(score_data, colWidths=[3*inch, 3*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('TOPPADDING', (0, 1), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 20),
    ]))
    
    story.append(score_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Gaps section
    if gaps:
        story.append(Paragraph("Compliance Gaps", heading_style))
        story.append(Spacer(1, 0.1*inch))
        
        for gap in gaps:
            severity_color = colors.red if gap.severity == "high" else colors.orange if gap.severity == "medium" else colors.blue
            
            gap_data = [
                [Paragraph(f"<b>{gap.regulation} — {gap.section}</b>", normal_style)],
                [Paragraph(f"<b>Severity:</b> <font color={severity_color.hexval()}>{gap.severity.upper()}</font>", normal_style)],
                [Paragraph(f"<b>Issue:</b> {gap.description}", normal_style)],
                [Paragraph(f"<b>Recommendation:</b> {gap.suggestion}", normal_style)]
            ]
            
            gap_table = Table(gap_data, colWidths=[6*inch])
            gap_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fef2f2')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#fee2e2')),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            story.append(gap_table)
            story.append(Spacer(1, 0.15*inch))
    
    # Footer
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("<i>This report is generated for informational purposes and does not constitute legal advice. Please consult with a qualified legal professional.</i>", 
                          ParagraphStyle('Footer', parent=normal_style, fontSize=8, textColor=colors.grey)))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.read()
# ============== ROUTES ==============

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.2.0"}

@app.get("/api/v1/regulations")
def list_regulations():
    return {
        "available": [
            {"id": "dpdp", "name": "DPDP Act 2023", "checks": 7},
            {"id": "rbi_cyber", "name": "RBI Cyber Security Framework", "checks": 4},
            {"id": "cert_in", "name": "CERT-In Directions", "checks": 3},
        ]
    }

@app.post("/api/v1/documents/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    text = extract_text(file_path)
    
    db_doc = DocumentDB(
        filename=file.filename,
        original_name=file.filename,
        extracted_text=text[:10000],
        status="pending"
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    
    return {
        "id": db_doc.id,
        "filename": file.filename,
        "status": "pending",
        "message": f"Saved {file.filename}. Read {len(text)} characters."
    }

@app.post("/api/v1/compliance/analyze/{document_id}")
def analyze_document(document_id: int, regulation: str = "dpdp", db: Session = Depends(get_db)):
    doc = db.query(DocumentDB).filter(DocumentDB.id == document_id).first()
    if not doc:
        return {"error": "Document not found"}
    
    text = doc.extracted_text or ""
    result = analyze_text_smart(text, regulation)
    
    # Clear old gaps
    db.query(ComplianceGapDB).filter(ComplianceGapDB.document_id == document_id).delete()
    
    for gap in result["gaps"]:
        db_gap = ComplianceGapDB(
            document_id=document_id,
            regulation=gap["regulation"],
            section=gap["section"],
            severity=gap["severity"],
            description=gap["description"],
            suggestion=gap["suggestion"]
        )
        db.add(db_gap)
    
    doc.compliance_score = result["overall_score"]
    doc.status = "completed"
    db.commit()
    
    return {
        "document_id": document_id,
        "score": result["overall_score"],
        "status": result["status"],
        "breakdown": result["breakdown"],
        "gaps": result["gaps"],
        "passed": result["passed"]
    }

@app.get("/api/v1/compliance/score/{document_id}")
def get_score(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentDB).filter(DocumentDB.id == document_id).first()
    gaps = db.query(ComplianceGapDB).filter(ComplianceGapDB.document_id == document_id).all()
    
    if not doc:
        return {"error": "Document not found"}
    
    return {
        "document_id": document_id,
        "overall_score": doc.compliance_score or 0,
        "status": "Compliant" if (doc.compliance_score or 0) >= 80 else "Needs Improvement" if (doc.compliance_score or 0) >= 60 else "Non-Compliant",
        "breakdown": [
            {"label": "Consent", "status": "pass", "score": 100},
            {"label": "Data Retention", "status": "warning", "score": 50},
            {"label": "Breach Notification", "status": "fail", "score": 0},
        ]
    }

@app.post("/api/v1/compliance/generate-fix/{document_id}")
def generate_fix(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentDB).filter(DocumentDB.id == document_id).first()
    gaps = db.query(ComplianceGapDB).filter(ComplianceGapDB.document_id == document_id).all()
    
    if not doc:
        return {"error": "Document not found"}
    
    gaps_list = [
        {
            "regulation": g.regulation,
            "section": g.section,
            "description": g.description,
            "suggestion": g.suggestion
        }
        for g in gaps
    ]
    
    fixed = generate_fix_policy(doc.extracted_text or "", gaps_list)
    
    return {
        "document_id": document_id,
        "fixed_policy": fixed,
        "gaps_fixed": len(gaps_list)
    }

@app.get("/api/v1/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(DocumentDB).all()
    return [
        {
            "id": d.id,
            "name": d.original_name,
            "status": d.status,
            "score": d.compliance_score,
            "uploadedAt": d.created_at.isoformat() if d.created_at else ""
        }
        for d in docs
    ]
@app.get("/api/v1/compliance/report/{document_id}")
def download_report(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentDB).filter(DocumentDB.id == document_id).first()
    gaps = db.query(ComplianceGapDB).filter(ComplianceGapDB.document_id == document_id).all()
    
    if not doc:
        return {"error": "Document not found"}
    
    analysis = {
        "overall_score": doc.compliance_score or 0,
        "status": "Compliant" if (doc.compliance_score or 0) >= 80 else "Needs Improvement"
    }
    
    gaps_list = [
        type('Gap', (), {
            'regulation': g.regulation,
            'section': g.section,
            'severity': g.severity,
            'description': g.description,
            'suggestion': g.suggestion
        })()
        for g in gaps
    ]
    
    pdf_bytes = generate_pdf_report(doc.original_name, analysis, gaps_list)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=compliance-report-{document_id}.pdf"}
    )