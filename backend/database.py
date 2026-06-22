from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Create SQLite database file (compliance.db will appear in your backend folder)
engine = create_engine("sqlite:///./compliance.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DocumentDB(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    original_name = Column(String)
    extracted_text = Column(Text)
    compliance_score = Column(Float, default=0)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

class ComplianceGapDB(Base):
    __tablename__ = "gaps"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer)
    regulation = Column(String)
    section = Column(String)
    severity = Column(String)
    description = Column(Text)
    suggestion = Column(Text)

# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()