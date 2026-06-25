from fastapi import FastAPI, UploadFile, File, Depends, Response, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import shutil
import os
import io
import re
from pathlib import Path

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

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "https://compliance-ai-xi.vercel.app",
]
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
] or DEFAULT_CORS_ORIGINS

mail_config = ConnectionConfig(
    MAIL_USERNAME="your-email@gmail.com",
    MAIL_PASSWORD="your-app-password",
    MAIL_FROM="your-email@gmail.com",
    MAIL_PORT=587,
    MAIL_SERVER="smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True
)

fm = FastMail(mail_config)


app = FastAPI(
    title="Compliance AI API",
    version="0.5.0",
    description="AI-powered compliance with actionable implementation guidance"
)

# CORS MUST BE FIRST - before any routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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
        "region": "India",
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
        "region": "India",
        "checks": [
            ("Cyber Security Policy", ["cyber security policy", "information security", "infosec"], "Framework 1.1", "Up to â‚¹5 crore"),
            ("Incident Response", ["incident response", "cyber incident", "security incident"], "Framework 3.1", "Up to â‚¹2 crore"),
            ("IT Governance", ["it governance", "board oversight", "risk management"], "Framework 2.1", "Up to â‚¹3 crore"),
            ("Data Localization", ["data localization", "data within india", "domestic storage"], "Framework 5.2", "Up to â‚¹5 crore"),
            ("Access Control", ["access control", "privileged access", "user authentication"], "Framework 4.1", "Up to â‚¹2 crore"),
        ]
    },
    "cert_in": {
        "name": "CERT-In Directions",
        "region": "India",
        "checks": [
            ("Incident Reporting", ["cert-in", "report incident", "incident reporting"], "Direction 1", "Up to â‚¹1 lakh per incident"),
            ("Log Retention", ["log retention", "preserve logs", "180 days"], "Direction 2", "Up to â‚¹1 lakh"),
            ("Data Breach Timeline", ["6 hours", "report within 6 hours"], "Direction 3", "Up to â‚¹1 lakh"),
            ("KYC Data Protection", ["kyc", "customer data protection"], "Direction 4", "Up to â‚¹5 lakh"),
        ]
    },
    "gdpr": {
        "name": "GDPR (EU)",
        "region": "Europe",
        "checks": [
            ("Lawful Basis", ["lawful basis", "legal basis", "legitimate interest", "contractual necessity"], "Article 6", "Up to â‚¬20M or 4% global turnover"),
            ("Consent Requirements", ["explicit consent", "withdraw consent", "freely given"], "Article 7", "Up to â‚¬20M or 4% global turnover"),
            ("Data Subject Rights", ["right to access", "right to erasure", "right to portability", "data portability"], "Articles 15-22", "Up to â‚¬20M or 4% global turnover"),
            ("Privacy by Design", ["privacy by design", "data protection by design", "default privacy"], "Article 25", "Up to â‚¬10M or 2% global turnover"),
            ("Breach Notification", ["72 hours", "supervisory authority", "data protection authority"], "Article 33", "Up to â‚¬10M or 2% global turnover"),
            ("DPO Requirement", ["data protection officer", "dpo"], "Article 37", "Up to â‚¬10M or 2% global turnover"),
            ("Cross-border Transfers", ["adequacy decision", "standard contractual clauses", "scc", "binding corporate rules"], "Chapter V", "Up to â‚¬20M or 4% global turnover"),
        ]
    },
    "ccpa": {
        "name": "CCPA/CPRA (California)",
        "region": "United States",
        "checks": [
            ("Consumer Rights", ["consumer rights", "right to know", "right to delete", "right to opt-out"], "Section 1798.100", "Up to $7,500 per violation"),
            ("Privacy Notice", ["privacy notice", "notice at collection", "categories of personal information"], "Section 1798.130", "Up to $2,500 per violation"),
            ("Opt-Out Rights", ["opt-out", "do not sell", "do not share", "sale of personal information"], "Section 1798.120", "Up to $7,500 per violation"),
            ("Service Provider Contracts", ["service provider", "contractor", "third party"], "Section 1798.140", "Up to $2,500 per violation"),
            ("Data Security", ["reasonable security", "security measures", "safeguards"], "Civil Code 1798.81.5", "Up to $7,500 per violation"),
        ]
    },
    "hipaa": {
        "name": "HIPAA (US Healthcare)",
        "region": "United States",
        "checks": [
            ("Privacy Rule", ["phi", "protected health information", "minimum necessary"], "45 CFR 164", "Up to $1.5M per violation"),
            ("Security Rule", ["administrative safeguards", "technical safeguards", "physical safeguards"], "45 CFR 164.308", "Up to $1.5M per violation"),
            ("Breach Notification", ["breach notification", "60 days", "hhs"], "45 CFR 164.404", "Up to $1.5M per violation"),
            ("Business Associate Agreements", ["business associate", "baa", "covered entity"], "45 CFR 164.504", "Up to $1.5M per violation"),
        ]
    }
}

# ---------- TECH STACK DETECTION REGISTRY ----------
TECH_STACK_PATTERNS = {
    "google_analytics_4": {
        "keywords": ["google analytics", "gtag", "ga4", "gtag('config'", "analytics.js", "googleanalytics", "measurement id"],
        "category": "analytics", "data_types": ["ip_address", "device_info", "browsing_behavior", "user_id", "location"],
        "third_party": True, "cross_border": True,
    },
    "google_tag_manager": {
        "keywords": ["google tag manager", "gtm-", "googletagmanager", "gtm.start"],
        "category": "tag_manager", "data_types": ["script_injection", "third_party_tags"],
        "third_party": True, "cross_border": True,
    },
    "meta_pixel": {
        "keywords": ["facebook pixel", "meta pixel", "fbq('track'", "fbq('init'", "connect.facebook.net"],
        "category": "advertising", "data_types": ["ip_address", "behavior", "conversion_data", "device_info"],
        "third_party": True, "cross_border": True,
    },
    "hotjar": {
        "keywords": ["hotjar", "hjid", "hjscript"],
        "category": "analytics", "data_types": ["session_recordings", "click_behavior", "ip_address"],
        "third_party": True, "cross_border": True,
    },
    "mixpanel": {
        "keywords": ["mixpanel", "mp.track"],
        "category": "analytics", "data_types": ["user_events", "ip_address", "device_info"],
        "third_party": True, "cross_border": True,
    },
    "stripe": {
        "keywords": ["stripe", "stripe.js", "stripe.com", "paymentintent"],
        "category": "payment", "data_types": ["payment_data", "card_tokens", "billing_address"],
        "third_party": True, "cross_border": True, "financial_regulation": True,
    },
    "razorpay": {
        "keywords": ["razorpay", "razorpay.com", "rzp_"],
        "category": "payment", "data_types": ["payment_data", "upi_id", "billing_address"],
        "third_party": True, "cross_border": False, "financial_regulation": True,
    },
    "aws_s3": {
        "keywords": ["s3.amazonaws.com", "aws s3", "boto3", "s3 bucket", "s3://"],
        "category": "cloud_storage", "data_types": ["file_storage", "backups", "user_uploads"],
        "third_party": True, "cross_border": True,
    },
    "aws_cloudfront": {
        "keywords": ["cloudfront", "cloudfront.net", "cdn"],
        "category": "cdn", "data_types": ["access_logs", "ip_address", "cache_data"],
        "third_party": True, "cross_border": True,
    },
    "aws_rds": {
        "keywords": ["aws rds", "rds.amazonaws.com", "postgresql", "mysql"],
        "category": "database", "data_types": ["user_data", "transaction_logs", "personal_data"],
        "third_party": True, "cross_border": True,
    },
    "aws_ec2": {
        "keywords": ["ec2", "ec2.amazonaws.com", "aws instance"],
        "category": "compute", "data_types": ["server_logs", "application_logs"],
        "third_party": True, "cross_border": True,
    },
    "gcp_cloud_storage": {
        "keywords": ["google cloud storage", "storage.googleapis.com", "gcs bucket"],
        "category": "cloud_storage", "data_types": ["file_storage", "backups"],
        "third_party": True, "cross_border": True,
    },
    "firebase": {
        "keywords": ["firebase", "firebaseapp", "firebase.google.com", "firestore"],
        "category": "backend", "data_types": ["user_data", "authentication_data", "analytics"],
        "third_party": True, "cross_border": True,
    },
    "postgresql": {
        "keywords": ["postgresql", "postgres", "psycopg2", "pg_", "sequelize"],
        "category": "database", "data_types": ["user_data", "transaction_data", "personal_data"],
        "third_party": False, "cross_border": False,
    },
    "mongodb": {
        "keywords": ["mongodb", "mongoose", "mongo", " ObjectId"],
        "category": "database", "data_types": ["user_data", "document_data"],
        "third_party": False, "cross_border": False,
    },
    "mysql": {
        "keywords": ["mysql", "mariadb", "innodb"],
        "category": "database", "data_types": ["user_data", "transaction_data"],
        "third_party": False, "cross_border": False,
    },
    "openai_api": {
        "keywords": ["openai", "chatgpt", "gpt-4", "gpt-3.5", "openai.com", "completions"],
        "category": "ai", "data_types": ["user_inputs", "conversation_history", "personal_data"],
        "third_party": True, "cross_border": True, "automated_decision": True,
    },
    "anthropic_claude": {
        "keywords": ["anthropic", "claude", "claude-3", "claude.ai"],
        "category": "ai", "data_types": ["user_inputs", "conversation_history"],
        "third_party": True, "cross_border": True, "automated_decision": True,
    },
    "auth0": {
        "keywords": ["auth0", "auth0.com", "auth0-spa-js"],
        "category": "authentication", "data_types": ["identity_data", "login_logs", "mfa_data"],
        "third_party": True, "cross_border": True,
    },
    "clerk": {
        "keywords": ["clerk", "clerk.dev", "clerk-js"],
        "category": "authentication", "data_types": ["identity_data", "session_data"],
        "third_party": True, "cross_border": True,
    },
    "mailchimp": {
        "keywords": ["mailchimp", "mailchimp.com", "mcapi", "audience"],
        "category": "marketing", "data_types": ["email", "name", "marketing_preferences"],
        "third_party": True, "cross_border": True,
    },
    "sendgrid": {
        "keywords": ["sendgrid", "twilio sendgrid", "sendgrid.com"],
        "category": "marketing", "data_types": ["email", "delivery_logs"],
        "third_party": True, "cross_border": True,
    },
    "hubspot": {
        "keywords": ["hubspot", "hubspot.com", "hs_", "hubspotutk"],
        "category": "crm", "data_types": ["contact_data", "behavior", "email"],
        "third_party": True, "cross_border": True,
    },
    "react": {
        "keywords": ["react", "react-dom", "jsx", "create-react-app", "next.js"],
        "category": "frontend", "data_types": ["client_state", "local_storage"],
        "third_party": False, "cross_border": False,
    },
    "nextjs": {
        "keywords": ["next.js", "nextjs", "next/", "getserversideprops", "app router"],
        "category": "frontend", "data_types": ["server_logs", "client_state", "local_storage"],
        "third_party": False, "cross_border": False,
    },
    "nodejs": {
        "keywords": ["node.js", "nodejs", "express", "fastify", "koa", "require("],
        "category": "backend", "data_types": ["server_logs", "application_logs"],
        "third_party": False, "cross_border": False,
    },
    "python": {
        "keywords": ["python", "fastapi", "flask", "django", "import "],
        "category": "backend", "data_types": ["server_logs", "application_logs"],
        "third_party": False, "cross_border": False,
    },
    "docker": {
        "keywords": ["docker", "dockerfile", "docker-compose", "container"],
        "category": "infrastructure", "data_types": ["container_logs", "image_data"],
        "third_party": False, "cross_border": False,
    },
    "kubernetes": {
        "keywords": ["kubernetes", "k8s", "kubectl", "pod", "deployment"],
        "category": "infrastructure", "data_types": ["cluster_logs", "audit_logs"],
        "third_party": False, "cross_border": False,
    },
}

