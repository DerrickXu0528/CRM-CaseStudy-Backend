from sqlalchemy import create_engine, Column, Integer, String, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# EXPLANATION: This creates a SQLite database file called "leads.db"
# SQLite is perfect for small projects - no server needed!
SQLALCHEMY_DATABASE_URL = "sqlite:///./leads.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # Needed for SQLite
)

# SessionLocal: This is how we'll talk to the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base: All our database models will inherit from this
Base = declarative_base()