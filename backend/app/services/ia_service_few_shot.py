# Copie EXACTE du vrai backend/app/services/ia_service.py, avec UN seul ajout : un exemple
# few-shot sélectif pour le cas prouvé aujourd'hui (options préfixées d'une lettre, ex "C.   ...")
# — ajouté SEULEMENT quand les vraies options de la question en contiennent un, pas pour toutes
# les questions choix_unique. Tout le reste est identique au fichier original, pour une
# comparaison honnête : à toi de lancer les deux sur les mêmes formulaires et de comparer.
import sys
from pathlib import Path
import json
import os
import re
import time

racine_projet = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(racine_projet / "scripts_extraction"))

from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from google_forms_public import extraire_formulaire_google_public
from microsoft_forms_scraper import extraire_formulaire_microsoft

DetectorFactory.seed = 0

env_path = racine_projet / "backend" / ".env"
load_dotenv(env_path)


class ReponseAgent(BaseModel):
    valeur: str
    precision_autre: str | None = None

google_api_key = os.getenv("GEMINI_API_KEY")
modele = ChatGoogleGenerativeAI(
   model="gemini-3.5-flash-lite",
   temperature=0.2,
   google_api_key=google_api_key,
)

agent=create_agent(model=modele, tools=[], system_prompt=(
    "Tu remplis un formulaire à la place d'un utilisateur qui y répond. "
    "Pour chaque question, imagine et donne une réponse plausible, comme si tu étais "
    "cette personne — ne parle jamais de toi-même en tant qu'IA ou assistant. "
    "Donne toujours une réponse concrète, même approximative si tu n'es pas sûr — "
    "ne pose jamais de question de clarification en retour, personne ne pourra te répondre. "
    "Si des choix possibles sont donnés dans la question, réponds avec le texte EXACT "
    "du ou des choix concernés, sans le reformuler ni l'abréger — certaines questions "
    "acceptent plusieurs choix à la fois, respecte ce que la question demande. "
    "Si tu choisis l'option 'Other'/'Autre' (parce qu'aucun des autres choix ne convient), "
    "tu DOIS aussi remplir precision_autre avec une réponse concrète et plausible qui explique "
    "ce que tu veux dire — ne réponds jamais juste 'Other' ou 'Autre' sans précision. Pour "
    "toutes les autres réponses, laisse precision_autre vide. "
    "Si la question demande de joindre un document (CV, lettre de motivation...) mais que la "
    "réponse attendue est un simple champ texte (pas un vrai bouton de dépôt de fichier), "
    "n'invente JAMAIS un nom de fichier — écris directement le contenu texte plausible du "
    "document à la place (ex : le texte d'une courte lettre de motivation), comme si tu le "
    "collais dans le champ. "
    "IMPORTANT — langue : détecte la langue EXACTE dans laquelle la question est écrite (le "
    "texte de la question lui-même, pas la langue de ces instructions) et réponds strictement "
    "dans cette même langue, du début à la fin, sans jamais changer de langue en cours de "
    "réponse ni traduire dans une autre langue par défaut."
)
,response_format=ReponseAgent)


# --- SEUL AJOUT par rapport au fichier original : few-shot sélectif ---
# Le SEUL cas prouvé aujourd'hui (2 formulaires différents, plusieurs lancements) où une simple
# instruction ne suffit pas : les options préfixées d'une lettre ("A.   ...", "C.   ..."), que
# l'agent a tendance à recopier sans le préfixe malgré la consigne "texte EXACT". On n'ajoute cet
# exemple QUE si les vraies options de la question en contiennent un — pas pour toute question
# choix_unique/choix_multiple, pour ne payer ce coût en tokens que quand c'est vraiment utile.
EXEMPLE_FEW_SHOT_PREFIXE_LETTRE = (
    "Exemple : Question : Quelle est la capitale de la France ? Choix possibles : "
    "A.   Marseille. B.   Paris. C.   Lyon.\n"
    "Réponse : B.   Paris.\n"
    "Maintenant réponds à la question suivante de la même manière, en gardant bien le préfixe "
    "de lettre EXACT s'il y en a un.\n"
)


def question_a_des_options_prefixees_dune_lettre(question: dict) -> bool:
    options = question.get("options") or []
    return any(re.match(r"^[A-Za-z][.\)]\s*", option["texte"]) for option in options)


