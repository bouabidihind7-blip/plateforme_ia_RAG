"""
Agent de standardisation : prend un fichier brut (texte non structuré, dans n'importe quel
style d'écriture) et le transforme en notre format standard — des paires Q : / R :, validées
empiriquement aujourd'hui (16/16 sur evaluer_reponses.py). Le résultat est un simple .txt,
prêt à être ingéré TEL QUEL par ingest_txt.py — aucun changement de pipeline nécessaire, on
change seulement le contenu des documents, pas le code qui les traite.

Usage : python rag/agent_standardisation.py <fichier_brut_entree> <fichier_txt_sortie>
"""
import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import sys
from pathlib import Path
from dotenv import load_dotenv

import pandas as pd
from langchain_community.document_loaders import PDFPlumberLoader, Docx2txtLoader
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed

# Même chemin que rag_chain.py/ia_service.py : backend/.env, peu importe le dossier courant.
env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(env_path)

# Chaque règle ci-dessous correspond à un vrai bug qu'on a trouvé et corrigé aujourd'hui en
# testant empiriquement — pas des principes abstraits (voir evaluer_reponses.py) :
# - Format Q:/R: + ligne vide : pour que RecursiveCharacterTextSplitter coupe pile entre deux
#   idées (séparateur \n\n prioritaire), jamais en plein milieu.
# - Pas de pronom ambigu : sinon un chunk retrouvé seul (sans son contexte d'origine) ne veut
#   plus rien dire pour le LLM qui le lit.
# - Longueur libre mais "brève", avec un REPÈRE (~250-300 caractères pour R), pas une limite
#   STRICTE : testé en réel qu'une limite dure en caractères (300, comptant Q+R) faisait
#   sacrifier des détails secondaires pour rentrer dedans (perte d'info silencieuse) — laisser
#   l'IA juger la longueur "naturelle" d'un fait bref a donné une bien meilleure fidélité, sans
#   casser le chunking (0 coupure Q/R sur le test, tailles naturellement entre 170 et 250
#   caractères). Repère chiffré réintroduit plus tard : sans lui, l'agent a quand même produit
#   un R de 410 caractères sur un cas dense (procédure tablette en 3 étapes), assez long pour
#   déclencher le filet de sécurité de ingest_txt.py (voir _decouper_bloc_trop_long) — le
#   repère aide l'agent à repérer LUI-MÊME ce genre de cas dense, sans jamais sacrifier
#   d'information pour rentrer dedans (contrairement à l'ancienne limite stricte).
# - Phrases naturelles, jamais "clé: valeur" : ce format brut classait la bonne réponse 5e
#   au lieu de 1re dans nos tests d'embedding (cas Nadia Chraibi).
# - Reformulations (query_variations) : pour combler l'écart de vocabulaire entre la question
#   posée et le texte source (cas "département communication" vs "Marketing").
# - Catégorie par bloc (RH/IT/Finance/Production/Commercial/Legal/Général) : RE-AJOUTÉE.
#   Le filtrage par catégorie devinée par GEMINI (testé en réel) était moins bon que la
#   fusion simple — mais on est ensuite passés à une classification par EMBEDDING LOCAL
#   (retriever.py), qui elle a gagné sur les deux axes (31/34 vs 31/34, mais ~2x plus rapide).
#   Cette méthode a besoin que l'ingestion (ingest_txt.py) range chaque fait dans la bonne
#   collection Chroma pour que la recherche ciblée trouve quelque chose — sans cette étiquette,
#   tout retombe sur le filet de sécurité "qa_general" (constaté en réel : nouveaux fichiers
#   sans étiquette après un retrait temporaire de cette règle).
SYSTEM_PROMPT = """Tu es un agent de standardisation de documents internes d'entreprise.

Ta tâche : transformer le texte source fourni en une série de paires Question/Réponse, selon des règles STRICTES.

RÈGLES OBLIGATOIRES :

1. Format : chaque entrée doit suivre exactement ce format, avec UNE ligne vide entre chaque entrée :
Catégorie : [une SEULE de ces 7 catégories, copiée EXACTEMENT : RH, IT, Finance, Production, Commercial, Legal, Général]
Q : [question]
R : [réponse]

Choix de la catégorie — ne jamais en inventer d'autre que ces 7 :
- RH : congés, télétravail, recrutement, formation, paie, avantages, intégration.
- IT : sécurité informatique, mots de passe, VPN, Wi-Fi, logiciels, support technique.
- Finance : remboursements, notes de frais, budgets, facturation.
- Production : machines, qualité, incidents techniques, procédures d'atelier, environnement/recyclage lié à la production.
- Commercial : clients, commandes, fournisseurs, délais, communication externe.
- Legal : contrats, conformité réglementaire, propriété intellectuelle, litiges, mentions légales.
- Général : tout ce qui ne correspond clairement à aucune des 6 catégories ci-dessus (organigramme, départements, politique générale, startups incubées).

2. Autonomie : chaque réponse doit être compréhensible seule, sans contexte extérieur. N'utilise JAMAIS de pronom ambigu ("il", "elle", "cela", "ce dernier") — reformule toujours le nom précis (personne, département, machine, politique...).

3. Longueur : sois BREF — dis l'essentiel en aussi peu de mots que possible, SANS AJOUTER ni SUPPRIMER la moindre information du texte source (même un détail secondaire). N'impose aucune limite fixe stricte : si une information source est dense (plusieurs étapes, plusieurs conditions), découpe-la en PLUSIEURS paires Q/R distinctes plutôt que d'écrire un bloc trop long — vise une réponse (R) d'environ 250 à 300 caractères ; au-delà, c'est presque toujours le signe qu'elle mélange plusieurs informations qui devraient être des questions séparées (ex : une procédure en plusieurs étapes doit devenir une paire Q/R par étape, pas une seule réponse qui les liste toutes). Si une information source est déjà très courte, développe légèrement la réponse pour qu'elle reste compréhensible seule, sans pour autant inventer de détails absents du texte source.

4. Langage naturel : écris toujours en phrases complètes et naturelles. N'utilise JAMAIS de notation "clé: valeur" ou de liste brute.

5. Fidélité : n'invente RIEN. N'utilise que les informations présentes dans le texte source fourni. Si un chiffre, un nom ou un fait est présent, garde-le précisément (ne l'arrondis pas, ne le déforme pas). Si une information n'est pas dans le texte source, ne l'invente pas. Nom de l'entreprise : utilise TOUJOURS exactement le nom d'entreprise ou d'organisation présent dans le texte source, quel qu'il soit — ne le remplace JAMAIS par un autre nom d'entreprise, même s'il t'est familier. Si le texte source utilise un espace réservé générique non rempli (ex : "[ORGANIZATION]", "[NOM DE L'ENTREPRISE]"), garde une formulation neutre ("l'entreprise", "l'organisation") plutôt que d'inventer un nom d'entreprise précis.

5bis. Exhaustivité : traite CHAQUE élément distinct du texte source (chaque puce, chaque règle, chaque rôle mentionné), même si le texte source est long ou contient de nombreuses listes similaires. N'en résume, n'en regroupe et n'en omets AUCUN, même si cela produit un grand nombre de paires Q/R — un texte source avec 20 puces doit donner environ 20 paires Q/R, pas une seule paire qui résume les 20.

6. Reformulations : pour les faits importants ou susceptibles d'être demandés de plusieurs façons différentes, ajoute 1 à 2 paires Q/R supplémentaires avec une formulation différente de la question, mais la même information en réponse.

Ne produis RIEN d'autre que ces paires Q/R — pas d'introduction, pas de titre, pas de conclusion, pas de commentaire.
"""


