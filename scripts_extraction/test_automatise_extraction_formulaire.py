# Version automatisée (pytest) de test_extraction_formulaire.py : mêmes 4 cas (1 normal,
# 3 cas d'erreur), avec assert au lieu de print. Une fois ce fichier en place,
# test_extraction_formulaire.py peut être supprimé.

from extraction_questions import extraire_formulaire


def construire_formulaire_test():
    return {
        "source": {
            "type": "simulation",
            "url": None
        },
        "titre": "Formulaire test avec erreurs",
        "description": "Formulaire utilisé pour tester les statuts d'erreur.",
        "questions": [
            {
                "texte": "Quelle est la capitale du Maroc ?",
                "type_brut": "text",
                "options": []
            },
            {
                "texte": "",
                "type_brut": "radio",
                "options": ["Oui", "Non"]
            },
            {
                "texte": "Choisissez une réponse.",
                "type_brut": "radio",
                "options": []
            },
            {
                "texte": "Question avec type inconnu.",
                "type_brut": "slider",
                "options": ["1", "2", "3"]
            }
        ]
    }


def test_question_normale_est_prete():
    resultat = extraire_formulaire(construire_formulaire_test())
    question = resultat["questions"][0]

    assert question["type_question"] == "texte_libre"
    assert question["statut_extraction"] == "prete"


def test_texte_vide_donne_statut_texte_manquant():
    resultat = extraire_formulaire(construire_formulaire_test())
    question = resultat["questions"][1]

    assert question["texte"] == ""
    assert question["statut_extraction"] == "texte_manquant"


def test_choix_sans_options_donne_statut_options_manquantes():
    resultat = extraire_formulaire(construire_formulaire_test())
    question = resultat["questions"][2]

    assert question["options"] == []
    assert question["statut_extraction"] == "options_manquantes"


def test_type_brut_inconnu_donne_type_inconnu():
    resultat = extraire_formulaire(construire_formulaire_test())
    question = resultat["questions"][3]

    assert question["type_question"] == "type_inconnu"
    assert question["type_reponse_attendu"] == "inconnu"
    assert question["statut_extraction"] == "type_inconnu"


def test_formulaire_avec_erreurs_a_statut_partiel():
    resultat = extraire_formulaire(construire_formulaire_test())

    assert resultat["statut_extraction"] == "partiel"
