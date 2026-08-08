# Importe la fonction qui lit les questions depuis PostgreSQL.
from backend.app.services.formulaire_service import lister_questions_textuelles_a_traiter

# Importe la fonction qui propose une réponse.
from backend.app.services.ia_service import proposer_reponse

# Importe la fonction qui enregistre une réponse.
from backend.app.services.reponse_service import enregistrer_reponse_proposee


# Lance le traitement des questions textuelles avec le modèle IA choisi.
def traiter_questions_textuelles(modele_ia: str = "modele_test") -> list[dict]:
    # Récupère les questions qui peuvent être traitées par ce modèle maintenant.
    questions = lister_questions_textuelles_a_traiter(modele_ia)

    # Liste qui contiendra le résumé du traitement.
    resultats = []

    # Parcourt chaque question récupérée.
    for question in questions:

        # Demande au service IA choisi de proposer une réponse.
        reponse = proposer_reponse(question, modele_ia)

        # Enregistre la réponse proposée dans PostgreSQL.
        reponse_db_id = enregistrer_reponse_proposee(reponse)

        # Ajoute un résumé du traitement.
        resultats.append(
            {
                "question_id": question["id"],
                "reponse_id": reponse_db_id,
                "modele_ia": modele_ia,
                "valeur": reponse["valeur"],
            }
        )

    # Retourne la liste des réponses enregistrées.
    return resultats