# Extrait le texte brut d'un fichier, quel que soit son format — l'agent (plus bas) ne
# reçoit ensuite QUE du texte, peu importe si la source était un PDF, un Excel ou du texte
# brut. Réutilise les mêmes loaders déjà validés dans ingest_pdf.py/ingest_tabulaire.py —
# pas besoin de réinventer l'extraction, juste de la brancher devant l'agent.
def extraire_texte(chemin_entree: str) -> str:
    extension = Path(chemin_entree).suffix.lower()

    if extension == ".pdf":
        pages = PDFPlumberLoader(chemin_entree).load()
        return "\n\n".join(page.page_content for page in pages)

    if extension == ".xlsx":
        feuilles = pd.read_excel(chemin_entree, sheet_name=None)
        morceaux = []
        for nom_feuille, tableau in feuilles.items():
            morceaux.append(f"Feuille : {nom_feuille}\n{tableau.to_string(index=False)}")
        return "\n\n".join(morceaux)

    if extension == ".csv":
        tableau = pd.read_csv(chemin_entree)
        return tableau.to_string(index=False)

    if extension == ".docx":
        return Docx2txtLoader(chemin_entree).load()[0].page_content

    # .txt, .json, .md et tout le reste : déjà du texte lisible tel quel (JSON et Markdown
    # sont des formats texte — pas besoin d'extraction, l'agent lit directement leur syntaxe).
    return Path(chemin_entree).read_text(encoding="utf-8")