# ---------- COMPLIANCE RULES ENGINE ----------
COMPLIANCE_RULES = {
    "dpdp": {
        "google_analytics_4": {
            "consent_required": True, "consent_type": "free_specific_informed_unambiguous",
            "default_state": "blocked", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "data_localization_note": "Consider storing analytics data in India or ensuring adequate safeguards for cross-border transfer under Section 16",
            "retention_guidance": "IP addresses in logs: 30 days max for security, 14 days for analytics. Anonymize after collection.",
            "dark_pattern_checks": ["pre_ticked", "bundled_consent", "passive_consent"],
            "penalty": "Up to ₹250 crore",
        },
        "meta_pixel": {
            "consent_required": True, "consent_type": "explicit_opt_in",
            "default_state": "blocked", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "data_localization_note": "Cross-border transfer to Meta (US) requires explicit consent or government notification under Section 16",
            "retention_guidance": "Event data: retain only as long as campaign attribution requires. Delete after 26 months per Meta's policy, or sooner if user withdraws consent.",
            "dark_pattern_checks": ["pre_ticked", "bundled_consent", "passive_consent", "unequal_buttons"],
            "penalty": "Up to ₹250 crore",
        },
        "stripe": {
            "consent_required": False, "consent_type": "contractual_necessity",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "data_localization_note": "Payment data: RBI mandates card data must be stored with PA/PG compliant entities. Ensure tokenization.",
            "retention_guidance": "Payment records: 7 years (Income Tax Act). Tokenized card data: per RBI PA/PG guidelines (typically 1 year post-transaction).",
            "dark_pattern_checks": [], "penalty": "Up to ₹200 crore + RBI penalties",
        },
        "aws_s3": {
            "consent_required": False, "consent_type": "legitimate_interest",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "data_localization_note": "If storing personal data of Indian users, ensure S3 bucket region is ap-south-1 (Mumbai) or ensure adequate cross-border safeguards.",
            "retention_guidance": "User uploads: retain only during service + 1 year. Server access logs: 30 days, then transition to Glacier and delete after 90 days.",
            "dark_pattern_checks": [], "penalty": "Up to ₹150 crore",
        },
        "aws_cloudfront": {
            "consent_required": False, "consent_type": "legitimate_interest_security",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "data_localization_note": "CDN logs may transit outside India. Ensure logs containing personal data are stored in ap-south-1.",
            "retention_guidance": "Access logs: 30 days in S3, then delete. Real-time logs: 7 days in CloudWatch.",
            "dark_pattern_checks": [], "penalty": "Up to ₹150 crore",
        },
        "openai_api": {
            "consent_required": True, "consent_type": "explicit_opt_in",
            "default_state": "blocked", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "data_localization_note": "User inputs sent to OpenAI (US) constitute cross-border transfer. Requires explicit consent or adequacy determination.",
            "retention_guidance": "API inputs/outputs: OpenAI retains for 30 days for abuse monitoring. Implement your own 30-day retention max.",
            "dark_pattern_checks": ["hidden_ai_use", "no_human_review_option"],
            "penalty": "Up to ₹250 crore",
            "special_note": "Under DPDP, if AI makes decisions affecting the data principal, you must disclose logic + provide human review option.",
        },
        "postgresql": {
            "consent_required": False, "consent_type": "legitimate_interest",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "data_localization_note": "Database must be encrypted at rest (AES-256) and in transit (TLS 1.2+). If hosted outside India, ensure Section 16 compliance.",
            "retention_guidance": "User account data: duration of service + 1 year. Deleted account data: purge within 90 days. Audit logs: 1 year.",
            "dark_pattern_checks": [], "penalty": "Up to ₹150 crore",
        },
        "mailchimp": {
            "consent_required": True, "consent_type": "free_specific_informed_unambiguous",
            "default_state": "blocked", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "data_localization_note": "Email data transferred to Mailchimp (US). Requires explicit consent or SCCs.",
            "retention_guidance": "Email lists: retain only while subscription is active. Unsubscribed users: delete within 30 days. Campaign analytics: 1 year.",
            "dark_pattern_checks": ["pre_ticked", "bundled_consent", "passive_consent"],
            "penalty": "Up to ₹200 crore",
        },
    },
    "gdpr": {
        "google_analytics_4": {
            "consent_required": True, "consent_type": "explicit_opt_in",
            "default_state": "denied", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "consent",
            "retention_guidance": "IP in GA4: enable IP anonymization. Raw logs: 26 months max. User-level data: delete when consent withdrawn.",
            "dark_pattern_checks": ["pre_ticked", "bundled_consent", "passive_consent", "nudging"],
            "penalty": "Up to €20M or 4% global turnover",
            "implementation": {"consent_mode_v2": True, "required_signals": ["ad_storage", "analytics_storage", "ad_user_data", "ad_personalization"]},
        },
        "meta_pixel": {
            "consent_required": True, "consent_type": "explicit_opt_in",
            "default_state": "denied", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "consent",
            "retention_guidance": "Pixel event data: 26 months max. Delete upon opt-out.",
            "dark_pattern_checks": ["pre_ticked", "bundled_consent", "passive_consent", "unequal_buttons"],
            "penalty": "Up to €20M or 4% global turnover",
        },
        "stripe": {
            "consent_required": False, "consent_type": "contractual_necessity",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "lawful_basis": "contract",
            "retention_guidance": "Payment records: 7+ years (tax law). Tokenized data: per PCI-DSS (1 year post-transaction).",
            "dark_pattern_checks": [], "penalty": "Up to €10M or 2% global turnover",
        },
        "aws_s3": {
            "consent_required": False, "consent_type": "legitimate_interest",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "lawful_basis": "legitimate_interest",
            "retention_guidance": "Access logs: 30 days. User data: duration of service + 1 year. Implement automated lifecycle policies.",
            "dark_pattern_checks": [], "penalty": "Up to €10M or 2% global turnover",
        },
        "openai_api": {
            "consent_required": True, "consent_type": "explicit_opt_in",
            "default_state": "blocked", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "consent",
            "retention_guidance": "API inputs: 30 days max (OpenAI abuse monitoring). Your copy: delete within 30 days. Document no-training opt-out.",
            "dark_pattern_checks": ["hidden_ai_use", "no_human_review_option", "automated_decision_without_disclosure"],
            "penalty": "Up to €20M or 4% global turnover",
            "special_note": "If AI makes decisions with legal/significant effects (Art. 22), requires DPIA, human review, and right to contest.",
        },
        "postgresql": {
            "consent_required": False, "consent_type": "legitimate_interest",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "lawful_basis": "legitimate_interest",
            "retention_guidance": "Personal data: duration of service + 1 year. Pseudonymize where possible. Enable row-level security.",
            "dark_pattern_checks": [], "penalty": "Up to €10M or 2% global turnover",
        },
        "mailchimp": {
            "consent_required": True, "consent_type": "explicit_opt_in",
            "default_state": "denied", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "consent",
            "retention_guidance": "Subscribers: while active. Unsubscribed: 30 days. Bounce/complaint records: 1 year.",
            "dark_pattern_checks": ["pre_ticked", "bundled_consent", "passive_consent", "nudging"],
            "penalty": "Up to €20M or 4% global turnover",
        },
    },
    "ccpa": {
        "google_analytics_4": {
            "consent_required": False, "consent_type": "opt_out",
            "default_state": "allowed", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "opt_out_right",
            "retention_guidance": "Honor GPC (Global Privacy Control) signal. Delete data within 45 days of deletion request.",
            "dark_pattern_checks": ["difficult_opt_out", "dark_patterns"],
            "penalty": "Up to $7,500 per violation",
            "special_note": "Must provide 'Do Not Sell or Share My Personal Information' link if sharing with Google for advertising purposes.",
        },
        "meta_pixel": {
            "consent_required": False, "consent_type": "opt_out",
            "default_state": "allowed", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "opt_out_right",
            "retention_guidance": "Honor opt-out within 15 days. Delete data within 45 days of request.",
            "dark_pattern_checks": ["difficult_opt_out", "dark_patterns", "unequal_buttons"],
            "penalty": "Up to $7,500 per violation",
            "special_note": "Meta Pixel is considered 'sharing' under CPRA. Must provide opt-out link and honor GPC.",
        },
        "stripe": {
            "consent_required": False, "consent_type": "necessary",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "lawful_basis": "contract",
            "retention_guidance": "Financial records: 7+ years. Tokenized data: per PCI-DSS.",
            "dark_pattern_checks": [], "penalty": "Up to $2,500 per violation",
        },
        "aws_s3": {
            "consent_required": False, "consent_type": "necessary",
            "default_state": "allowed", "must_provide_withdrawal": False,
            "lawful_basis": "necessary",
            "retention_guidance": "Access logs: 30 days. User data: delete within 45 days of consumer request.",
            "dark_pattern_checks": [], "penalty": "Up to $2,500 per violation",
        },
        "openai_api": {
            "consent_required": False, "consent_type": "opt_out",
            "default_state": "allowed", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "opt_out_right",
            "retention_guidance": "Delete within 45 days of request. Disclose AI use in privacy policy.",
            "dark_pattern_checks": ["hidden_ai_use"],
            "penalty": "Up to $7,500 per violation",
            "special_note": "If AI is used for profiling with legal/significant effects, enhanced disclosure required.",
        },
        "mailchimp": {
            "consent_required": False, "consent_type": "opt_out",
            "default_state": "allowed", "must_provide_withdrawal": True, "withdrawal_as_easy": True,
            "lawful_basis": "opt_out_right",
            "retention_guidance": "Unsubscribe: immediate. Delete data: within 45 days of request.",
            "dark_pattern_checks": ["difficult_opt_out", "dark_patterns"],
            "penalty": "Up to $7,500 per violation",
        },
    },
}

