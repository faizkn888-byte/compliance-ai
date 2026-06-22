from fastapi import FastAPI, UploadFile, File, Depends, Response, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
import shutil
import os
import io

from sqlalchemy.orm import Session
from PyPDF2 import PdfReader
import docx

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER

from database import get_db, get_password_hash, verify_password, UserDB, DocumentDB, ComplianceGapDB

# JWT Config
SECRET_KEY = "your-super-secret-key-change-this-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

app = FastAPI(
    title="Compliance AI API",
    version="0.4.0",
    description="AI-powered compliance for Indian businesses"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ============== AUTH HELPERS ==============

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(UserDB).filter(UserDB.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

# ============== REGULATIONS ==============

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
    }
}

# ============== HELPERS ==============

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
                "severity": "high" if category in ["Consent", "Breach Notification"] else "medium",
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
        item_score = 100 if found else (0 if category in ["Consent", "Breach Notification"] else 30)
        item_status = "pass" if found else ("fail" if category in ["Consent", "Breach Notification"] else "warning")
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

def generate_fix_policy(original_text: str, gaps: list) -> str:
    fixes = {
        "Consent": "1. CONSENT\nBy using our services, you provide free, specific, informed, unconditional, and unambiguous consent to the collection and processing of your personal data. You may withdraw consent at any time by contacting us.",
        "Notice": "2. NOTICE\nWe collect your personal data for the following specific purposes: [list purposes]. We inform you of the nature of personal data collected, purpose of processing, and your rights before or at the time of collection.",
        "Data Retention": "3. DATA RETENTION\nWe retain personal data only as long as necessary for the specified purpose. Customer data is retained for 3 years after account closure. Financial records are retained for 7 years as required by law. Data is securely deleted thereafter.",
        "Breach Notification": "4. DATA BREACH NOTIFICATION\nIn the event of a personal data breach, we will:\n- Notify the Data Protection Board of India within 72 hours of becoming aware\n- Inform affected data principals without undue delay\n- Document all breaches including facts, effects, and remedial actions taken",
        "Data Principal Rights": "5. DATA PRINCIPAL RIGHTS\nYou have the following rights under the DPDP Act 2023:\n- Right to access your personal data\n- Right to correction and erasure\n- Right to grievance redressal\n- Right to nominate another individual\nTo exercise these rights, contact our Grievance Officer.",
        "Grievance Officer": "6. GRIEVANCE OFFICER\nName: [Insert Name]\nEmail: grievance@company.com\nPhone: [Insert Phone]\nAddress: [Insert Address]\nResponse Time: 30 days from date of receipt",
        "Cross-border Transfer": "7. CROSS-BORDER DATA TRANSFERS\nWe ensure that personal data transferred outside India is subject to adequate protection. We rely on:\n- Government notifications of adequate countries\n- Standard contractual clauses approved by the Data Protection Board\n- Your explicit consent for specific transfers"
    }
    
    fixed_policy = "PRIVACY POLICY\n\nLast Updated: 2024\n\n"
    fixed_policy += original_text[:500] if original_text else ""
    fixed_policy += "\n\n--- COMPLIANCE FIXES ---\n"
    
    for gap in gaps:
        for fix_name, fix_text in fixes.items():
            if fix_name.lower() in gap.get("description", "").lower():
                fixed_policy += fix_text + "\n\n"
    
    fixed_policy += "\n\n--- END OF POLICY ---\n\nThis is a generated template. Please review with your legal counsel before use."
    
    return fixed_policy

