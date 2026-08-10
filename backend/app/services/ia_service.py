# Ce fichier contient la logique IA : un agent LangChain qui reçoit une question (au format
# JSON produit par scripts_extraction/) et propose une réponse.
import sys
from pathlib import Path
import json
import os
import re
import time

# Ajoute le dossier scripts_extraction/ à la liste des endroits où Python cherche des imports.
# Doit venir AVANT tout import venant de ce dossier (google_forms_public, microsoft_forms_scraper...).
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

# langdetect n'est pas déterministe par défaut (probabiliste) — fixer une graine rend ses
# résultats reproductibles d'un lancement à l'autre.
DetectorFactory.seed = 0

# Même chemin que backend/app/database.py : backend/.env, peu importe le dossier courant
# depuis lequel ce fichier est lancé (important pour pouvoir le tester tout seul).
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)


class ReponseAgent(BaseModel):
    valeur: str
    # Rempli uniquement quand valeur est l'option "Other"/"Autre" (texte libre) : sans ce champ,
    # l'agent renverrait juste le mot "Other" tout seul, sans dire ce qu'il veut dire concrètement.
    precision_autre: str | None = None

google_api_key = os.getenv("GEMINI_API_KEY")
modele = ChatGoogleGenerativeAI(
   model="gemini-3.1-flash-lite",
   temperature=0.2,
   google_api_key=google_api_key,
)

# Extrait dans une constante (plutôt que gardé inline dans create_agent) pour pouvoir être
# réimporté tel quel par les scripts de comparaison de modèles (ex: test_documents/), sans
# dupliquer ce texte à chaque fois qu'on veut tester un autre LLM avec le même prompt.
SYSTEM_PROMPT = (
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

agent = create_agent(model=modele, tools=[], system_prompt=SYSTEM_PROMPT, response_format=ReponseAgent)


def construire_prompt(question:dict )-> str:
    # On part du texte de base de la question.
    texte = question["texte_pour_ia"] or ""

    # Contrairement à question_precedente (une seule question, injectée seulement pour les
    # fragments/conditionnelles), le titre du formulaire est ajouté à TOUTES les questions —
    # c'est le seul indice du SUJET GÉNÉRAL du formulaire que le modèle reçoit, puisque chaque
    # question est envoyée dans un appel indépendant (voir generer_reponses_formulaire) et ne
    # voit jamais le reste du formulaire. Bug réel corrigé par ça : "Commentaires libres" en fin
    # de formulaire répondait avec un texte de candidature à un emploi, faute de savoir que le
    # formulaire était en réalité une enquête de satisfaction sur une formation.
    if question.get("titre_formulaire"):
        texte = "(Ce formulaire s'intitule : \"" + question["titre_formulaire"] + "\".) " + texte

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



# Réduit un texte à sa forme "comparable" : retire un éventuel préfixe de lettre ("A.   ",
# "C.   "...), écrase toute suite d'espaces en un seul, retire la ponctuation finale, minuscule.
# Les vraies options Google Forms contiennent parfois plusieurs espaces après la lettre
# ("D.   It helps prevent accidents.." — présent tel quel dans les données extraites, ce n'est
# pas une erreur d'extraction) que le modèle, en générant du texte librement, ne reproduit
# jamais exactement (il renvoie "D. It helps prevent accidents." avec un seul espace). Appliquer
# cette normalisation aux DEUX côtés de la comparaison absorbe ça, en plus du cas où le préfixe
# est totalement omis par le modèle.
def normaliser_texte_comparaison(texte: str) -> str:
    texte = re.sub(r"^[A-Za-z][.\)]\s*", "", texte)
    texte = re.sub(r"\s+", " ", texte)
    return texte.strip().rstrip(".!?").strip().lower()


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
        partie_nettoyee = normaliser_texte_comparaison(partie.strip())
        correspondance = next(
            (
                texte for texte in textes_options
                if normaliser_texte_comparaison(texte) == partie_nettoyee
            ),
            None,
        )
        parties_normalisees.append(correspondance if correspondance else partie.strip())

    return ", ".join(parties_normalisees)


# Détecte la langue dominante du formulaire à partir de TOUTES les questions, pas d'une seule —
# une seule question est parfois trop courte ou ambiguë (ex : "Position", identique en français
# et en anglais) pour une détection fiable. On combine tout le texte pour donner à langdetect
# assez de matière.
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

    # Si UNE question fait planter l'agent (vrai bug, panne de l'API...), on ne veut pas
    # perdre les réponses des autres questions du formulaire — on isole l'erreur ici et on
    # renvoie un résultat marqué en erreur pour cette question précise, sans faire planter
    # tout le ThreadPoolExecutor de generer_reponses_formulaire.
    tentatives_max = 3
    for tentative in range(1, tentatives_max + 1):
        try:
            resp = agent.invoke({"messages": [{"role": "user", "content": construction_prompt}]})
            reponse = resp["structured_response"]

            valeur_normalisee = normaliser_choix(reponse.valeur, question)

            # Si l'agent a choisi "Other"/"Autre", on complète avec la précision donnée plutôt
            # que de renvoyer juste ce mot seul, qui ne veut rien dire pour un humain qui valide.
            valeur_finale = valeur_normalisee
            if reponse.precision_autre:
                valeur_finale = f"{valeur_normalisee} : {reponse.precision_autre}"

            # Le system_prompt demande déjà de répondre dans la langue de la question, mais un
            # LLM ne suit pas cette consigne à 100% (constaté en réel plusieurs fois) — filet de
            # sécurité côté code, comme pour normaliser_choix. Uniquement pour du texte libre
            # assez long (< 10 caractères = détection de langue peu fiable, ex: "Oui", "5").
            # Les choix fixes ne sont pas concernés : leur texte vient déjà du formulaire lui-même.
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
            # Le quota gratuit Gemini (15 requêtes/min) peut être dépassé temporairement même
            # avec max_workers limité, sur un formulaire avec beaucoup de questions — dans ce
            # cas précis (et seulement celui-là), on réessaie après une pause au lieu d'abandonner
            # tout de suite. Une vraie erreur (bug, question mal formée...) remonte immédiatement,
            # sans attendre inutilement 3 fois.
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

    # On calcule la langue du formulaire une seule fois (pas question par question, voir
    # detecter_langue_formulaire) et on attache à chaque question le texte de celle juste avant
    # elle (voir construire_prompt) — tout ça avant de lancer les appels en parallèle.
    langue_formulaire = detecter_langue_formulaire(questions_valides)
    for index, question in enumerate(questions_valides):
        question["question_precedente"] = (
            questions_valides[index - 1]["texte_pour_ia"] if index > 0 else None
        )
        question["langue_formulaire"] = langue_formulaire
        question["titre_formulaire"] = formulaire.get("titre")

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


# Ce bloc ne s'exécute que si on lance CE fichier directement (python ia_service.py),
# pas quand on l'importe depuis ailleurs (un autre script, une future route API...).
if __name__ == "__main__":
    formulaire = extraire_formulaire_depuis_url("https://docs.google.com/forms/d/e/1FAIpQLSeHTE1i2-1C9LCLaTYAy7mzvpPT42l1Lvu0H279geXqlTD87Q/viewform?usp=header")

    resultat = generer_reponses_formulaire(formulaire)
    print(json.dumps(resultat, indent=2, ensure_ascii=False))