# ---------- CONSENT TEMPLATES ----------
CONSENT_TEMPLATES = {
    "dpdp": {
        "banner_html": """<!-- DPDP Act 2023 Compliant Consent Banner -->
<div id="consent-banner" style="display:none; position:fixed; bottom:0; left:0; right:0; background:#fff; border-top:2px solid #1e40af; padding:20px; z-index:9999; font-family:system-ui,sans-serif; box-shadow:0 -4px 20px rgba(0,0,0,0.1);">
  <div style="max-width:1200px; margin:0 auto; display:flex; flex-wrap:wrap; gap:16px; align-items:center; justify-content:space-between;">
    <div style="flex:1; min-width:280px;">
      <p style="margin:0 0 8px 0; font-size:14px; color:#111; line-height:1.5;">
        <strong>We need your consent to process your personal data.</strong><br>
        We use cookies and similar technologies for [specific purposes: analytics, advertising, AI assistance]. 
        You can withdraw consent anytime. Read our <a href="/privacy" style="color:#1e40af; text-decoration:underline;">Privacy Notice</a>.
      </p>
    </div>
    <div style="display:flex; gap:10px; flex-wrap:wrap;">
      <button id="consent-reject" style="padding:10px 20px; border:1px solid #d1d5db; background:#fff; color:#374151; border-radius:6px; font-weight:500; cursor:pointer; font-size:14px;">Reject All</button>
      <button id="consent-customize" style="padding:10px 20px; border:1px solid #d1d5db; background:#f3f4f6; color:#374151; border-radius:6px; font-weight:500; cursor:pointer; font-size:14px;">Customize</button>
      <button id="consent-accept" style="padding:10px 20px; border:none; background:#1e40af; color:#fff; border-radius:6px; font-weight:600; cursor:pointer; font-size:14px;">Accept All</button>
    </div>
  </div>
</div>""",
        "checkbox_html": """<!-- DPDP Compliant Consent Checkboxes -->
<form id="consent-form">
  <div style="margin-bottom:16px;">
    <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer;">
      <input type="checkbox" name="consent_analytics" value="1" style="width:18px; height:18px; margin-top:2px; accent-color:#1e40af;">
      <span style="font-size:14px; color:#374151; line-height:1.5;">
        <strong>I consent</strong> to the processing of my personal data for <strong>analytics purposes</strong> 
        (understanding website usage). I understand my data may be processed by <strong>Google Analytics</strong> and may be transferred outside India.
      </span>
    </label>
  </div>
  <div style="margin-bottom:16px;">
    <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer;">
      <input type="checkbox" name="consent_marketing" value="1" style="width:18px; height:18px; margin-top:2px; accent-color:#1e40af;">
      <span style="font-size:14px; color:#374151; line-height:1.5;">
        <strong>I consent</strong> to receiving <strong>marketing communications</strong> via email. 
        I understand my email and name will be shared with <strong>Mailchimp</strong> for delivery purposes. I can unsubscribe at any time.
      </span>
    </label>
  </div>
  <div style="margin-bottom:16px;">
    <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer;">
      <input type="checkbox" name="consent_ai" value="1" style="width:18px; height:18px; margin-top:2px; accent-color:#1e40af;">
      <span style="font-size:14px; color:#374151; line-height:1.5;">
        <strong>I consent</strong> to my inputs being processed by <strong>AI systems (OpenAI)</strong> 
        to provide automated assistance. I understand a human review is available upon request.
      </span>
    </label>
  </div>
  <p style="font-size:12px; color:#6b7280; margin-top:12px;">
    <strong>Your rights:</strong> You may withdraw any consent at any time by contacting 
    <a href="mailto:privacy@company.com">privacy@company.com</a>. Withdrawal is as easy as giving consent.
  </p>
</form>""",
        "js_implementation": """// DPDP Consent Manager - Must load BEFORE any tracking scripts
class DPDPConsentManager {
  constructor() {
    this.consent = this.loadConsent();
    this.banner = document.getElementById('consent-banner');
    this.init();
  }
  init() {
    if (!this.consent) this.showBanner();
    this.applyConsent();
    this.bindEvents();
  }
  loadConsent() {
    try { return JSON.parse(localStorage.getItem('dpdp_consent')); } catch { return null; }
  }
  saveConsent(choices) {
    const record = {
      timestamp: new Date().toISOString(), version: '1.0', choices: choices,
      ip_anonymized: true, user_agent: navigator.userAgent.substring(0, 100)
    };
    localStorage.setItem('dpdp_consent', JSON.stringify(record));
    this.consent = record; this.hideBanner(); this.applyConsent();
    fetch('/api/consent-log', { method: 'POST', body: JSON.stringify(record) });
  }
  showBanner() { if(this.banner) this.banner.style.display = 'block'; }
  hideBanner() { if(this.banner) this.banner.style.display = 'none'; }
  applyConsent() {
    if (!this.consent) { this.blockGA4(); this.blockMetaPixel(); this.blockOpenAI(); return; }
    const c = this.consent.choices;
    if (c.analytics) this.loadGA4(); else this.blockGA4();
    if (c.marketing) this.loadMetaPixel(); else this.blockMetaPixel();
    if (c.ai) this.enableOpenAI(); else this.blockOpenAI();
  }
  blockGA4() { window['ga-disable-GA_MEASUREMENT_ID'] = true; }
  blockMetaPixel() { window.fbq = function(){}; }
  blockOpenAI() { window.openAIConsent = false; }
  loadGA4() { /* inject gtag with consent: granted */ }
  loadMetaPixel() { /* inject fbq with consent: granted */ }
  enableOpenAI() { window.openAIConsent = true; }
  bindEvents() {
    document.getElementById('consent-accept')?.addEventListener('click', () => {
      this.saveConsent({ analytics: true, marketing: true, ai: true });
    });
    document.getElementById('consent-reject')?.addEventListener('click', () => {
      this.saveConsent({ analytics: false, marketing: false, ai: false });
    });
  }
}
const consentManager = new DPDPConsentManager();""",
        "dark_pattern_violations": [
            "Pre-ticked consent checkboxes", "Bundling terms of service with marketing consent",
            "'By using this site you agree' passive consent", "Reject button smaller or lower contrast than Accept",
            "Multi-click opt-out (more than 1 click to withdraw)", "Color-faded or disabled-looking Reject button",
        ],
    },
    "gdpr": {
        "banner_html": """<!-- GDPR Compliant Consent Banner (Consent Mode v2) -->
<div id="consent-banner" style="display:none; position:fixed; bottom:0; left:0; right:0; background:#fff; border-top:2px solid #1d4ed8; padding:20px; z-index:9999; font-family:system-ui,sans-serif; box-shadow:0 -4px 20px rgba(0,0,0,0.1);">
  <div style="max-width:1200px; margin:0 auto; display:flex; flex-wrap:wrap; gap:16px; align-items:center; justify-content:space-between;">
    <div style="flex:1; min-width:280px;">
      <p style="margin:0 0 8px 0; font-size:14px; color:#111; line-height:1.5;">
        <strong>This website uses cookies and similar technologies.</strong><br>
        Some are necessary for the site to function. For others (analytics, marketing, personalization), we need your consent. 
        You can change your preferences at any time. 
        <a href="/privacy" style="color:#1d4ed8; text-decoration:underline;">Privacy Policy</a> | 
        <a href="/cookies" style="color:#1d4ed8; text-decoration:underline;">Cookie Policy</a>
      </p>
    </div>
    <div style="display:flex; gap:10px; flex-wrap:wrap;">
      <button id="consent-reject" style="padding:10px 20px; border:1.5px solid #374151; background:#fff; color:#111; border-radius:6px; font-weight:500; cursor:pointer; font-size:14px; min-width:120px;">Reject All</button>
      <button id="consent-customize" style="padding:10px 20px; border:1.5px solid #d1d5db; background:#f9fafb; color:#374151; border-radius:6px; font-weight:500; cursor:pointer; font-size:14px; min-width:120px;">Manage Preferences</button>
      <button id="consent-accept" style="padding:10px 20px; border:none; background:#1d4ed8; color:#fff; border-radius:6px; font-weight:600; cursor:pointer; font-size:14px; min-width:120px;">Accept All</button>
    </div>
  </div>
</div>""",
        "checkbox_html": """<!-- GDPR Compliant Consent Checkboxes -->
<form id="consent-form">
  <fieldset style="border:1px solid #e5e7eb; border-radius:8px; padding:16px; margin-bottom:16px;">
    <legend style="font-weight:600; font-size:14px; color:#111; padding:0 8px;">Cookie & Data Processing Preferences</legend>
    <div style="margin-bottom:12px; padding:12px; background:#f9fafb; border-radius:6px;">
      <label style="display:flex; align-items:flex-start; gap:10px;">
        <input type="checkbox" checked disabled style="width:18px; height:18px; margin-top:2px;">
        <span style="font-size:14px; color:#374151; line-height:1.5;">
          <strong>Strictly Necessary</strong> — Required for the website to function. Cannot be disabled. <em>Lawful basis: Article 6(1)(b).</em>
        </span>
      </label>
    </div>
    <div style="margin-bottom:12px; padding:12px; border:1px solid #e5e7eb; border-radius:6px;">
      <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer;">
        <input type="checkbox" name="consent_analytics" value="1" style="width:18px; height:18px; margin-top:2px; accent-color:#1d4ed8;">
        <span style="font-size:14px; color:#374151; line-height:1.5;">
          <strong>Analytics & Performance</strong> — Helps us understand how visitors interact. Data shared with <strong>Google Analytics</strong>. IP addresses anonymized. <em>Lawful basis: Article 6(1)(a) — Consent.</em>
        </span>
      </label>
    </div>
    <div style="margin-bottom:12px; padding:12px; border:1px solid #e5e7eb; border-radius:6px;">
      <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer;">
        <input type="checkbox" name="consent_marketing" value="1" style="width:18px; height:18px; margin-top:2px; accent-color:#1d4ed8;">
        <span style="font-size:14px; color:#374151; line-height:1.5;">
          <strong>Marketing & Advertising</strong> — Used to deliver personalized ads. Data shared with <strong>Meta (Facebook)</strong> and <strong>Google Ads</strong>. <em>Lawful basis: Article 6(1)(a) — Consent.</em>
        </span>
      </label>
    </div>
    <div style="margin-bottom:12px; padding:12px; border:1px solid #e5e7eb; border-radius:6px;">
      <label style="display:flex; align-items:flex-start; gap:10px; cursor:pointer;">
        <input type="checkbox" name="consent_ai" value="1" style="width:18px; height:18px; margin-top:2px; accent-color:#1d4ed8;">
        <span style="font-size:14px; color:#374151; line-height:1.5;">
          <strong>AI-Assisted Processing</strong> — Your inputs may be processed by <strong>OpenAI GPT-4</strong>. You have the right to request human review. <em>Lawful basis: Article 6(1)(a) — Consent. Article 22 applies.</em>
        </span>
      </label>
    </div>
  </fieldset>
  <p style="font-size:12px; color:#6b7280; margin-top:12px;">
    <strong>Your rights under GDPR:</strong> Access, rectification, erasure, restriction, data portability, objection. Contact our DPO at <a href="mailto:dpo@company.com">dpo@company.com</a>.
  </p>
</form>""",
        "js_implementation": """// GDPR Consent Manager with Google Consent Mode v2
class GDPRConsentManager {
  constructor() {
    this.consent = this.loadConsent(); this.banner = document.getElementById('consent-banner'); this.init();
  }
  init() {
    this.setDefaultConsent();
    if (!this.consent) this.showBanner();
    this.applyConsent(); this.bindEvents();
  }
  setDefaultConsent() {
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('consent', 'default', {
      'ad_storage': 'denied', 'analytics_storage': 'denied',
      'ad_user_data': 'denied', 'ad_personalization': 'denied', 'wait_for_update': 500
    });
    gtag('set', 'ads_data_redaction', true);
  }
  loadConsent() { try { return JSON.parse(localStorage.getItem('gdpr_consent')); } catch { return null; } }
  saveConsent(choices) {
    const record = { timestamp: new Date().toISOString(), version: '1.0', choices: choices, policy_version: '2024-01' };
    localStorage.setItem('gdpr_consent', JSON.stringify(record));
    this.consent = record; this.hideBanner(); this.applyConsent();
    fetch('/api/consent-log', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(record) });
  }
  showBanner() { if(this.banner) this.banner.style.display = 'block'; }
  hideBanner() { if(this.banner) this.banner.style.display = 'none'; }
  applyConsent() {
    if (!this.consent) return;
    const c = this.consent.choices;
    window.dataLayer = window.dataLayer || []; function gtag(){dataLayer.push(arguments);}
    gtag('consent', 'update', {
      'ad_storage': c.marketing ? 'granted' : 'denied',
      'analytics_storage': c.analytics ? 'granted' : 'denied',
      'ad_user_data': c.marketing ? 'granted' : 'denied',
      'ad_personalization': c.marketing ? 'granted' : 'denied',
    });
    if (c.analytics) this.loadGA4(); if (c.marketing) this.loadMetaPixel();
    if (c.ai) this.enableOpenAI(); else this.blockOpenAI();
  }
  blockOpenAI() { window.openAIConsent = false; }
  enableOpenAI() { window.openAIConsent = true; }
  loadGA4() { /* inject gtag script */ }
  loadMetaPixel() { /* inject fbq script */ }
  bindEvents() {
    document.getElementById('consent-accept')?.addEventListener('click', () => {
      this.saveConsent({ analytics: true, marketing: true, ai: true, necessary: true });
    });
    document.getElementById('consent-reject')?.addEventListener('click', () => {
      this.saveConsent({ analytics: false, marketing: false, ai: false, necessary: true });
    });
  }
}
const gdprConsent = new GDPRConsentManager();""",
        "dark_pattern_violations": [
            "Pre-ticked or pre-selected consent boxes (Article 7 violation)",
            "Consent bundled with terms of service (must be separate)",
            "'Continue' or 'OK' button implying consent without clear information",
            "Reject button smaller, lighter, or less accessible than Accept",
            "More than 1 click required to reject (vs 1 click to accept)",
            "Nudging: Accept button has animation, color, or size advantage",
            "No 'Reject All' option — only 'Manage Preferences' with toggles",
            "Storing cookies before user interaction (no legitimate interest override for non-essential)",
        ],
    },
    "ccpa": {
        "banner_html": """<!-- CCPA/CPRA Compliant Notice (Opt-Out Model) -->
<div id="privacy-notice" style="position:fixed; bottom:0; left:0; right:0; background:#fff; border-top:2px solid #047857; padding:16px; z-index:9999; font-family:system-ui,sans-serif; box-shadow:0 -4px 20px rgba(0,0,0,0.1);">
  <div style="max-width:1200px; margin:0 auto; display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between;">
    <div style="flex:1; min-width:280px;">
      <p style="margin:0; font-size:14px; color:#111; line-height:1.5;">
        <strong>California Privacy Notice:</strong> We collect personal information as described in our 
        <a href="/privacy" style="color:#047857; text-decoration:underline;">Privacy Policy</a>. 
        We may share your data with advertising partners. 
        <a href="/do-not-sell" style="color:#047857; text-decoration:underline; font-weight:600;">Do Not Sell or Share My Personal Information</a> | 
        <a href="/limit-use" style="color:#047857; text-decoration:underline;">Limit Use of My Sensitive PI</a>
      </p>
    </div>
    <button id="notice-dismiss" style="padding:8px 16px; border:1px solid #d1d5db; background:#fff; color:#374151; border-radius:6px; font-weight:500; cursor:pointer; font-size:13px;">Dismiss</button>
  </div>
</div>""",
        "checkbox_html": """<!-- CCPA/CPRA: Opt-Out Rights -->
<div style="border:1px solid #e5e7eb; border-radius:8px; padding:20px; max-width:600px;">
  <h3 style="margin:0 0 16px 0; font-size:16px; color:#111;">Your California Privacy Rights</h3>
  <div style="margin-bottom:16px; padding:16px; background:#f0fdf4; border-radius:6px; border:1px solid #bbf7d0;">
    <p style="margin:0 0 12px 0; font-size:14px; color:#111; line-height:1.5;">
      <strong>Right to Opt-Out of Sale/Sharing</strong><br>We share personal information with third-party advertising partners (Meta Pixel, Google Ads). You have the right to opt-out.
    </p>
    <a href="/do-not-sell" style="display:inline-block; padding:10px 20px; background:#047857; color:#fff; text-decoration:none; border-radius:6px; font-weight:600; font-size:14px;">Do Not Sell or Share My Personal Information</a>
  </div>
  <div style="margin-bottom:16px; padding:16px; background:#eff6ff; border-radius:6px; border:1px solid #bfdbfe;">
    <p style="margin:0 0 12px 0; font-size:14px; color:#111; line-height:1.5;">
      <strong>Right to Limit Use of Sensitive PI</strong><br>If we collect sensitive personal information, you can limit its use to only what is necessary.
    </p>
    <a href="/limit-use" style="display:inline-block; padding:10px 20px; background:#1d4ed8; color:#fff; text-decoration:none; border-radius:6px; font-weight:600; font-size:14px;">Limit Use of My Sensitive PI</a>
  </div>
  <p style="font-size:12px; color:#6b7280; margin:0;">We honor the <strong>Global Privacy Control (GPC)</strong> signal from your browser.</p>
</div>""",
        "js_implementation": """// CCPA/CPRA Compliance: Honor GPC + Opt-Out
class CCPACompliance {
  constructor() {
    this.gpcEnabled = navigator.globalPrivacyControl === true;
    this.init();
  }
  init() {
    if (this.gpcEnabled) { this.applyOptOut(); console.log('GPC honored: Sale/Sharing disabled'); }
    const optOut = localStorage.getItem('ccpa_opt_out');
    if (optOut === 'true') this.applyOptOut();
    this.bindEvents();
  }
  applyOptOut() {
    window.fbq = function(){};
    window.dataLayer = window.dataLayer || []; function gtag(){dataLayer.push(arguments);}
    gtag('set', 'allow_ad_personalization_signals', false);
    gtag('set', 'restricted_data_processing', true);
    fetch('/api/opt-out-log', { method: 'POST', body: JSON.stringify({ source: this.gpcEnabled ? 'GPC' : 'manual', timestamp: new Date().toISOString() })});
  }
  bindEvents() {
    document.getElementById('notice-dismiss')?.addEventListener('click', () => {
      document.getElementById('privacy-notice').style.display = 'none';
      localStorage.setItem('ccpa_notice_dismissed', 'true');
    });
  }
}
const ccpa = new CCPACompliance();""",
        "dark_pattern_violations": [
            "'Do Not Sell' link hidden in footer or buried in settings",
            "Requiring account creation to exercise opt-out rights",
            "More than 2 clicks to reach opt-out mechanism",
            "Opt-out button smaller or less visible than opt-in",
            "Ignoring Global Privacy Control (GPC) browser signal",
            "Requiring excessive identity verification for opt-out",
        ],
    },
}

