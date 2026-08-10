# Importe les fonctions qui rechargent un formulaire déjà importé depuis PostgreSQL.
from backend.app.services.formulaire_service import (
    charger_formulaire_pour_generation,
    lister_questions_deja_repondues,
)

# Importe la fonction qui génère les réponses de tout un formulaire (déjà écrite et
# éprouvée dans ia_service.py — on la réutilise telle quelle, sans réécrire la boucle
# nous-mêmes, pour garder le parallélisme (ThreadPoolExecutor) déjà en place).
from backend.app.services.ia_service import generer_reponses_formulaire

# Importe la fonction qui enregistre une réponse.
from backend.app.services.reponse_service import enregistrer_reponse_proposee


# Lance le traitement de toutes les questions d'un formulaire avec le modèle IA choisi.
def traiter_questions_textuelles(formulaire_id: int, modele_ia: str = "gemini-3.1-flash-lite") -> list[dict]:
    # Recharge le formulaire complet depuis PostgreSQL, sous la forme attendue par ia_service.py.
    formulaire = charger_formulaire_pour_generation(formulaire_id)

    # id_interne de chaque question, retrouvé par son identifiant externe (question_id) —
    # nécessaire puisque generer_reponses_formulaire identifie ses réponses par question_id
    # (l'identifiant externe), mais reponses_proposees a besoin de l'id interne PostgreSQL.
    id_interne_par_question_id = {
        question["question_id"]: question["id_interne"]
        for question in formulaire["questions"]
    }

    # Ignore les questions qui ont déjà une réponse de CE modèle — évite de rappeler Gemini
    # (coûteux) et de créer des doublons dans reponses_proposees si le traitement est relancé
    # sur un formulaire déjà (partiellement) traité.
    deja_repondues = lister_questions_deja_repondues(formulaire_id, modele_ia)
    formulaire["questions"] = [
        question for question in formulaire["questions"]
        if question["question_id"] not in deja_repondues
    ]

    # Génère les réponses pour les questions restantes — même fonction, même parallélisme,
    # que le formulaire vienne d'une extraction fraîche ou d'un rechargement depuis la base.
    resultat = generer_reponses_formulaire(formulaire)

    # Liste qui contiendra le résumé du traitement.
    resultats = []

    # Parcourt chaque réponse générée.
    for reponse in resultat["reponses"]:

        # Une question dont proposer_reponse a échoué a "reponse": None — pas de valeur à
        # enregistrer, on la retente au prochain traitement plutôt que d'écrire un NULL.
        if reponse["reponse"] is None:
            continue

        question_db_id = id_interne_par_question_id[reponse["question_id"]]

        # Enregistre la réponse proposée dans PostgreSQL.
        reponse_db_id = enregistrer_reponse_proposee(
            {
                "question_id": question_db_id,
                "type_reponse": next(
                    q["type_reponse_attendu"] for q in formulaire["questions"]
                    if q["question_id"] == reponse["question_id"]
                ),
                "valeur": reponse["reponse"],
                "modele_ia": modele_ia,
                "methode_traitement": "texte",
            }
        )

        # Ajoute un résumé du traitement.
        resultats.append(
            {
                "question_id": question_db_id,
                "reponse_id": reponse_db_id,
                "modele_ia": modele_ia,
                "valeur": reponse["reponse"],
            }
        )

    # Retourne la liste des réponses enregistrées.
    return resultats
