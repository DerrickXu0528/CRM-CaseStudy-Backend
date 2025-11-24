from sqlalchemy import Column, Integer, String, Text
from database import Base

class Lead(Base):
    __tablename__ = "leads"
   
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, index=True)
    industry = Column(String, index=True)
    location = Column(String)
    contact_name = Column(String)
    contact_email = Column(String)
    contact_phone = Column(String)
    revenue = Column(String, nullable=True)
    employees = Column(String, nullable=True)
    website = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
   
    # AI scoring fields
    ai_score = Column(Integer, nullable=True)
    ai_justification = Column(Text, nullable=True)
    ai_next_action = Column(Text, nullable=True)