# ---------- RETENTION POLICIES ----------
RETENTION_POLICIES = {
    "dpdp": {
        "server_access_logs": {
            "contains_pii": True, "pii_types": ["ip_address", "user_agent", "timestamp"],
            "legal_basis": "Legitimate interest (security)", "max_retention_days": 30,
            "justification": "Section 8(5) — data not to be retained longer than necessary. IP addresses are personal data under DPDP.",
            "implementation": {
                "aws_s3": '{"Rules":[{"ID":"server-access-logs-dpdp","Status":"Enabled","Filter":{"Prefix":"logs/access/"},"Transitions":[{"Days":7,"StorageClass":"GLACIER"}],"Expiration":{"Days":30}}]}',
                "aws_cloudwatch": "aws logs put-retention-policy --log-group-name /var/log/nginx --retention-in-days 30",
            },
            "anonymization_required": True, "anonymization_method": "Truncate last octet of IPv4; hash IPv6",
        },
        "application_logs": {
            "contains_pii": True, "pii_types": ["user_id", "error_context", "ip_address"],
            "legal_basis": "Legitimate interest (debugging)", "max_retention_days": 90,
            "justification": "Extended for debugging, but must pseudonymize user IDs after 30 days.",
            "implementation": {
                "aws_cloudwatch": "aws logs put-retention-policy --log-group-name /app/logs --retention-in-days 90",
            },
            "anonymization_required": True, "anonymization_method": "Hash user_id with HMAC-SHA256 after 30 days; strip IP after 7 days",
        },
        "user_account_data": {
            "contains_pii": True, "pii_types": ["name", "email", "phone", "address"],
            "legal_basis": "Contract / Consent", "max_retention_days": "duration_of_service_plus_1_year",
            "justification": "Section 8(5) — retain only as long as necessary. Post-termination: 1 year for legal claims.",
            "implementation": {
                "postgresql": "DELETE FROM users WHERE account_status = 'deleted' AND deleted_at < NOW() - INTERVAL '1 year';\n-- Or use pg_cron: SELECT cron.schedule('purge-deleted-users', '0 2 1 * *', $$DELETE FROM users WHERE account_status='deleted' AND deleted_at < NOW() - INTERVAL '1 year'$$);",
                "mongodb": "db.users.createIndex({ deleted_at: 1 }, { expireAfterSeconds: 31536000 }) // 1 year",
            },
            "anonymization_required": False, "anonymization_method": "Full deletion after retention period",
        },
        "payment_records": {
            "contains_pii": True, "pii_types": ["card_token", "transaction_id", "billing_address"],
            "legal_basis": "Legal obligation (RBI / Income Tax Act)", "max_retention_days": 2555,
            "justification": "Income Tax Act requires 7-year retention. RBI PA/PG guidelines require tokenized card data retention per license terms.",
            "implementation": {
                "stripe": "Stripe retains charge records for 7+ years per PCI-DSS. Ensure you do NOT store raw card data — only Stripe tokens (tok_xxx).",
                "razorpay": "Razorpay retains transaction records per RBI norms. Your application should only store order_id and payment_id.",
                "postgresql": "-- Store only token references, NEVER raw card data\nCREATE TABLE payments (\n  id UUID PRIMARY KEY,\n  stripe_payment_intent_id VARCHAR(255), -- tok_xxx or pi_xxx\n  amount DECIMAL(10,2), currency VARCHAR(3), created_at TIMESTAMP\n);",
            },
            "anonymization_required": False, "anonymization_method": "Tokenization only — never store raw card data",
        },
        "cookie_consent_records": {
            "contains_pii": False, "pii_types": ["consent_choices", "timestamp", "anonymized_ip"],
            "legal_basis": "Legal obligation (demonstrating compliance)", "max_retention_days": 1825,
            "justification": "Must retain proof of consent for regulatory audits. Store anonymized data only.",
            "implementation": {
                "postgresql": "CREATE TABLE consent_records (\n  id UUID PRIMARY KEY,\n  consent_choices JSONB NOT NULL,\n  timestamp TIMESTAMP NOT NULL,\n  policy_version VARCHAR(10),\n  user_agent_hash VARCHAR(64), -- SHA-256 hash\n  ip_hash VARCHAR(64), -- SHA-256 hash of truncated IP\n  created_at TIMESTAMP DEFAULT NOW()\n);",
            },
            "anonymization_required": True, "anonymization_method": "Hash IP and UA; do not store raw values",
        },
        "ai_api_logs": {
            "contains_pii": True, "pii_types": ["user_inputs", "ai_outputs", "session_id"],
            "legal_basis": "Consent", "max_retention_days": 30,
            "justification": "Section 8(5) — retain only as long as necessary. OpenAI retains for 30 days for abuse monitoring.",
            "implementation": {
                "openai_api": "Set your own retention to 30 days max. Use OpenAI's 'no-training' API endpoint. Document in DPIA.",
                "postgresql": "DELETE FROM ai_conversations WHERE created_at < NOW() - INTERVAL '30 days';",
                "aws_s3": '{"Rules":[{"ID":"ai-logs-dpdp","Status":"Enabled","Filter":{"Prefix":"ai-logs/"},"Expiration":{"Days":30}}]}',
            },
            "anonymization_required": True, "anonymization_method": "Strip PII from inputs before sending to API; retain only conversation metadata",
        },
    },
    "gdpr": {
        "server_access_logs": {
            "contains_pii": True, "pii_types": ["ip_address", "user_agent"],
            "legal_basis": "Legitimate interest (Art. 6(1)(f)) — security", "max_retention_days": 30,
            "justification": "Art. 5(1)(e) — kept no longer than necessary. EDPB guidelines: 30 days for security logs.",
            "implementation": {
                "aws_s3": "Same as DPDP: 30-day S3 lifecycle + Glacier transition",
                "gdpr_specific": "Document in ROPA (Art. 30): 'Access logs: IP, 30 days, security purpose, legitimate interest'",
            },
            "anonymization_required": True, "anonymization_method": "Anonymize IP immediately after collection (last octet truncation)",
        },
        "user_account_data": {
            "contains_pii": True, "pii_types": ["name", "email", "phone"],
            "legal_basis": "Contract (Art. 6(1)(b)) / Consent (Art. 6(1)(a))", "max_retention_days": "duration_of_service_plus_1_year",
            "justification": "Art. 5(1)(e). Post-contract: 1 year for legal claims, then erasure.",
            "implementation": {
                "gdpr_specific": "Must honor Art. 17 'Right to Erasure' within 30 days of request. Implement automated DSAR workflow.",
                "postgresql": "Same as DPDP + add DSAR tracking table for Art. 30 ROPA",
            },
            "anonymization_required": False, "anonymization_method": "Full erasure after retention period",
        },
        "cookie_consent_records": {
            "contains_pii": False, "pii_types": ["consent_choices", "timestamp"],
            "legal_basis": "Legal obligation (Art. 7 proof of consent)", "max_retention_days": 1825,
            "justification": "Must demonstrate compliance. Art. 30 ROPA requires documentation of processing activities.",
            "implementation": {
                "gdpr_specific": "Include in ROPA: 'Consent records: choices, timestamp, version, 5 years, legal obligation basis'",
            },
            "anonymization_required": True, "anonymization_method": "No IP storage; hash user agent",
        },
    },
    "ccpa": {
        "server_access_logs": {
            "contains_pii": True, "pii_types": ["ip_address"],
            "legal_basis": "Business purpose (security)", "max_retention_days": 30,
            "justification": "Must delete within 45 days of consumer deletion request. Proactive 30-day limit is safer.",
            "implementation": {
                "ccpa_specific": "Honor deletion requests within 45 days (extendable to 90 with notice). Document retention in privacy policy.",
            },
            "anonymization_required": False, "anonymization_method": "Delete upon consumer request",
        },
        "user_account_data": {
            "contains_pii": True, "pii_types": ["name", "email", "phone"],
            "legal_basis": "Business purpose", "max_retention_days": "duration_of_service_plus_1_year",
            "justification": "Must delete within 45 days of verifiable consumer request. Exception: financial records (7 years).",
            "implementation": {
                "ccpa_specific": "Provide 'Right to Delete' form. Verify identity via 2-factor before deletion. Exempt financial records per Civil Code.",
            },
            "anonymization_required": False, "anonymization_method": "Delete upon verified request",
        },
    },
}