def generate_pdf_report(document_name: str, analysis: dict, gaps: list) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Heading1'],
        fontSize=24, textColor=colors.HexColor('#1e40af'),
        spaceAfter=30, alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#1e40af'),
        spaceAfter=12, spaceBefore=12
    )
    
    normal_style = styles["Normal"]
    normal_style.fontSize = 10
    normal_style.leading = 14
    
    story = []
    story.append(Paragraph("DPDP Compliance Report", title_style))
    story.append(Spacer(1, 0.2*inch))
    story.append(Paragraph(f"<b>Document:</b> {document_name}", normal_style))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}", normal_style))
    story.append(Paragraph(f"<b>Regulation:</b> DPDP Act 2023", normal_style))
    story.append(Spacer(1, 0.3*inch))
    
    score = analysis.get("overall_score", 0)
    score_color = colors.green if score >= 80 else colors.orange if score >= 60 else colors.red
    status = "COMPLIANT" if score >= 80 else "NEEDS IMPROVEMENT" if score >= 60 else "NON-COMPLIANT"
    
    score_data = [
        [Paragraph("<b>Compliance Score</b>", normal_style), 
         Paragraph("<b>Status</b>", normal_style)],
        [Paragraph(f"<font size=32 color='{score_color.hexval()}'>{score}%</font>", normal_style),
         Paragraph(f"<font size=16 color='{score_color.hexval()}'>{status}</font>", normal_style)]
    ]
    
    score_table = Table(score_data, colWidths=[3*inch, 3*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('TOPPADDING', (0, 1), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 20),
    ]))
    
    story.append(score_table)
    story.append(Spacer(1, 0.3*inch))
    
    if analysis.get("breakdown"):
        story.append(Paragraph("Score Breakdown", heading_style))
        for item in analysis["breakdown"]:
            color = colors.green if item["score"] >= 80 else colors.orange if item["score"] >= 60 else colors.red
            story.append(Paragraph(f"• <b>{item['label']}</b>: {item['score']}%", normal_style))
        story.append(Spacer(1, 0.2*inch))
    
    if gaps:
        story.append(Paragraph("Compliance Gaps", heading_style))
        story.append(Spacer(1, 0.1*inch))
        
        for gap in gaps:
            severity_color = colors.red if gap["severity"] == "high" else colors.orange if gap["severity"] == "medium" else colors.blue
            
            gap_data = [
                [Paragraph(f"<b>{gap['regulation']} — {gap['section']}</b>", normal_style)],
                [Paragraph(f"<b>Severity:</b> <font color='{severity_color.hexval()}'>{gap['severity'].upper()}</font>", normal_style)],
                [Paragraph(f"<b>Issue:</b> {gap['description']}", normal_style)],
                [Paragraph(f"<b>Recommendation:</b> {gap['suggestion']}", normal_style)]
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
    
    if analysis.get("passed"):
        story.append(Paragraph("Passed Checks", heading_style))
        for item in analysis["passed"]:
            story.append(Paragraph(f"✓ {item}", normal_style))
        story.append(Spacer(1, 0.2*inch))
    
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("<i>This report is generated for informational purposes and does not constitute legal advice. Please consult with a qualified legal professional.</i>", 
                          ParagraphStyle('Footer', parent=normal_style, fontSize=8, textColor=colors.grey)))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.read()

# ============== AUTH ROUTES ==============

@app.post("/api/v1/auth/register")
def register(
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    company_name: str = Form(""),
    db: Session = Depends(get_db),
):
    # Check if user exists
    db_user = db.query(UserDB).filter(UserDB.email == email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(password)
    user = UserDB(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        company_name=company_name
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User created successfully",
        "user_id": user.id,
        "email": user.email
    }

@app.post("/api/v1/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "company_name": user.company_name
        }
    }

@app.get("/api/v1/auth/me")
def get_me(current_user: UserDB = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "company_name": current_user.company_name
    }

# ============== DOCUMENT ROUTES (PROTECTED) ==============

@app.post("/api/v1/documents/upload")
async def upload_document(
    file: UploadFile = File(...), 
    current_user: UserDB = Depends(get_current_user),
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
        status="pending",
        owner_id=current_user.id
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

@app.get("/api/v1/documents")
def list_documents(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = db.query(DocumentDB).filter(DocumentDB.owner_id == current_user.id).all()
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

# ============== COMPLIANCE ROUTES (PROTECTED) ==============

@app.post("/api/v1/compliance/analyze/{document_id}")
def analyze_document(
    document_id: int, 
    regulation: str = "dpdp", 
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(DocumentDB).filter(
        DocumentDB.id == document_id,
        DocumentDB.owner_id == current_user.id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    text = doc.extracted_text or ""
    result = analyze_text_smart(text, regulation)
    
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
def get_score(
    document_id: int, 
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(DocumentDB).filter(
        DocumentDB.id == document_id,
        DocumentDB.owner_id == current_user.id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
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
def generate_fix(
    document_id: int, 
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(DocumentDB).filter(
        DocumentDB.id == document_id,
        DocumentDB.owner_id == current_user.id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    gaps = db.query(ComplianceGapDB).filter(ComplianceGapDB.document_id == document_id).all()
    gaps_list = [{"description": g.description} for g in gaps]
    fixed = generate_fix_policy(doc.extracted_text or "", gaps_list)
    
    return {
        "document_id": document_id,
        "fixed_policy": fixed,
        "gaps_fixed": len(gaps_list)
    }

@app.get("/api/v1/compliance/report/{document_id}")
def download_report(
    document_id: int, 
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    doc = db.query(DocumentDB).filter(
        DocumentDB.id == document_id,
        DocumentDB.owner_id == current_user.id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    gaps = db.query(ComplianceGapDB).filter(ComplianceGapDB.document_id == document_id).all()
    
    analysis = {
        "overall_score": doc.compliance_score or 0,
        "status": "Compliant" if (doc.compliance_score or 0) >= 80 else "Needs Improvement",
        "breakdown": [
            {"label": "Consent", "status": "pass", "score": 100},
            {"label": "Data Retention", "status": "warning", "score": 50},
        ]
    }
    
    gaps_list = [
        {
            "regulation": g.regulation,
            "section": g.section,
            "severity": g.severity,
            "description": g.description,
            "suggestion": g.suggestion
        }
        for g in gaps
    ]
    
    pdf_bytes = generate_pdf_report(doc.original_name, analysis, gaps_list)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=compliance-report-{document_id}.pdf"}
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.4.0"}