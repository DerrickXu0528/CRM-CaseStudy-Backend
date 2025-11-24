from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import pandas as pd
import io
import anthropic
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

from database import SessionLocal, engine, Base
from models import Lead

# Load environment variables
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(title="CRM Lead Management API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                   "http://127.0.0.1:3000",
                   "https://crm-case-study-frontend.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic model for API responses
class LeadResponse(BaseModel):
    id: int
    company_name: str
    industry: str
    location: str
    contact_name: str
    contact_email: str
    contact_phone: str
    revenue: Optional[str] = None
    employees: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
    ai_score: Optional[int] = None
    ai_justification: Optional[str] = None
    ai_next_action: Optional[str] = None
   
    class Config:
        from_attributes = True

# Helper function to fetch and analyze website
def fetch_website_content(url):
    """Fetch and extract key information from a company website."""
    if not url or url == 'nan' or url == '':
        return None
   
    try:
        # Add https:// if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
       
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
       
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
       
        soup = BeautifulSoup(response.content, 'html.parser')
       
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
       
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
       
        title = soup.title.string if soup.title else ""
       
        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag:
            meta_desc = meta_tag.get('content', '')
       
        key_sections = []
        for heading in soup.find_all(['h1', 'h2', 'h3']):
            heading_text = heading.get_text().strip().lower()
            if any(keyword in heading_text for keyword in ['about', 'service', 'what we do', 'expertise', 'consulting']):
                section_text = ""
                for sibling in heading.find_next_siblings(['p', 'ul', 'div'], limit=3):
                    section_text += " " + sibling.get_text().strip()
                if section_text:
                    key_sections.append(section_text[:500])
       
        summary = {
            'title': title[:200] if title else "",
            'meta_description': meta_desc[:300] if meta_desc else "",
            'key_sections': ' '.join(key_sections)[:1000],
            'full_text_sample': text[:1500],
            'has_content': len(text) > 100,
            'url_analyzed': url
        }
       
        return summary
   
    except Exception as e:
        return {'error': f'Could not fetch website: {str(e)}', 'url_analyzed': url}

# Helper function to analyze email domain
def analyze_email_domain(email, website):
    """Check if email domain matches website domain."""
    if not email or email == 'nan' or email == '':
        return "No email provided"
   
    try:
        email_domain = email.split('@')[1].lower()
       
        generic_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com']
        if email_domain in generic_domains:
            return f"Generic email domain ({email_domain}) - less professional"
       
        if website and website != 'nan' and website != '':
            website_clean = website.replace('http://', '').replace('https://', '').replace('www.', '').split('/')[0].lower()
            if email_domain in website_clean or website_clean in email_domain:
                return f"Professional email - domain matches website ({email_domain})"
            else:
                return f"Email domain ({email_domain}) doesn't match website"
       
        return f"Professional email domain ({email_domain})"
   
    except:
        return "Invalid email format"

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "CRM API is running"}

# Upload CSV endpoint
@app.post("/upload")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a CSV file of leads and import them into the database."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
   
    try:
        contents = await file.read()
       
        # Read CSV WITHOUT header
        df = pd.read_csv(
            io.BytesIO(contents),
            header=None,
            names=[
                'id_uuid', 'company_name', 'location', 'industry',
                'col4', 'col5', 'col6', 'website',
                'col8', 'contact_email', 'col10',
                'col11', 'col12', 'col13', 'col14',
                'status', 'score', 'source', 'tags', 'notes',
                'col20', 'col21', 'col22', 'col23'
            ]
        )
       
        print(f"\n{'='*60}")
        print(f"CSV Upload - Total rows: {len(df)}")
        print(f"{'='*60}")
       
        if len(df) > 0:
            print("\nFirst row sample:")
            first_row = df.iloc[0]
            print(f"  Company: {first_row['company_name']}")
            print(f"  Location: {first_row['location']}")
            print(f"  Industry: {first_row['industry']}")
            print(f"  Website: {first_row['website']}")
            print(f"  Email: {first_row['contact_email']}")
            print(f"{'='*60}\n")
       
        added_count = 0
       
        for _, row in df.iterrows():
            # Extract contact name from email
            email = str(row.get('contact_email', ''))
            contact_name = ''
            if email and '@' in email and email != 'nan':
                contact_name = email.split('@')[0].replace('.', ' ').title()
           
            # Clean up values
            def clean_value(val):
                val_str = str(val)
                return '' if val_str == 'nan' else val_str
           
            lead = Lead(
                company_name=clean_value(row.get('company_name', '')),
                industry=clean_value(row.get('industry', '')),
                location=clean_value(row.get('location', '')),
                contact_name=contact_name,
                contact_email=clean_value(row.get('contact_email', '')),
                contact_phone='',
                revenue='',
                employees='',
                website=clean_value(row.get('website', '')),
                notes=clean_value(row.get('notes', ''))
            )
           
            db.add(lead)
            added_count += 1
       
        db.commit()
       
        print(f"✓ Successfully added {added_count} leads to database\n")
       
        return {
            "message": "CSV uploaded successfully",
            "leads_added": added_count
        }
   
    except Exception as e:
        import traceback
        print("ERROR uploading CSV:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")