# Filet de sécurité GÉNÉRAL, pas spécifique à un document — s'applique à N'IMPORTE QUEL appel
# de standardisation, sur n'importe quel document. Bug réel constaté : un document assez
# volumineux (38 lots) épuise le quota gratuit de Gemini (15 requêtes/minute) en cours de
# route, et l'erreur faisait planter tout le script, perdant la progression déjà faite (17
# lots sur 38 traités en vain). Réessaie automatiquement après une pause si l'erreur est bien
# un quota dépassé (429 RESOURCE_EXHAUSTED) — ne réessaie PAS sur d'autres erreurs (mauvaise
# clé API, etc.), qui elles doivent remonter immédiatement plutôt que d'être masquées.
def _est_erreur_quota(exception: Exception) -> bool:
    return isinstance(exception, ChatGoogleGenerativeAIError) and "RESOURCE_EXHAUSTED" in str(exception)


@retry(
    retry=retry_if_exception(_est_erreur_quota),
    wait=wait_fixed(60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _invoquer_avec_reessai(chaine, texte_source: str) -> str:
    return chaine.invoke({"texte_source": texte_source})


def standardiser_fichier(chemin_entree: str, chemin_sortie: str) -> None:
    # Gemini a besoin d'un vrai message "human" en plus du "system" (sinon erreur "contents
    # are required") — le texte source part donc dans le message human, pas dans le system.
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Texte source à transformer :\n\n{texte_source}"),
    ])
    # Clé API dédiée, séparée de GEMINI_API_KEY (utilisée par ia_service.py pour les vraies
    # réponses aux utilisateurs) — projet Google Cloud distinct, donc quota distinct. Sinon,
    # un traitement de standardisation en parallèle (plusieurs appels à la fois) pourrait
    # consommer le même quota que les réponses RAG en direct et les ralentir.
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0.1,
        google_api_key=os.getenv("GEMINI_API_KEY_STANDARDISATION"),
    )
    chaine = prompt | llm | StrOutputParser()

    texte_source = extraire_texte(chemin_entree)
    print(f"Standardisation de {chemin_entree} ({len(texte_source)} caracteres source)...")

    resultat = _invoquer_avec_reessai(chaine, texte_source)

    Path(chemin_sortie).write_text(resultat, encoding="utf-8")
    print(f"  -> {chemin_sortie} ({len(resultat)} caracteres produits)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage : python rag/agent_standardisation.py <fichier_brut_entree> <fichier_txt_sortie>")
        sys.exit(1)
    standardiser_fichier(sys.argv[1], sys.argv[2])
