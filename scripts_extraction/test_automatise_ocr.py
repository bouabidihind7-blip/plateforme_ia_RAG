# Version automatisée (pytest) de test_ocr.py.
#
# ATTENTION : contrairement aux autres tests (qui tournent en une fraction de seconde),
# celui-ci appelle vraiment EasyOCR (chargement du modèle + inférence) — plusieurs
# secondes à chaque exécution. Un `pytest` normal l'exécutera avec le reste, donc si tu
# veux exclure les tests lents au quotidien, on peut ajouter un marqueur @pytest.mark.slow
# plus tard (demande-le si tu veux ça).

from pathlib import Path

from ocr_utils import extraire_texte_image

# Chemin basé sur l'emplacement de ce fichier, pas sur le dossier courant : fonctionne
# qu'on lance pytest depuis la racine du projet ou depuis scripts_extraction/.
CHEMIN_IMAGE_TEST = Path(__file__).resolve().parent / "images_test" / "question_test.png"


def test_ocr_extrait_du_texte_non_vide():
    resultat = extraire_texte_image(str(CHEMIN_IMAGE_TEST))

    assert resultat["texte_extrait"] != ""
    assert resultat["score_confiance"] > 0
    assert resultat["nb_mots"] > 0
