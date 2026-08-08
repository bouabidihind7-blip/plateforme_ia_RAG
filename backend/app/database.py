# Permet de lire les variables d’environnement comme DB_USER.
import os

# Permet de construire le chemin vers le fichier backend/.env.
from pathlib import Path

# Permet de charger les valeurs contenues dans le fichier .env.
from dotenv import load_dotenv

# URL construit l’adresse PostgreSQL.
# create_engine prépare la communication avec PostgreSQL.
from sqlalchemy import URL, create_engine

# sessionmaker permet de créer des sessions de travail avec la base.
from sqlalchemy.orm import sessionmaker


# __file__ représente le fichier database.py actuel.
# parent correspond au dossier app.
# parent.parent correspond au dossier backend.
# On ajoute ensuite le nom du fichier .env.
env_path = Path(__file__).resolve().parent.parent / ".env"

# Charge les variables du fichier backend/.env.
# Après cette ligne, os.getenv() peut les lire.
load_dotenv(env_path)


# Construit proprement l’adresse de connexion PostgreSQL.
database_url = URL.create(

    # Indique que nous utilisons PostgreSQL avec le pilote Psycopg.
    drivername="postgresql+psycopg",

    # Lit l’utilisateur PostgreSQL depuis DB_USER dans .env.
    username=os.getenv("DB_USER"),

    # Lit le mot de passe PostgreSQL sans l’écrire dans le code.
    password=os.getenv("DB_PASSWORD"),

    # Lit l’adresse du serveur, normalement localhost.
    host=os.getenv("DB_HOST"),

    # Lit le port et le transforme en nombre entier.
    # Si DB_PORT manque, le port PostgreSQL 5432 sera utilisé.
    port=int(os.getenv("DB_PORT", "5432")),

    # Lit le nom de notre base plateforme_ia.
    database=os.getenv("DB_NAME"),
)


# Crée le moteur utilisé par SQLAlchemy pour parler à PostgreSQL.
# Cette ligne prépare la connexion, mais ne l’ouvre pas immédiatement.
# pool_pre_ping vérifie qu’une connexion est valide avant de l’utiliser.
engine = create_engine(database_url, pool_pre_ping=True)


# Prépare un fabricant de sessions.
# Une session servira à lire, ajouter ou modifier des données.
SessionLocal = sessionmaker(

    # Associe chaque nouvelle session à notre moteur PostgreSQL.
    bind=engine,

    # Évite l’envoi automatique prématuré des changements.
    autoflush=False,

    # Garde les données accessibles après leur enregistrement.
    expire_on_commit=False,
)