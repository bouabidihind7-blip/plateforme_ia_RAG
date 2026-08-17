"""
Petit script d'évaluation du pipeline RAG complet (retriever + génération réelle via
ia_service.proposer_reponse, pas juste rag_chain.py) — une liste de questions avec leur
réponse attendue, pour mesurer en un coup si un changement (format des documents, réglages
du chunking...) améliore ou casse les résultats, plutôt que de tester une question à la main
à chaque fois.
Un "mot-clé attendu" (pas une correspondance exacte) suffit pour compter une réponse comme
correcte — la formulation exacte de Gemini varie d'un appel à l'autre.
À relancer à chaque changement de format/chunking : python rag/evaluer_reponses.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.ia_service import proposer_reponse

# (question, mots-clés attendus, titre_formulaire) — le titre est nécessaire depuis le
# filtrage par catégorie : construire_prompt devine la catégorie à partir de LUI (voir
# deviner_categorie dans ia_service.py), pas à partir du texte de la question elle-même —
# sans titre réaliste ici, tout tomberait dans qa_general, même les questions IT/Finance/
# Production, faussant le test.
QUESTIONS_TEST = [
    ("Qui est responsable du département communication ?", ["Nadia Chraibi"], "Sondage entreprise"),
    ("Dans quel secteur travaille la startup SolarNow ?", ["solaire"], "Sondage entreprise"),
    ("Combien de jours de télétravail par semaine sont autorisés pour les stagiaires ?", ["2 jours", "deux jours"], "Sondage RH"),
    ("Combien de jours de congés a-t-on après 3 ans d'ancienneté ?", ["25"], "Sondage RH"),
    ("Où se trouvent les locaux du département Marketing ?", ["1er étage", "premier étage"], "Sondage entreprise"),
    ("Qui dirige le département Incubation Startups ?", ["responsable incubation", "Rachid Ouazzani"], "Sondage entreprise"),
    ("Est-ce que 3D Smart Factory fournit un ordinateur portable aux stagiaires ?", ["oui"], "Sondage RH"),
    ("Quelles sont les horaires de travail habituels ?", ["9h", "17h30"], "Sondage RH"),
    ("Comment réinitialiser un PIN oublié ?", ["PIN Reset Tool", "réinitialis"], "Sondage sécurité informatique"),
    # Nouveau fichier format_standard_prototype_2.txt (sujets différents : production, qualité, sécurité, client).
    ("Qui dirige l'atelier de production ?", ["Hamza Fassi"], "Sondage production"),
    ("Quel logiciel est utilisé pour la conception des pièces ?", ["SolidWorks"], "Sondage production"),
    ("Quelle matière première est utilisée pour l'impression FDM ?", ["PLA", "PETG"], "Sondage production"),
    ("Un stagiaire peut-il accéder seul à l'atelier de production ?", ["non"], "Sondage production"),
    ("Qui est responsable de la relation client ?", ["Leila Benjelloun"], "Sondage commercial"),
    ("Quel est le délai moyen de production d'une commande client ?", ["5 jours"], "Sondage commercial"),
    # Nouveau fichier format_standard_prototype_3.txt (généré par l'agent de standardisation,
    # pas écrit à la main — sécurité informatique, badges, Wi-Fi).
    ("Tous les combien de temps faut-il changer son mot de passe réseau ?", ["90 jours"], "Sondage sécurité informatique"),
    ("Qui dirige le service informatique ?", ["Youssef El Amrani"], "Sondage sécurité informatique"),
    ("Un stagiaire peut-il accéder à l'atelier de production avec son badge, sans accompagnement ?", ["non"], "Sondage sécurité informatique"),
    ("Que se passe-t-il après 5 échecs de connexion consécutifs ?", ["30 minutes"], "Sondage sécurité informatique"),
    ("Sous combien de temps un nouveau badge est-il disponible après une perte ?", ["3 jours"], "Sondage sécurité informatique"),
    # Cas de synthèse : la réponse complète du processus de candidature demande d'assembler
    # plusieurs sous-questions différentes (généré par l'agent) — test de complétude.
    ("Comment se déroule le processus de candidature pour être incubé chez 3D Smart Factory ?", ["dossier", "comité de sélection"], "Sondage recrutement"),
    # Agent testé sur 3 nouveaux formats bruts : CSV (fournisseurs), PDF (politique
    # environnementale), XLSX (inventaire machines) — aucun n'existait avant aujourd'hui.
    ("Quel est le délai de livraison du fournisseur PlastiMaroc ?", ["5 jours"], "Sondage fournisseurs"),
    ("Quel matériau fournit MetalPrint ?", ["poudre métallique"], "Sondage fournisseurs"),
    ("Qui retraite les chutes de filament de 3D Smart Factory ?", ["NordFil"], "Sondage fournisseurs"),
    ("Quel est l'objectif de réduction de la consommation électrique de 3D Smart Factory ?", ["20"], "Sondage production"),
    ("Quel est le statut de l'imprimante FDM-03 ?", ["en maintenance"], "Sondage production"),
    ("Quel est le numéro de série de la découpeuse laser-01 ?", ["LAS-2024-002"], "Sondage production"),
    # Agent testé sur 3 formats supplémentaires, avec du contenu dense/technique exprès pour
    # chercher les cas limites : DOCX (procédure qualité, 3 paragraphes longs), JSON (journal
    # d'incidents, descriptions longues), MD (guide interne avec titres et paragraphes denses).
    ("Quelle est la tolérance maximale acceptée lors du contrôle dimensionnel ?", ["0.2 millimètre", "0,2 millimètre"], "Sondage qualité production"),
    ("Quelle force de rupture minimale l'échantillon doit-il atteindre lors du test de compression ?", ["85"], "Sondage qualité production"),
    ("Quelle est la cause du blocage de la buse d'extrusion sur l'imprimante FDM-02 ?", ["PETG carbonisé", "résidus"], "Sondage incidents production"),
    ("Combien de temps l'imprimante SLS-01 est-elle restée immobilisée suite à l'incident INC-2026-016 ?", ["72 heures", "3 jours"], "Sondage incidents production"),
    ("Quel est le volume d'impression maximal des imprimantes FDM de 3D Smart Factory ?", ["300x300x400", "300 x 300 x 400"], "Sondage gestion commerciale"),
    ("Que doit préciser Leila Benjelloun dans l'e-mail envoyé au client en cas de retard ?", ["cause du retard"], "Sondage gestion commerciale"),
    # Cas piège : réponse absente des documents — l'IA ne doit JAMAIS inventer.
    ("Quel est le nom du fournisseur de café utilisé dans les bureaux ?", ["non disponible", "pas d'information", "aucune information", "ne contient pas"], "Sondage entreprise"),
]


def construire_question(texte: str, titre_formulaire: str) -> dict:
    return {
        "question_id": "eval",
        "texte_pour_ia": texte,
        "ocr": None,
        "type_question": "texte_libre",
        "titre_formulaire": titre_formulaire,
    }


def main():
    reussies = 0
    for texte_question, mots_cles_attendus, titre_formulaire in QUESTIONS_TEST:
        resultat = proposer_reponse(construire_question(texte_question, titre_formulaire))
        reponse = (resultat.get("reponse") or "").lower()

        reussi = any(mot_cle.lower() in reponse for mot_cle in mots_cles_attendus)
        reussies += reussi

        marqueur = "OK  " if reussi else "RATE"
        print(f"[{marqueur}] ({titre_formulaire}) {texte_question}")
        print(f"        -> {resultat.get('reponse')}")
        print()

    print(f"Score : {reussies}/{len(QUESTIONS_TEST)}")


if __name__ == "__main__":
    main()
