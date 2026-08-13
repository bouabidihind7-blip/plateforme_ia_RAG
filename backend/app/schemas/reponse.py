# Literal limite une valeur à une liste précise de choix autorisés.
from typing import Literal

# BaseModel crée un modèle qui valide le JSON reçu.
from pydantic import BaseModel


# Représente le JSON envoyé pour modifier le statut d’une réponse.
class StatutReponseModification(BaseModel):
    # Le statut accepté est "validée" ou "rejetée" (avec accent — bonne orthographe française,
    # choisie volontairement) — même valeurs que chk_reponse_statut côté SQL et que ce
    # qu'envoie script.js, les 3 doivent rester synchronisés.
    statut: Literal["validée", "rejetée"]

    # Commentaire facultatif ajouté par l’humain lors de la validation ou du rejet.
    commentaire: str | None = None

    # Valeur corrigée à la main par l’humain (bouton "Ajuster" dans le frontend) — quand
    # elle est fournie, elle remplace la réponse proposée par l’IA. None = pas de correction,
    # on garde la valeur générée par l’IA telle quelle.
    valeur: str | None = None