# ---------- PRIVACY POLICY MODULES ----------
PRIVACY_POLICY_MODULES = {
    "header": """PRIVACY POLICY

Last Updated: {date}
Effective Date: {date}

This Privacy Policy applies to {company_name} ("we", "us", "our") and describes how we collect, use, store, share, and protect your personal information when you use our services at {website_url}.

This policy is designed to comply with:
{regulations_list}

If you have questions about this policy, contact our {contact_role} at {contact_email}.

---

""",
    "data_controller": """1. DATA CONTROLLER

Name: {company_name}
Address: {company_address}
Email: {contact_email}
{gdpr_dpo_line}

We are the data controller responsible for your personal information under the applicable data protection laws.

---

""",
    "what_we_collect": """2. WHAT PERSONAL DATA WE COLLECT

We collect the following categories of personal data:

{data_table}

---

""",
    "legal_basis": """3. LEGAL BASIS FOR PROCESSING

We process your personal data based on the following lawful bases:

{legal_basis_table}

---

""",
    "third_parties": """4. THIRD PARTIES AND DATA SHARING

We share your personal data with the following categories of recipients:

{third_party_table}

---

""",
    "data_retention": """5. DATA RETENTION

We retain your personal data for the following periods:

{retention_table}

After the retention period expires, we securely delete or anonymize your data in accordance with our data destruction procedures.

---

""",
    "your_rights": """6. YOUR RIGHTS

{rights_section}

---

""",
    "cookies": """7. COOKIES AND TRACKING TECHNOLOGIES

We use cookies and similar technologies as follows:

{cookie_table}

You can manage your preferences through our {consent_mechanism}.

---

""",
    "ai_disclosure": """8. ARTIFICIAL INTELLIGENCE AND AUTOMATED PROCESSING

We use artificial intelligence systems to {ai_purpose}. Specifically:

- AI Provider: {ai_provider}
- Data Processed: {ai_data_types}
- Automated Decision-Making: {automated_decision_status}
- Human Review: {human_review_option}
- Data Retention by AI Provider: {ai_provider_retention}
- Your Rights: {ai_rights}

{ai_special_note}

---

""",
    "security": """9. DATA SECURITY

We implement the following technical and organizational measures to protect your personal data:

- Encryption at rest: AES-256
- Encryption in transit: TLS 1.2+
- Access controls: Role-based access control (RBAC)
- Regular security audits and penetration testing
- Incident response plan with {breach_timeline} notification timeline
- Staff training on data protection

---

""",
    "international_transfers": """10. INTERNATIONAL DATA TRANSFERS

Your personal data may be transferred to and processed in countries outside your jurisdiction. We ensure adequate protection through:

{transfer_safeguards}

---

""",
    "grievance": """11. GRIEVANCE OFFICER / DPO

{grievance_officer_section}

---

""",
    "updates": """12. CHANGES TO THIS POLICY

We may update this Privacy Policy from time to time. We will notify you of significant changes by:
- Email notification to your registered address
- A prominent notice on our website
- Updating the "Last Updated" date at the top of this policy

---

13. COMPLIANCE CERTIFICATION

This privacy policy has been reviewed for compliance with:
{regulations_certified}

Generated by Compliance AI. This is a template. Please review with qualified legal counsel before use.
""",
}

