# Version automatisée (pytest) de test_extraction_texte.py : mêmes 3 cas, mais avec assert
# au lieu de print. Une fois ce fichier en place, test_extraction_texte.py peut être supprimé.

from extraction_questions import extraire_question_textuelle


def test_texte_libre_est_bien_reconnu():
    question_brute = {
        "texte": "Quelle est la capitale du Maroc ?",
        "type_brut": "text",
        "options": []
    }

    resultat = extraire_question_textuelle(question_brute, ordre=1)

    assert resultat["type_question"] == "texte_libre"
    assert resultat["type_reponse_attendu"] == "texte"
    assert resultat["options"] == []


def test_choix_unique_est_bien_reconnu():
    question_brute = {
        "texte": "Choisissez la capitale du Maroc.",
        "type_brut": "radio",
        "options": ["Rabat", "Casablanca", "Fès"]
    }

    resultat = extraire_question_textuelle(question_brute, ordre=2)

    assert resultat["type_question"] == "choix_unique"
    assert resultat["type_reponse_attendu"] == "option_unique"
    assert len(resultat["options"]) == 3
    assert resultat["options"][0]["texte"] == "Rabat"


def test_choix_multiple_est_bien_reconnu():
    question_brute = {
        "texte": "Sélectionnez les nombres pairs.",
        "type_brut": "checkbox",
        "options": ["1", "2", "3", "4"]
    }

    resultat = extraire_question_textuelle(question_brute, ordre=3)

    assert resultat["type_question"] == "choix_multiple"
    assert resultat["type_reponse_attendu"] == "options_multiples"
    assert len(resultat["options"]) == 4
