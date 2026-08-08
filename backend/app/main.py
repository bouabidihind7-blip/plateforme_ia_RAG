# Importe FastAPI pour créer l’application backend.
from fastapi import FastAPI

# Importe CORSMiddleware pour autoriser le frontend à appeler le backend.
from fastapi.middleware.cors import CORSMiddleware

# Importe le modèle qui décrit la structure correcte d’un formulaire reçu.
from backend.app.schemas.formulaire import FormulaireEntree

# Importe le modèle qui vérifie le statut envoyé pour une réponse.
from backend.app.schemas.reponse import StatutReponseModification

# Importe la fonction qui enregistre le formulaire dans PostgreSQL.
from backend.app.services.formulaire_service import enregistrer_formulaire

from backend.app.services.traitement_service import traiter_questions_textuelles

from backend.app.services.reponse_service import (
    lister_reponses_proposees,
    lister_reponses_par_formulaire,
    modifier_statut_reponse,
)

# Crée l’application principale.
app = FastAPI(title="Plateforme IA de réponses aux formulaires")


# Autorise le frontend local à communiquer avec ce backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Route simple utilisée pour vérifier que le backend fonctionne.
@app.get("/")
def accueil():
    # Retourne un message JSON.
    return {"message": "Bienvenue sur l'API"}


# Route utilisée pour recevoir un formulaire envoyé au backend.
# POST signifie qu’on envoie des données au backend.
# status_code=201 signifie que la ressource a été reçue/créée avec succès.
@app.post("/formulaires", status_code=201)
def recevoir_formulaire(formulaire: FormulaireEntree):
    # Le formulaire est déjà validé automatiquement par Pydantic ici.

    # Enregistre le formulaire validé dans PostgreSQL.
    formulaire_db_id = enregistrer_formulaire(formulaire)

    # Retourne une réponse simple au client.
    return {
        "message": "Formulaire enregistré avec succès",
        "id": formulaire_db_id,
        "formulaire_id": formulaire.formulaire_id,
        "nombre_questions": len(formulaire.questions),
    }



@app.post("/traitements/questions-textuelles")
def lancer_traitement_questions_textuelles(modele_ia: str = "modele_test"):
    # Lance le traitement avec le modèle IA choisi dans l’URL.
    resultats = traiter_questions_textuelles(modele_ia)

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


@app.get("/formulaires/{formulaire_id}/reponses")
def lire_reponses_formulaire(formulaire_id: int):
    # Récupère seulement les réponses liées à ce formulaire.
    reponses = lister_reponses_par_formulaire(formulaire_id)

    return {
        "formulaire_id": formulaire_id,
        "nombre_reponses": len(reponses),
        "reponses": reponses,
    }