def construire_prompt(question:dict )-> str:
    # On part du texte de base de la question.
    texte = question["texte_pour_ia"] or ""

    # Si la question a de l'OCR (image), on ajoute le texte lu sur l'image.
    if question["ocr"] is not None:
        texte = texte + " Texte lu sur l'image : " + question["ocr"]["texte_extrait"]

    # Une grille à cases à cocher accepte plusieurs colonnes cochées par ligne, contrairement
    # à une grille à choix unique — le préciser explicitement, sinon le modèle n'en choisit
    # qu'une par ligne comme pour une grille simple. Le champ grille est séparé de options,
    # donc ce cas doit être vérifié avant/à côté du if question.get("options") ci-dessous.
    if question["type_question"] == "grille_choix_multiple" and question.get("grille"):
        textes_lignes = [ligne["texte"] for ligne in question["grille"]["lignes"]]
        textes_colonnes = [colonne["texte"] for colonne in question["grille"]["colonnes"]]
        texte = (
            texte
            + " Pour CHAQUE ligne (" + ", ".join(textes_lignes) + "), tu peux cocher UNE OU "
            "PLUSIEURS colonnes à la fois parmi : " + ", ".join(textes_colonnes) + ". "
            "Réponds ligne par ligne, au format \"ligne: colonne1, colonne2\", en séparant "
            "les lignes par un point-virgule, et en listant pour chaque ligne toutes les "
            "colonnes cochées."
        )
    # Une grille à choix unique a besoin de la même consigne explicite quand elle a plusieurs
    # lignes : sans ça, l'agent répond parfois avec une seule valeur pour toute la grille au
    # lieu d'une réponse par ligne (vérifié en réel sur une grille à 4 lignes).
    elif question["type_question"] == "grille_choix_unique" and question.get("grille"):
        textes_lignes = [ligne["texte"] for ligne in question["grille"]["lignes"]]
        textes_colonnes = [colonne["texte"] for colonne in question["grille"]["colonnes"]]
        texte = (
            texte
            + " Pour CHAQUE ligne (" + ", ".join(textes_lignes) + "), choisis UNE SEULE colonne "
            "parmi : " + ", ".join(textes_colonnes) + ". Réponds ligne par ligne, au format "
            "\"ligne: colonne\", en séparant les lignes par un point-virgule — n'en oublie aucune."
        )

    # Sans format imposé, le modèle improvise (vérifié en réel : deux questions "date" du même
    # formulaire renvoyées dans deux formats différents, JJ/MM/AAAA et AAAA-MM-JJ) — on impose
    # un format cohérent. Mais Google ne distingue PAS "date complète" de "année seulement" dans
    # ses données internes (vérifié en réel : structure interne identique pour "Course Date"
    # et "Year of Birth") — imposer aveuglément AAAA-MM-JJ partout a fait inventer un faux
    # jour/mois pour "Year of Birth". Seul le texte de la question donne ce signal, donc on
    # laisse le modèle adapter la précision à ce qui est réellement demandé.
    elif question["type_question"] == "date":
        texte = (
            texte
            + " Si la question demande une date complète, réponds au format AAAA-MM-JJ "
            "(ex : 2024-05-01). Si elle ne demande qu'une année (ex : \"Year of Birth\", "
            "\"Année de naissance\"), réponds uniquement avec l'année à 4 chiffres, sans "
            "inventer de mois ni de jour."
        )
    elif question["type_question"] == "heure":
        texte = texte + " Réponds uniquement avec une heure au format HH:MM sur 24h (ex : 14:30)."

    # On ajoute une instruction sur le type de réponse attendu.
    elif question.get("options"):
        textes_options = [option["texte"] for option in question["options"]]

        # Un classement a besoin d'une consigne différente d'un simple choix : il faut
        # TOUS les classer, dans l'ordre, pas en choisir un seul.
        if question["type_question"] == "classement":
            texte = (
                texte
                + " Classe TOUS ces éléments du plus important au moins important, dans l'ordre : "
                + ", ".join(textes_options)
                + ". Réponds avec la liste complète, dans l'ordre, séparée par des virgules, "
                "sans en omettre aucun."
            )
        # Une question à cases à cocher accepte plusieurs réponses à la fois, contrairement
        # à un choix unique : le préciser explicitement, sinon le modèle n'en choisit qu'une.
        elif question["type_question"] == "choix_multiple":
            texte = (
                texte
                + " Cette question accepte PLUSIEURS réponses à la fois, choisis parmi : "
                + ", ".join(textes_options)
                + ". Liste TOUS les choix qui s'appliquent, séparés par des virgules."
            )
        # Une échelle linéaire numérique (ex : "Nombre d'adolescents") commence parfois à 1,
        # sans option "0" — vérifié en réel : l'agent répondait "0" pour une quantité nulle,
        # une valeur qui n'est pas une option valide de cette échelle précise. La réponse doit
        # TOUJOURS être une des options réelles (pour pouvoir la relier à un option_id plus
        # tard) — donc pas de mot inventé type "Aucun(e)" non plus, juste choisir la valeur la
        # plus basse disponible si la vraie quantité est zéro.
        elif question["type_question"] == "echelle_lineaire":
            texte = (
                texte
                + " Choix possibles : " + ", ".join(textes_options) + ". Réponds "
                "OBLIGATOIREMENT avec l'une de ces valeurs exactes, jamais un autre mot ou "
                "nombre. Si la vraie réponse est zéro/aucun(e) et que \"0\" ne fait pas partie "
                "des choix, réponds avec la valeur la plus basse de la liste (ex : \"1\")."
            )
        else:
            texte = texte + " Choix possibles : " + ", ".join(textes_options) + "."

        # Certaines options font elles-mêmes référence à la case "Other"/"Autre" dans leur
        # propre texte (ex : "Yes, please specify... in the Other box below.") — vérifié en
        # réel sur un vrai formulaire, deux fois. Demander au modèle de repérer ça lui-même de
        # façon abstraite ("si une option quelconque mentionne Other...") s'est révélé peu
        # fiable (testé 3 fois, échec 2 fois sur 3) — on détecte donc directement dans le code,
        # à partir des VRAIES options de cette question précise, et on donne une instruction
        # concrète nommant l'option exacte, plus facile à suivre qu'une règle générale.
        option_renvoie_vers_other = next(
            (option["texte"] for option in question["options"] if "other box" in option["texte"].lower()),
            None,
        )
        if option_renvoie_vers_other:
            texte = (
                texte
                + " ATTENTION : si tu choisis l'option \"" + option_renvoie_vers_other + "\", tu DOIS "
                "AUSSI ajouter 'Other' à ta réponse et remplir precision_autre avec une précision "
                "concrète — cette option te le demande explicitement. Si tu ne choisis PAS cette "
                "option précise, n'ajoute rien à propos de 'Other'."
            )

        # AJOUT few-shot sélectif (absent du fichier original) : uniquement si les vraies
        # options de CETTE question contiennent un préfixe de lettre — pas pour toutes les
        # questions à choix, pour ne payer ce coût en tokens que là où c'est prouvé utile.
        if question_a_des_options_prefixees_dune_lettre(question):
            texte = EXEMPLE_FEW_SHOT_PREFIXE_LETTRE + texte

    # Certaines questions sont des fragments qui ne veulent rien dire seuls (ex : "Lesquels ?",
    # "If yes, please explain") sans savoir de quoi parlait la question juste avant dans le
    # formulaire — vérifié en réel ("Lesquels ?" après "Êtes-vous à l'aise avec les outils
    # informatiques ?" répondu à tort avec des langues au lieu d'outils ; "If yes, please
    # explain" après une question médicale répondue "No" a halluciné un texte de candidature à
    # un stage, sans AUCUN rapport). On ajoute UNIQUEMENT le texte court de la question
    # précédente (pas tout l'historique du formulaire) pour rester économe en tokens et garder
    # chaque appel indépendant, donc toujours parallélisable.
    # ATTENTION : donner ce contexte a lui-même causé un vrai bug plusieurs fois quand la
    # question actuelle est une simple ÉTIQUETTE de champ, pas un vrai fragment (ex : "Team
    # size" après "major challenges", "Course" après "Year of Completion", "School" après "team
    # name" — trois cas testés en réel, tous dérivés vers le sujet de la question précédente,
    # même avec une consigne explicite de l'ignorer si non nécessaire). Signal fiable trouvé en
    # comparant les cas réels : les questions qui ont VRAIMENT besoin de ce contexte sont soit
    # de vraies questions avec un "?" ("Lesquels ?", "Quel type d'événements était-ce ?"), soit
    # des formulations conditionnelles ("If yes/so", "Si oui") qui font explicitement référence
    # à la réponse précédente — les étiquettes de champ (ni "?", ni conditionnelle) n'en ont
    # jamais besoin. On restreint donc l'ajout du contexte à ces deux cas précis, plutôt que de
    # compter sur le modèle pour juger lui-même de la pertinence.
    texte_question_actuelle = (question.get("texte_pour_ia") or "").lower()
    est_un_fragment = "?" in texte_question_actuelle or any(
        marqueur in texte_question_actuelle
        for marqueur in ("if yes", "if so", "if applicable", "si oui", "le cas échéant")
    )
    if question.get("question_precedente") and est_un_fragment:
        texte = (
            texte
            + " (Pour référence UNIQUEMENT si la question ci-dessus est un fragment ambigu "
            "(ex : \"Lesquels ?\", \"Pourquoi ?\") qui a besoin de savoir de quoi parlait la "
            "question précédente du formulaire pour être compris : \"" + question["question_precedente"]
            + "\". Si la question ci-dessus a un sens complet toute seule, ignore totalement "
            "cette référence et n'y fais aucune allusion.)"
        )

    return texte