# ============== NEW HELPER FUNCTIONS ==============

def detect_tech_stack(text: str) -> List[Dict]:
    """Scan document text for technology mentions and return detected stack."""
    text_lower = text.lower()
    detected = []
    for tech_id, tech_info in TECH_STACK_PATTERNS.items():
        confidence = 0
        matched_keywords = []
        for keyword in tech_info["keywords"]:
            if keyword.lower() in text_lower:
                confidence += 1
                matched_keywords.append(keyword)
        if confidence > 0:
            detected.append({
                "id": tech_id, "name": tech_id.replace("_", " ").title(),
                "category": tech_info["category"],
                "confidence": min(confidence / len(tech_info["keywords"]) * 100, 100),
                "matched_keywords": matched_keywords,
                "data_types": tech_info["data_types"],
                "third_party": tech_info["third_party"],
                "cross_border": tech_info.get("cross_border", False),
            })
    detected.sort(key=lambda x: x["confidence"], reverse=True)
    return detected

def detect_dark_patterns(text: str) -> List[Dict]:
    """Scan text for dark pattern language and UI anti-patterns."""
    text_lower = text.lower()
    patterns = []

    # Pre-ticked boxes
    if any(kw in text_lower for kw in ["pre-ticked", "pre selected", "pre-selected", "checked by default", "enabled by default"]):
        patterns.append({"pattern": "Pre-ticked consent boxes", "severity": "HIGH", "regulation": "DPDP/GDPR", "fix": "All consent checkboxes must be unchecked by default. Pre-ticked boxes violate Article 7 GDPR and Section 5 DPDP."})

    # Passive consent
    if any(kw in text_lower for kw in ["by using this site", "by continuing", "by browsing", "your use constitutes consent", "by accessing"]):
        patterns.append({"pattern": "Passive consent language", "severity": "HIGH", "regulation": "DPDP/GDPR", "fix": "Replace passive consent with active, explicit opt-in mechanisms. Consent must be free, specific, informed, unconditional, and unambiguous."})

    # Bundled consent
    if any(kw in text_lower for kw in ["i agree to the terms and privacy policy", "by signing up you agree to our terms and marketing", "combined consent"]):
        patterns.append({"pattern": "Bundled consent (ToS + marketing)", "severity": "HIGH", "regulation": "DPDP/GDPR", "fix": "Separate consent for terms of service from consent for marketing/analytics. Each purpose must have its own granular consent mechanism."})

    # Hidden opt-out
    if any(kw in text_lower for kw in ["to opt out contact us", "email us to unsubscribe", "write to us to withdraw"]):
        patterns.append({"pattern": "Friction-heavy withdrawal", "severity": "MEDIUM", "regulation": "DPDP/GDPR", "fix": "Withdrawal must be as easy as giving consent. Provide one-click opt-out in the same UI where consent was given."})

    # Unequal buttons
    if any(kw in text_lower for kw in ["accept all (recommended)", "accept (recommended)", "yes please", "no thanks (boring)"]):
        patterns.append({"pattern": "Nudging / unequal button prominence", "severity": "MEDIUM", "regulation": "GDPR", "fix": "Accept and Reject buttons must be equally prominent in size, color, and accessibility. No nudging language."})

    # Hidden AI
    if any(kw in text_lower for kw in ["ai-powered", "automated processing", "machine learning", "algorithm"]):
        if not any(kw in text_lower for kw in ["human review", "you can request human", "human oversight"]):
            patterns.append({"pattern": "AI use without human review disclosure", "severity": "MEDIUM", "regulation": "DPDP/GDPR", "fix": "If using AI for decisions affecting users, disclose the logic and provide a human review option."})

    return patterns

