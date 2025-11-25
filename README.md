### Prerequisites

- Python 3.11 or higher
- Git
- Anthropic API key ([Please Contact Developer](https://console.anthropic.com/))

### Local Development Setup

#### Backend Setup
```bash
# Clone the repository
git clone https://github.com/DerrickXu0528/CRM-CaseStudy-Backend.git
cd CRM-CaseStudy-Backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo "ANTHROPIC_API_KEY=Please Contact Developer" > .env

# Run the server
uvicorn main:app --reload
```

Backend will run at: `http://127.0.0.1:8000`

API Docs available at: `http://127.0.0.1:8000/docs`
