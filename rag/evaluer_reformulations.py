"""
Même principe que evaluer_reponses.py, mais avec des questions reformulées TRÈS différemment
de celles déjà testées (mêmes faits/sujets, formulations jamais vues) — pour vérifier que la
classification par embedding local (retriever.py) généralise, pas seulement aux phrasings
qu'on a déjà utilisés pour la construire/tester.
À lancer : python rag/evaluer_reformulations.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.ia_service import proposer_reponse

# (question reformulée, mots-clés attendus) — même contenu que evaluer_reponses.py, jamais la
# même phrase.
QUESTIONS_TEST = [
    ("Est-ce que je peux travailler depuis chez moi en tant que stagiaire ?", ["2 jours", "deux jours"]),
    ("J'ai trois ans d'ancienneté, à combien de jours de vacances ai-je droit ?", ["25"]),
    ("J'ai oublié mon code PIN, que dois-je faire pour en choisir un nouveau ?", ["PIN Reset Tool", "réinitialis"]),
    ("Quel est le nom du responsable de l'atelier chez 3D Smart Factory ?", ["Hamza Fassi"]),
    ("En combien de temps PlastiMaroc livre-t-il ses commandes ?", ["5 jours"]),
    ("À qui dois-je m'adresser si j'ai une question sur mon salaire ?", ["Finance", "Salma Idrissi"]),
    ("Pourquoi la buse de l'imprimante FDM-02 s'est-elle bouchée ?", ["PETG carbonisé", "résidus"]),
    ("Quel est le seuil de résistance mécanique exigé lors des tests de compression ?", ["85"]),
    ("3D Smart Factory a-t-elle un objectif écologique concernant l'électricité ?", ["20"]),
    ("Où est-ce que l'entreprise achète son café ?", ["non disponible", "pas d'information", "aucune information", "ne contient pas"]),
    ("Peut-on rentrer dans l'atelier tout seul quand on est stagiaire ?", ["non"]),
    ("Quel programme sert à dessiner les pièces avant impression ?", ["SolidWorks"]),
    ("Nadia Chraibi travaille dans quelle équipe ?", ["Marketing"]),
    ("SolarNow, ça fait quoi comme entreprise ?", ["solaire"]),
    ("Faut-il un accompagnateur pour un stagiaire qui va à l'atelier avec son badge ?", ["oui", "technicien", "accompagn"]),
]


def construire_question(texte: str) -> dict:
    return {
        "question_id": "eval-reform",
        "texte_pour_ia": texte,
        "ocr": None,
        "type_question": "texte_libre",
        "titre_formulaire": None,
    }


def main():
    reussies = 0
    for texte_question, mots_cles_attendus in QUESTIONS_TEST:
        resultat = proposer_reponse(construire_question(texte_question))
        reponse = (resultat.get("reponse") or "").lower()

        reussi = any(mot_cle.lower() in reponse for mot_cle in mots_cles_attendus)
        reussies += reussi

        marqueur = "OK  " if reussi else "RATE"
        print(f"[{marqueur}] {texte_question}")
        print(f"        -> {resultat.get('reponse')}")
        print()

    print(f"Score : {reussies}/{len(QUESTIONS_TEST)}")


if __name__ == "__main__":
    main()