def generate_consent_spec(tech_stack: List[Dict], regulation: str) -> Dict:
    """Generate exact consent checkbox specifications for detected tech stack."""
    reg_rules = COMPLIANCE_RULES.get(regulation, {})
    template = CONSENT_TEMPLATES.get(regulation, CONSENT_TEMPLATES["dpdp"])
    consent_required_tech = []
    consent_not_required_tech = []
    for tech in tech_stack:
        rules = reg_rules.get(tech["id"], {})
        if rules.get("consent_required", False):
            consent_required_tech.append({"tech": tech, "rules": rules})
        else:
            consent_not_required_tech.append({"tech": tech, "rules": rules})
    purposes = []
    for item in consent_required_tech:
        tech = item["tech"]
        if tech["category"] == "analytics":
            purposes.append({"id": "analytics", "label": "Analytics & Performance",
                "description": f"We use {tech['name']} to understand how visitors interact with our website. Data may include your IP address and browsing behavior.",
                "third_party": tech["name"], "cross_border": tech["cross_border"], "default_checked": False, "required": False})
        elif tech["category"] == "advertising":
            purposes.append({"id": "marketing", "label": "Marketing & Advertising",
                "description": f"We use {tech['name']} to deliver personalized advertisements and measure their effectiveness.",
                "third_party": tech["name"], "cross_border": tech["cross_border"], "default_checked": False, "required": False})
        elif tech["category"] == "ai":
            purposes.append({"id": "ai", "label": "AI-Assisted Processing",
                "description": f"Your inputs may be processed by {tech['name']} to provide automated assistance. You can request human review.",
                "third_party": tech["name"], "cross_border": tech["cross_border"], "default_checked": False, "required": False})
        elif tech["category"] == "marketing":
            purposes.append({"id": "marketing_communications", "label": "Marketing Communications",
                "description": f"We use {tech['name']} to send you newsletters and promotional emails.",
                "third_party": tech["name"], "cross_border": tech["cross_border"], "default_checked": False, "required": False})
    return {
        "regulation": regulation, "regulation_name": REGULATIONS.get(regulation, {}).get("name", regulation.upper()),
        "consent_model": "opt_in" if regulation in ["dpdp", "gdpr"] else "opt_out",
        "banner_html": template["banner_html"], "checkbox_html": template["checkbox_html"],
        "js_implementation": template["js_implementation"], "purposes": purposes,
        "consent_required_tech": [{"name": t["tech"]["name"], "reason": t["rules"].get("consent_type", "required")} for t in consent_required_tech],
        "consent_not_required_tech": [{"name": t["tech"]["name"], "reason": t["rules"].get("consent_type", "not_required")} for t in consent_not_required_tech],
        "dark_pattern_violations": template.get("dark_pattern_violations", []),
        "must_implement": [
            "All consent checkboxes must be UNCHECKED by default",
            "Withdrawal mechanism must be as easy as giving consent",
            "Consent records must be maintained for audit (5 years)",
            "Third-party scripts must be blocked until consent is given",
        ] if regulation in ["dpdp", "gdpr"] else [
            "'Do Not Sell or Share' link must be prominently displayed",
            "Must honor Global Privacy Control (GPC) browser signal",
            "Must respond to deletion requests within 45 days",
        ],
    }

def generate_retention_policy(tech_stack: List[Dict], regulation: str) -> Dict:
    """Generate per-data-type retention schedules with cloud-specific configs."""
    reg_retention = RETENTION_POLICIES.get(regulation, RETENTION_POLICIES["dpdp"])
    schedules = []
    cloud_providers = set()

    for data_type, policy in reg_retention.items():
        sched = {
            "data_type": data_type.replace("_", " ").title(),
            "contains_pii": policy["contains_pii"],
            "pii_types": policy["pii_types"],
            "legal_basis": policy["legal_basis"],
            "max_retention": policy["max_retention_days"] if isinstance(policy["max_retention_days"], int) else policy["max_retention_days"],
            "justification": policy["justification"],
            "implementation": policy["implementation"],
            "anonymization_required": policy["anonymization_required"],
            "anonymization_method": policy["anonymization_method"],
        }
        schedules.append(sched)
        for provider in policy["implementation"].keys():
            if provider not in ["gdpr_specific", "ccpa_specific"]:
                cloud_providers.add(provider)

    return {
        "regulation": regulation,
        "regulation_name": REGULATIONS.get(regulation, {}).get("name", regulation.upper()),
        "generated_at": datetime.utcnow().isoformat(),
        "schedules": schedules,
        "summary": {
            "total_schedules": len(schedules),
            "pii_schedules": sum(1 for s in schedules if s["contains_pii"]),
            "require_anonymization": sum(1 for s in schedules if s["anonymization_required"]),
            "cloud_providers_detected": sorted(list(cloud_providers)),
        }
    }

def assemble_privacy_policy(tech_stack: List[Dict], regulation: str, business_info: Dict) -> str:
    """Build a full privacy policy from modular templates mapped to detected tech stack."""
    modules = PRIVACY_POLICY_MODULES
    date_str = datetime.utcnow().strftime("%B %d, %Y")

    # Build data table
    data_table_rows = []
    for tech in tech_stack:
        data_types = ", ".join(tech["data_types"])
        data_table_rows.append(f"- **{tech['name']}** ({tech['category']}): {data_types}")
    if not data_table_rows:
        data_table_rows = ["- General user data collected during registration and service usage"]
    data_table = "\n".join(data_table_rows)

    # Build legal basis table
    reg_rules = COMPLIANCE_RULES.get(regulation, {})
    legal_basis_rows = []
    for tech in tech_stack:
        rules = reg_rules.get(tech["id"], {})
        if rules.get("consent_required"):
            legal_basis_rows.append(f"- **{tech['name']}**: Consent (can be withdrawn anytime)")
        elif rules.get("consent_type") == "contractual_necessity":
            legal_basis_rows.append(f"- **{tech['name']}**: Contractual necessity")
        else:
            legal_basis_rows.append(f"- **{tech['name']}**: Legitimate interest")
    if not legal_basis_rows:
        legal_basis_rows = ["- Legitimate interest for core service delivery"]
    legal_basis_table = "\n".join(legal_basis_rows)

    # Build third-party table
    third_party_rows = []
    for tech in tech_stack:
        if tech["third_party"]:
            cross = " (cross-border transfer)" if tech["cross_border"] else ""
            third_party_rows.append(f"- **{tech['name']}**{cross}: {', '.join(tech['data_types'])}")
    if not third_party_rows:
        third_party_rows = ["- No third-party services detected"]
    third_party_table = "\n".join(third_party_rows)

    # Build retention table
    reg_retention = RETENTION_POLICIES.get(regulation, RETENTION_POLICIES["dpdp"])
    retention_rows = []
    for data_type, policy in reg_retention.items():
        max_ret = str(policy["max_retention_days"]) if isinstance(policy["max_retention_days"], int) else policy["max_retention_days"]
        retention_rows.append(f"- **{data_type.replace('_', ' ').title()}**: {max_ret} days — {policy['legal_basis']}")
    retention_table = "\n".join(retention_rows)

    # Rights section
    if regulation == "dpdp":
        rights_section = """Under the DPDP Act 2023, you have the following rights:
- Right to access your personal data
- Right to correction and erasure
- Right to grievance redressal
- Right to nominate another individual
- Right to withdraw consent
Contact our Grievance Officer to exercise these rights."""
    elif regulation == "gdpr":
        rights_section = """Under GDPR, you have the following rights:
- Right to access (Article 15)
- Right to rectification (Article 16)
- Right to erasure (Article 17)
- Right to restrict processing (Article 18)
- Right to data portability (Article 20)
- Right to object (Article 21)
- Right not to be subject to automated decision-making (Article 22)
Contact our DPO to exercise these rights."""
    else:
        rights_section = """Under CCPA/CPRA, you have the following rights:
- Right to know what personal information is collected
- Right to delete personal information
- Right to opt-out of sale/sharing
- Right to non-discrimination for exercising rights
- Right to limit use of sensitive personal information
Contact us to exercise these rights."""

    # Cookie table
    cookie_rows = []
    for tech in tech_stack:
        if tech["category"] in ["analytics", "advertising", "marketing"]:
            cookie_rows.append(f"- **{tech['name']}**: {tech['category']} — requires explicit consent")
    if not cookie_rows:
        cookie_rows = ["- Essential cookies: Required for site functionality (no consent needed)"]
    cookie_table = "\n".join(cookie_rows)

    # AI disclosure
    ai_tech = [t for t in tech_stack if t["category"] == "ai"]
    if ai_tech:
        ai_provider = ai_tech[0]["name"]
        ai_data_types = ", ".join(ai_tech[0]["data_types"])
        ai_section = modules["ai_disclosure"].format(
            ai_purpose="provide automated customer support and content generation",
            ai_provider=ai_provider,
            ai_data_types=ai_data_types,
            automated_decision_status="Yes, for certain automated responses",
            human_review_option="Available upon request via email",
            ai_provider_retention="30 days for abuse monitoring (OpenAI policy)",
            ai_rights="You may request human review and contest automated decisions",
            ai_special_note="Under DPDP Section 5 and GDPR Article 22, we disclose the use of AI and provide human review options."
        )
    else:
        ai_section = ""

    # International transfers
    cross_border_tech = [t for t in tech_stack if t["cross_border"]]
    if cross_border_tech:
        if regulation == "dpdp":
            transfer_safeguards = "- Government notification of adequate countries\n- Standard contractual clauses approved by the Data Protection Board\n- Your explicit consent for specific transfers"
        elif regulation == "gdpr":
            transfer_safeguards = "- Adequacy decisions (EU Commission)\n- Standard Contractual Clauses (SCCs)\n- Binding Corporate Rules (BCRs)"
        else:
            transfer_safeguards = "- Disclosed in privacy policy\n- Service provider contracts with data protection obligations"
    else:
        transfer_safeguards = "- No cross-border transfers detected"

    # Grievance officer
    if regulation == "dpdp":
        grievance_officer_section = f"""Grievance Officer
Name: [Insert Name]
Email: {business_info.get('contact_email', 'grievance@company.com')}
Address: {business_info.get('company_address', '[Insert Address]')}
Response Time: 30 days from date of receipt"""
    elif regulation == "gdpr":
        grievance_officer_section = f"""Data Protection Officer (DPO)
Name: [Insert DPO Name]
Email: {business_info.get('contact_email', 'dpo@company.com')}
Address: {business_info.get('company_address', '[Insert Address]')}
Supervisory Authority: [Insert relevant authority]"""
    else:
        grievance_officer_section = f"""Privacy Contact
Email: {business_info.get('contact_email', 'privacy@company.com')}
Address: {business_info.get('company_address', '[Insert Address]')}
Phone: [Insert Phone]"""

    # Assemble policy
    policy = modules["header"].format(
        date=date_str,
        company_name=business_info.get("company_name", "[Your Company Name]"),
        website_url=business_info.get("website_url", "[your-website.com]"),
        regulations_list="\n".join([f"- {REGULATIONS.get(regulation, {}).get('name', regulation.upper())}"]),
        contact_role="Grievance Officer" if regulation == "dpdp" else "DPO" if regulation == "gdpr" else "Privacy Contact",
        contact_email=business_info.get("contact_email", "[contact@company.com]")
    )

    policy += modules["data_controller"].format(
        company_name=business_info.get("company_name", "[Your Company Name]"),
        company_address=business_info.get("company_address", "[Your Address]"),
        contact_email=business_info.get("contact_email", "[contact@company.com]"),
        gdpr_dpo_line=f"DPO: {business_info.get('contact_email', '[dpo@company.com]')}\n" if regulation == "gdpr" else ""
    )

    policy += modules["what_we_collect"].format(data_table=data_table)
    policy += modules["legal_basis"].format(legal_basis_table=legal_basis_table)
    policy += modules["third_parties"].format(third_party_table=third_party_table)
    policy += modules["data_retention"].format(retention_table=retention_table)
    policy += modules["your_rights"].format(rights_section=rights_section)
    policy += modules["cookies"].format(cookie_table=cookie_table, consent_mechanism="Consent Manager" if regulation in ["dpdp", "gdpr"] else "Privacy Settings")

    if ai_section:
        policy += ai_section

    policy += modules["security"].format(breach_timeline="72 hours" if regulation == "dpdp" else "72 hours (GDPR) / 60 days (HIPAA)")
    policy += modules["international_transfers"].format(transfer_safeguards=transfer_safeguards)
    policy += modules["grievance"].format(grievance_officer_section=grievance_officer_section)
    policy += modules["updates"].format(regulations_certified=REGULATIONS.get(regulation, {}).get("name", regulation.upper()))

    return policy