# L'agent doit répondre avec le texte EXACT d'une option (voir system_prompt), mais un LLM ne
# suit jamais une consigne à 100% (ex: "Oui." au lieu de "Oui") — un filet de sécurité côté code
# est plus fiable qu'une instruction de prompt seule, utile si on veut un jour retrouver
# automatiquement l'option_id correspondant à la réponse. Uniquement pour choix_unique/
# choix_multiple : classement et grilles produisent déjà des chaînes composées ("ligne: colonne")
# qui ne correspondent pas à une seule option, pas concernées ici.
def normaliser_choix(valeur: str, question: dict) -> str:
    if question["type_question"] not in ("choix_unique", "choix_multiple"):
        return valeur
    if not question.get("options"):
        return valeur

    textes_options = [option["texte"] for option in question["options"]]

    parties_normalisees = []
    for partie in valeur.split(","):
        partie_nettoyee = partie.strip().rstrip(".!?").strip().lower()
        correspondance = next(
            (texte for texte in textes_options if texte.lower() == partie_nettoyee),
            None,
        )
        if not correspondance:
            correspondance = next(
                (
                    texte for texte in textes_options
                    if re.sub(r"^[A-Za-z][.\)]\s*", "", texte).strip().rstrip(".!?").strip().lower()
                    == partie_nettoyee
                ),
                None,
            )
        parties_normalisees.append(correspondance if correspondance else partie.strip())

    return ", ".join(parties_normalisees)


