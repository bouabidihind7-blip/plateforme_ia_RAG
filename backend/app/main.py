# Importe FastAPI pour créer l’application backend.
from fastapi import FastAPI, HTTPException
# Importe CORSMiddleware pour autoriser le frontend à appeler le backend.
from fastapi.middleware.cors import CORSMiddleware
# Importe IntegrityError pour détecter un formulaire déjà importé (contrainte UNIQUE).
from sqlalchemy.exc import IntegrityError

# os.getenv() lit les variables d'environnement, load_dotenv() charge backend/.env.
import os
from pathlib import Path
from dotenv import load_dotenv

# Même schéma que database.py/ia_service.py : chaque fichier qui a besoin de variables
# d'environnement charge explicitement backend/.env lui-même, sans dépendre de l'ordre
# des imports pour que ce soit déjà fait.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
# Importe le modèle qui décrit la structure correcte d’un formulaire reçu.
from backend.app.schemas.formulaire import FormulaireEntree
# Importe le modèle qui vérifie le statut envoyé pour une réponse.
from backend.app.schemas.reponse import StatutReponseModification
# Importe la fonction qui enregistre le formulaire dans PostgreSQL.
from backend.app.services.formulaire_service import  enregistrer_formulaire, lister_formulaires
from backend.app.services.ia_service import extraire_formulaire_depuis_url
from backend.app.services.traitement_service import traiter_questions_textuelles
from backend.app.services.reponse_service import (
    lister_reponses_proposees,
    lister_reponses_par_formulaire,
    lister_historique_formulaire,
   modifier_statut_reponse,
)
# Crée l’application principale.
app = FastAPI(title="Plateforme IA de réponses aux formulaires")


