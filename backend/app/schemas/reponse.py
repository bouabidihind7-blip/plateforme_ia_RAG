# Literal limite une valeur à une liste précise de choix autorisés.
from typing import Literal

# BaseModel crée un modèle qui valide le JSON reçu.
from pydantic import BaseModel


# Représente le JSON envoyé pour modifier le statut d’une réponse.
class StatutReponseModification(BaseModel):
    # Le statut accepté est seulement "validee" ou "rejetee".
    statut: Literal["validee", "rejetee"]

    # Commentaire facultatif ajouté par l’humain lors de la validation ou du rejet.
    commentaire: str | None = None