def detecter_langue_formulaire(questions: list) -> str | None:
    texte_combine = " ".join(
        question["texte_pour_ia"] for question in questions if question.get("texte_pour_ia")
    )
    try:
        return detect(texte_combine)
    except LangDetectException:
        return None


def proposer_reponse(question:dict)-> dict:
    construction_prompt = construire_prompt(question)

    tentatives_max = 3
    for tentative in range(1, tentatives_max + 1):
        try:
            resp = agent.invoke({"messages": [{"role": "user", "content": construction_prompt}]})
            reponse = resp["structured_response"]

            valeur_normalisee = normaliser_choix(reponse.valeur, question)

            valeur_finale = valeur_normalisee
            if reponse.precision_autre:
                valeur_finale = f"{valeur_normalisee} : {reponse.precision_autre}"

            if (
                question["type_question"] == "texte_libre"
                and question.get("langue_formulaire")
                and len(valeur_finale) >= 10
                and tentative < tentatives_max
            ):
                try:
                    if detect(valeur_finale) != question["langue_formulaire"]:
                        construction_prompt = (
                            construction_prompt
                            + f" (Rappel STRICT : réponds uniquement en langue "
                            f"'{question['langue_formulaire']}'.)"
                        )
                        continue
                except LangDetectException:
                    pass

            return {
                "question_id": question["question_id"],
                "question": question["texte_pour_ia"],
                "reponse": valeur_finale,
            }
        except Exception as erreur:
            if "RESOURCE_EXHAUSTED" in str(erreur) and tentative < tentatives_max:
                time.sleep(30)
                continue
            return {
                "question_id": question["question_id"],
                "question": question["texte_pour_ia"],
                "reponse": None,
                "erreur": str(erreur),
            }



def generer_reponses_formulaire(formulaire: dict) -> dict:
    questions_valides = [
    question for question in formulaire["questions"]
    if question["statut_extraction"] == "prete"
]

    langue_formulaire = detecter_langue_formulaire(questions_valides)
    for index, question in enumerate(questions_valides):
        question["question_precedente"] = (
            questions_valides[index - 1]["texte_pour_ia"] if index > 0 else None
        )
        question["langue_formulaire"] = langue_formulaire

    with ThreadPoolExecutor(max_workers=3) as executeur:
     reponses = list(executeur.map(proposer_reponse, questions_valides))


     return {"formulaire_url": formulaire["source"]["url"], "reponses": reponses}



def extraire_formulaire_depuis_url(url: str) -> dict:
    if "google.com" in url:
        return extraire_formulaire_google_public(url)
    elif "microsoft" in url or "office.com" in url:
        return extraire_formulaire_microsoft(url)
    else:
        raise ValueError(f"Impossible de déterminer le fournisseur du formulaire depuis cette URL : {url}")


if __name__ == "__main__":
    import sys as _sys
    url = _sys.argv[1] if len(_sys.argv) > 1 else "https://docs.google.com/forms/d/e/1FAIpQLSeHTE1i2-1C9LCLaTYAy7mzvpPT42l1Lvu0H279geXqlTD87Q/viewform?usp=header"
    formulaire = extraire_formulaire_depuis_url(url)
    resultat = generer_reponses_formulaire(formulaire)
    print(json.dumps(resultat, indent=2, ensure_ascii=False))