# Get all leads
@app.get("/leads", response_model=List[LeadResponse])
def get_leads(
    industry: Optional[str] = None,
    location: Optional[str] = None,
    min_score: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all leads with optional filters."""
    query = db.query(Lead)
   
    if industry:
        query = query.filter(Lead.industry == industry)
    if location:
        query = query.filter(Lead.location.contains(location))
    if min_score:
        query = query.filter(Lead.ai_score >= min_score)
   
    leads = query.all()
    return leads

# Get single lead
@app.get("/leads/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    """Get details for a specific lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
   
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
   
    return lead

# Delete a lead
@app.delete("/leads/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    """Delete a lead by ID."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
   
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
   
    db.delete(lead)
    db.commit()
   
    return {"message": "Lead deleted successfully"}

# Get filter options
@app.get("/filters")
def get_filter_options(db: Session = Depends(get_db)):
    """Get unique industries and locations."""
    industries = db.query(Lead.industry).distinct().all()
    locations = db.query(Lead.location).distinct().all()
   
    return {
        "industries": [i[0] for i in industries if i[0]],
        "locations": [l[0] for l in locations if l[0]]
    }

# Clear all leads
@app.delete("/clear-all")
def clear_all_leads(db: Session = Depends(get_db)):
    """Delete all leads - FOR TESTING ONLY!"""
    count = db.query(Lead).count()
    db.query(Lead).delete()
    db.commit()
   
    return {
        "message": f"All {count} leads deleted successfully",
        "leads_deleted": count
    }

# Score a lead with AI - ENHANCED VERSION
@app.post("/leads/{lead_id}/score")
async def score_lead(lead_id: int, db: Session = Depends(get_db)):
    """
    Use Claude AI to score a lead's quality with deep analysis.
    Fetches website content and analyzes email legitimacy.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
   
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
   
    try:
        print(f"\n{'='*60}")
        print(f"Scoring Lead {lead_id}: {lead.company_name}")
        print(f"{'='*60}")
       
        # Fetch and analyze website
        print(f"Website: {lead.website}")
        website_analysis = fetch_website_content(lead.website)
       
        if website_analysis:
            if 'error' in website_analysis:
                print(f"  ✗ Error: {website_analysis['error']}")
            else:
                print(f"  ✓ Fetched successfully")
                print(f"    Title: {website_analysis.get('title', 'N/A')[:80]}")
        else:
            print("  - No website to analyze")
       
        # Analyze email
        print(f"Email: {lead.contact_email}")
        email_analysis = analyze_email_domain(lead.contact_email, lead.website)
        print(f"  Analysis: {email_analysis}")
       
        # Build prompt for Claude
        prompt = f"""You are an expert sales consultant analyzing leads for a consulting services company.

=== LEAD BASIC INFORMATION ===
Company: {lead.company_name}
Industry: {lead.industry}
Location: {lead.location}
Contact: {lead.contact_name}
Email: {lead.contact_email}
Website: {lead.website}

=== EMAIL ANALYSIS ===
{email_analysis}

=== WEBSITE ANALYSIS ===
"""

        if website_analysis and 'error' not in website_analysis:
            prompt += f"""
✓ Website Successfully Analyzed: {website_analysis.get('url_analyzed')}

Page Title: {website_analysis.get('title', 'Not found')}
Meta Description: {website_analysis.get('meta_description', 'Not found')}

Key Content:
{website_analysis.get('key_sections', 'No key sections found')}

Website Content Sample:
{website_analysis.get('full_text_sample', 'No content')}

Status: Active and accessible with {'professional' if website_analysis.get('has_content') else 'limited'} content
"""
        elif website_analysis and 'error' in website_analysis:
            prompt += f"""
✗ Website Analysis FAILED
Error: {website_analysis['error']}
RED FLAG: Website may be down, blocked, or non-existent.
"""
        else:
            prompt += """
✗ NO WEBSITE PROVIDED
RED FLAG: Professional consulting companies should have websites.
"""

        prompt += """

=== SCORING CRITERIA ===

Score from 0-100 based on these criteria:

**Website Quality (0-30 points):**
- 30: Excellent professional site with detailed services, case studies, team info
- 20: Good professional site with clear services
- 10: Basic site with limited info
- 5: Website exists but poor quality or inaccessible
- 0: No website

**Contact Legitimacy (0-25 points):**
- 25: Professional email matching website domain + contact name
- 15: Professional email matching domain
- 10: Professional email (not generic)
- 5: Generic email (gmail, yahoo)
- 0: No valid email

**Industry Fit (0-20 points):**
- 20: Clearly consulting company (evident from website/notes)
- 10: Likely consulting but not strongly evident
- 0: Not a consulting company

**Company Legitimacy (0-15 points):**
- Based on: location, website quality, email professionalism
- 15: All indicators positive
- 10: Most indicators positive
- 5: Mixed signals
- 0: Red flags

**Information Completeness (0-10 points):**
- 10: Complete info (name, email, website, location)
- 5: Most info present
- 0: Very limited info

**Respond in this EXACT format:**

SCORE: [number 0-100]
JUSTIFICATION: [2-3 sentences explaining score based on actual website content and analysis. BE SPECIFIC.]
NEXT_ACTION: [one specific actionable next step]

Example good justification: "Score of 85 because website shows established consulting firm with case studies in manufacturing sector. Professional email domain matches website. Clear service offerings in strategy consulting with 15+ years experience stated."

Now analyze this lead:"""

        # Call Claude API
        print("Calling Claude API...")
        client = anthropic.Anthropic(api_key=api_key)
       
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
       
        response_text = message.content[0].text
        print(f"\nClaude Response:\n{response_text[:200]}...\n")
       
        # Parse response
        score = None
        justification = ""
        next_action = ""
       
        lines = response_text.strip().split('\n')
        for i, line in enumerate(lines):
            if line.startswith('SCORE:'):
                score_text = line.replace('SCORE:', '').strip()
                import re
                numbers = re.findall(r'\d+', score_text)
                if numbers:
                    score = int(numbers[0])
            elif line.startswith('JUSTIFICATION:'):
                justification = line.replace('JUSTIFICATION:', '').strip()
                for next_line in lines[i+1:]:
                    if next_line.startswith('NEXT_ACTION:'):
                        break
                    justification += " " + next_line.strip()
            elif line.startswith('NEXT_ACTION:'):
                next_action = line.replace('NEXT_ACTION:', '').strip()
                for next_line in lines[i+1:]:
                    next_action += " " + next_line.strip()
       
        # Fallback
        if score is None:
            score = 50
        if not justification:
            justification = response_text[:400]
        if not next_action:
            next_action = "Review lead and determine outreach strategy"
       
        score = max(0, min(100, score))
        justification = ' '.join(justification.split())[:500]
        next_action = ' '.join(next_action.split())[:300]
       
        # Update database
        lead.ai_score = score
        lead.ai_justification = justification
        lead.ai_next_action = next_action
        db.commit()
       
        print(f"✓ Final Score: {score}/100")
        print(f"{'='*60}\n")
       
        return {
            "lead_id": lead_id,
            "score": score,
            "justification": justification,
            "next_action": next_action,
            "website_analyzed": website_analysis is not None and 'error' not in website_analysis
        }
   
    except Exception as e:
        import traceback
        print("ERROR scoring lead:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error scoring lead: {str(e)}")