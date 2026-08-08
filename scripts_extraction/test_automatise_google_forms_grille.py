# Test de régression pour un bug réel trouvé sur un vrai formulaire (2026-07-27) :
# le type général Google Forms (question_google[3] == 7) ne suffit pas à distinguer une
# grille à choix unique d'une grille à cases à cocher — les deux partagent le même type 7.
# Le vrai signal est le dernier élément de la première ligne : [0] = choix unique,
# [1] = cases à cocher. Voir grille_est_choix_unique dans google_forms_public.py.

from google_forms_public import grille_est_choix_unique, convertir_question_google


def construire_grille_google(indicateur):
    # Structure minimale reproduisant fidèlement une grille réelle scrapée.
    return [
        123456,
        "Titre de la grille",
        None,
        7,
        [
            [
                987654,
                [["colonne1"], ["colonne2"]],
                0,
                ["ligne1"],
                None, None, None, None, None, None, None,
                indicateur,
            ]
        ],
    ]


def test_indicateur_0_est_choix_unique():
    assert grille_est_choix_unique(construire_grille_google([0])) is True


def test_indicateur_1_est_cases_a_cocher():
    assert grille_est_choix_unique(construire_grille_google([1])) is False


def test_convertir_question_google_reclasse_en_grille_choix_unique():
    resultat = convertir_question_google(construire_grille_google([0]))
    assert resultat["type_brut"] == "grille_choix_unique"


def test_convertir_question_google_garde_grille_choix_multiple():
    resultat = convertir_question_google(construire_grille_google([1]))
    assert resultat["type_brut"] == "grille_choix_multiple"