# ============== EXISTING HELPERS ==============

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
                "severity": "HIGH" if category in ["Consent", "Breach Notification"] else "MEDIUM",
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
        "regulation_type": regulation_type,
        "tech_stack": detect_tech_stack(text),
        "dark_patterns": detect_dark_patterns(text),
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
            severity = str(gap["severity"]).upper()
            severity_color = colors.red if severity == "HIGH" else colors.orange if severity == "MEDIUM" else colors.blue

            gap_data = [
                [Paragraph(f"<b>{gap['regulation']} — {gap['section']}</b>", normal_style)],
                [Paragraph(f"<b>Severity:</b> <font color='{severity_color.hexval()}'>{severity}</font>", normal_style)],
                [Paragraph(f"<b>Issue:</b> {gap['description']}</b>", normal_style)],
                [Paragraph(f"<b>Recommendation:</b> {gap['suggestion']}</b>", normal_style)]
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
    regulation: str = "dpdp",
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    original_name = Path(file.filename or "uploaded-document").name
    file_path = Path("uploads") / original_name
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    text = extract_text(str(file_path))

    db_doc = DocumentDB(
        filename=original_name,
        original_name=original_name,
        extracted_text=text[:10000],
        status="pending",
        owner_id=current_user.id
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    return {
        "id": db_doc.id,
        "filename": original_name,
        "name": original_name,
        "status": "pending",
        "message": f"Saved {original_name}. Read {len(text)} characters.",
        "regulation": regulation
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
        "overall_score": result["overall_score"],
        "status": result["status"],
        "breakdown": result["breakdown"],
        "gaps": result["gaps"],
        "passed": result["passed"],
        "regulation_type": result["regulation_type"],
        "tech_stack": result["tech_stack"],
        "dark_patterns": result["dark_patterns"],
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

# ============== NEW IMPLEMENTATION ROUTES ==============

@app.post("/api/v1/compliance/tech-stack/{document_id}")
def get_tech_stack(
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
    text = doc.extracted_text or ""
    return {"document_id": document_id, "tech_stack": detect_tech_stack(text)}

@app.post("/api/v1/compliance/consent-spec/{document_id}")
def get_consent_spec(
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
    tech_stack = detect_tech_stack(text)
    return generate_consent_spec(tech_stack, regulation)

@app.post("/api/v1/compliance/retention-policy/{document_id}")
def get_retention_policy(
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
    tech_stack = detect_tech_stack(text)
    return generate_retention_policy(tech_stack, regulation)

@app.post("/api/v1/compliance/boilerplate/{document_id}")
def get_boilerplate(
    document_id: int,
    regulation: str = "dpdp",
    company_name: str = Form("[Your Company]"),
    website_url: str = Form("[your-website.com]"),
    contact_email: str = Form("[privacy@company.com]"),
    company_address: str = Form("[Your Address]"),
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
    tech_stack = detect_tech_stack(text)
    business_info = {
        "company_name": company_name,
        "website_url": website_url,
        "contact_email": contact_email,
        "company_address": company_address,
    }
    policy = assemble_privacy_policy(tech_stack, regulation, business_info)
    return {"document_id": document_id, "regulation": regulation, "privacy_policy": policy}

@app.post("/api/v1/compliance/dark-patterns/{document_id}")
def get_dark_patterns(
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
    text = doc.extracted_text or ""
    return {"document_id": document_id, "dark_patterns": detect_dark_patterns(text)}

@app.post("/api/v1/compliance/full-implementation/{document_id}")
def get_full_implementation(
    document_id: int,
    regulation: str = "dpdp",
    company_name: str = Form("[Your Company]"),
    website_url: str = Form("[your-website.com]"),
    contact_email: str = Form("[privacy@company.com]"),
    company_address: str = Form("[Your Address]"),
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
    tech_stack = detect_tech_stack(text)
    dark_patterns = detect_dark_patterns(text)
    consent_spec = generate_consent_spec(tech_stack, regulation)
    retention_policy = generate_retention_policy(tech_stack, regulation)

    business_info = {
        "company_name": company_name,
        "website_url": website_url,
        "contact_email": contact_email,
        "company_address": company_address,
    }
    privacy_policy = assemble_privacy_policy(tech_stack, regulation, business_info)

    third_party_count = sum(1 for t in tech_stack if t["third_party"])
    cross_border_count = sum(1 for t in tech_stack if t["cross_border"])
    consent_required = sum(1 for t in tech_stack if COMPLIANCE_RULES.get(regulation, {}).get(t["id"], {}).get("consent_required", False))

    return {
        "document_id": document_id,
        "regulation": regulation,
        "generated_at": datetime.utcnow().isoformat(),
        "tech_stack": tech_stack,
        "consent_spec": consent_spec,
        "retention_policy": retention_policy,
        "privacy_policy": privacy_policy,
        "dark_patterns": dark_patterns,
        "summary": {
            "technologies_detected": len(tech_stack),
            "third_party_services": third_party_count,
            "cross_border_services": cross_border_count,
            "consent_required_count": consent_required,
        }
    }

# ============== HEALTH & REGULATIONS ==============

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.5.0"}

@app.get("/api/v1/regulations")
def list_regulations():
    return {
        "regulations": [
            {
                "id": key,
                "name": value["name"],
                "region": value["region"],
                "checks_count": len(value["checks"])
            }
            for key, value in REGULATIONS.items()
        ]
    }

@app.post("/api/v1/compliance/email-report/{document_id}")
async def email_report(
    document_id: int,
    email_to: str,
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
        "breakdown": []
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

    message = MessageSchema(
        subject=f"Compliance Report: {doc.original_name}",
        recipients=[email_to],
        body=f"Your compliance report for {doc.original_name} is attached.\n\nScore: {doc.compliance_score}%\n\nGenerated by Compliance AI.",
        attachments=[{
            "file": pdf_bytes,
            "filename": f"compliance-report-{document_id}.pdf",
            "mime_type": "application/pdf"
        }]
    )

    await fm.send_message(message)

    return {"message": "Report emailed successfully"}