# Autorise le(s) frontend(s) à communiquer avec ce backend — lu depuis .env (comme DB_HOST
# dans database.py), pas codé en dur, pour que chaque environnement (dev chez un développeur,
# production en entreprise) puisse avoir sa propre adresse sans jamais toucher ce fichier
# partagé. Plusieurs origines possibles à la fois, séparées par des virgules dans .env.
origines_autorisees = os.getenv("FRONTEND_URL", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origines_autorisees,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route simple utilisée pour vérifier que le backend fonctionne.
@app.get("/")
def accueil():
    return {"message": "Bienvenue sur l'API"}


# Route utilisée pour recevoir un formulaire envoyé au backend.
# POST signifie qu’on envoie des données au backend.
# status_code=201 signifie que la ressource a été reçue/créée avec succès.
@app.post("/formulaires", status_code=201)
def recevoir_formulaire(formulaire: FormulaireEntree):
    # Le formulaire est déjà validé automatiquement par Pydantic ici.

    # Enregistre le formulaire validé dans PostgreSQL.
    formulaire_db_id = enregistrer_formulaire(formulaire)

    return {
        "message": "Formulaire enregistré avec succès",
        "id": formulaire_db_id,
        "formulaire_id": formulaire.formulaire_id,
        "nombre_questions": len(formulaire.questions),
    }



@app.post("/traitements/questions-textuelles")
def lancer_traitement_questions_textuelles(formulaire_id: int, modele_ia: str = "gemini-3.1-flash-lite"):
    # Lance le traitement du formulaire précisé, avec le modèle IA choisi dans l’URL.
    resultats = traiter_questions_textuelles(formulaire_id, modele_ia)

    return {
        "message": "Traitement terminé",
        "modele_ia": modele_ia,
        "nombre_reponses": len(resultats),
        "resultats": resultats,
    }


@app.get("/reponses")
def lire_reponses():
    reponses = lister_reponses_proposees()

    return {
        "nombre_reponses": len(reponses),
        "reponses": reponses,
    }


@app.patch("/reponses/{reponse_id}/statut")
def changer_statut_reponse(
    reponse_id: int,
    modification: StatutReponseModification,
):
    # Modifie le statut dans PostgreSQL.
    reponse = modifier_statut_reponse(
        reponse_id=reponse_id,
        statut=modification.statut,
        commentaire=modification.commentaire,
        valeur=modification.valeur,
    )

    # Si l’id n’existe pas, aucune réponse n’a été modifiée.
    if reponse is None:
        return {
            "message": "Réponse introuvable",
            "reponse_id": reponse_id,
        }

    # Retourne la réponse mise à jour.
    return {
        "message": "Statut modifié avec succès",
        "reponse": reponse,
    }


@app.get("/formulaires")
def lire_formulaires():
    # Liste tous les formulaires importés — utilisé par la page historique.html pour
    # afficher un titre cliquable par formulaire, avant de choisir lequel consulter.
    formulaires = lister_formulaires()

    return {
        "nombre_formulaires": len(formulaires),
        "formulaires": formulaires,
    }


@app.get("/formulaires/{formulaire_id}/reponses")
def lire_reponses_formulaire(formulaire_id: int):
    # Récupère seulement les réponses liées à ce formulaire.
    reponses = lister_reponses_par_formulaire(formulaire_id)

    return {
        "formulaire_id": formulaire_id,
        "nombre_reponses": len(reponses),
        "reponses": reponses,
    }


@app.get("/formulaires/{formulaire_id}/historique")
def lire_historique_formulaire(formulaire_id: int):
    # Récupère TOUTES les réponses de ce formulaire (pas seulement la dernière par question).
    historique = lister_historique_formulaire(formulaire_id)

    return {
        "formulaire_id": formulaire_id,
        "nombre_reponses": len(historique),
        "historique": historique,
    }

# source.type (produit par l'extraction) ne s'écrit pas exactement pareil que fournisseur
# (attendu par FormulaireEntree/la contrainte SQL) — cette table fait la correspondance.
FOURNISSEUR_PAR_TYPE_SOURCE = {
    "google_forms_public": "google_forms",
    "microsoft_forms_scraping": "microsoft_forms",
}


@app.post("/formulaires/depuis-url", status_code=201)
def recevoir_formulaire_depuis_url(url: str):
    # Étape 1 : extrait le formulaire (détecte Google/Microsoft toute seule).
    formulaire_brut = extraire_formulaire_depuis_url(url)

    # Étape 2 : construit un FormulaireEntree validé — l'extraction ne produit ni
    # formulaire_id, ni un fournisseur dans le format exact attendu, donc on les
    # complète nous-mêmes ici, à partir de ce que l'extraction a réellement trouvé.
    formulaire = FormulaireEntree(
        formulaire_id=url,
        fournisseur=FOURNISSEUR_PAR_TYPE_SOURCE[formulaire_brut["source"]["type"]],
        titre=formulaire_brut["titre"],
        source=formulaire_brut["source"],
        description=formulaire_brut.get("description"),
        date_extraction=formulaire_brut.get("date_extraction"),
        statut_extraction=formulaire_brut.get("statut_extraction"),
        questions=formulaire_brut["questions"],
    )

    # Étape 3 : enregistre le formulaire validé — même fonction que POST /formulaires.
    # Un même lien déjà importé viole la contrainte UNIQUE (fournisseur, identifiant_externe) —
    # voulu, pas un bug (voir uq_formulaire_fournisseur_identifiant). Sans ce try/except, cette
    # IntegrityError remontait en erreur 500 non gérée, qui ne passe pas par le middleware CORS
    # (ServerErrorMiddleware, en dehors du CORS, génère la réponse) : le navigateur bloquait alors
    # la réponse et fetch() plantait côté frontend avant même de lire le code HTTP. Un 409 (déjà
    # géré par FastAPI) passe normalement par le CORS et laisse le frontend afficher un message clair.
    try:
        formulaire_db_id = enregistrer_formulaire(formulaire)
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Ce formulaire a déjà été importé.",
        )

    return {
        "message": "Formulaire importé et enregistré avec succès",
        "id": formulaire_db_id,
        "formulaire_id": formulaire.formulaire_id,
        "nombre_questions": len(formulaire.questions),
    }

