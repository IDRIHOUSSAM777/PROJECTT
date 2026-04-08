from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# ⚠️ Remplace par tes infos : user:password@localhost/nom_de_ta_base
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:1234@127.0.0.1:5432/smartbuilding_db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Fonction utilitaire pour récupérer la session DB dans chaque requête
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()