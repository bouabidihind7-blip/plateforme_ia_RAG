"""
Construit un retriever fusionné sur nos collections Chroma :
  - tabulaire_excel_csv : lignes Excel/CSV (1 ligne = 1 doc, pas de chunking)
  - politique_pdf       : chunks du PDF de politique (RecursiveCharacterTextSplitter à l'ingestion)
  - qa_<categorie>      : les 7 collections par sujet (qa_rh/qa_it/qa_finance/qa_production/
    qa_commercial/qa_legal/qa_general).

La catégorie d'une question est devinée par EMBEDDING LOCAL, pas par Gemini : on compare le
vecteur de la question à 7 phrases de référence (une par catégorie), et on prend la plus
proche par similarité cosinus — aucun appel réseau, juste du calcul local, déjà fait de toute
façon pour chercher dans Chroma.

Comparé empiriquement en réel sur 34 questions à 2 autres approches :
  A. Filtrage par catégorie devinée par Gemini : 28/34, 369.1s
  B. Recherche fusionnée dans les 7 collections (pas de catégorie) : 31/34, 329.4s
  C. Filtrage par catégorie devinée par embedding local (celle-ci) : 31/34, 169.6s
C égale la précision de B tout en étant ~2x plus rapide, sans coût Gemini supplémentaire —
la meilleure des 3 approches testées, d'où son adoption ici.

Modèle d'embedding : comparé empiriquement à 3 autres modèles locaux (même méthode C
ci-dessus, mêmes 34 questions) :
  multilingual-e5-large-instruct (avant)   : 31/34, ingestion 597 chunks ~150s+, 169.6s questions
  multilingual-e5-small (actuel)           : 31/34, ingestion 16.6s,             125.2s questions
  BAAI/bge-m3                              : 31/34, ingestion 152.7s,            132.5s questions
  Qwen/Qwen3-Embedding-0.6B                : 30/34, ingestion 1013.8s,           175.2s questions
e5-small égale la précision de e5-large-instruct (~4x plus petit, ~120M paramètres) tout en
étant nettement plus rapide à l'ingestion (10x) — le meilleur compromis trouvé, d'où le passage
de "large-instruct" à "small" ici.

Classification par embedding : PHRASES_REFERENCE utilise PLUSIEURS phrases par catégorie (pas
une seule) — voir le commentaire sur PHRASES_REFERENCE plus bas. Testé sur les 229 vraies
questions du corpus : 95.6% (1 phrase/catégorie) -> 100% (plusieurs phrases/catégorie).
k_qa (nombre de chunks considérés par catégorie avant le tri global) : passé de 3 à 6. Testé
en réel que la bonne réponse peut légitimement classer 5e ou 6e (pas 1re-3e) dans sa propre
catégorie quand plusieurs chunks du MÊME document se ressemblent beaucoup en surface (ex :
plusieurs questions "Citrix..." ou "point de restauration..." qui partagent énormément de
vocabulaire) — un k_qa=3 les excluait avant même que le LLM les voie. k_total (nombre final
gardé tous documents confondus) monté à 6 en cohérence, sinon k_qa=6 ne change rien une fois
retronqué à l'ancien k_total=5. Vérifié sur les 34+12 questions de test : 31/34 -> 32/34,
9/12 -> 12/12, aucune régression observée.

Fusion multi-collections : passée d'un tri global par SCORE BRUT à un tri par RANG (Reciprocal
Rank Fusion, K_RRF=60) — bug réel constaté à l'ajout des fichiers tabulaires (Excel/CSV) : le
score cosinus d'une phrase tabulaire synthétique ("Cette entrée a les caractéristiques
suivantes : X vaut Y") est structurellement plus bas que celui d'une vraie paire Q/R en
langage naturel, même quand le contenu tabulaire est la bonne réponse — il se faisait évincer
du tri global par des candidats d'autres collections, HORS SUJET mais mieux scorés dans
l'absolu, juste à cause du style de phrase. RRF ignore la valeur absolue du score, ne compare
que le rang au sein de la collection d'origine.
Sélection des catégories qa_* interrogées : passée d'un filtrage par MARGE_AMBIGUITE (toute
catégorie à moins de 0.05 de la gagnante) à un top N_CATEGORIES=3 fixe — la marge ne filtrait
quasiment plus rien à cette taille de corpus (~6.9 catégories sur 7 interrogées en moyenne),
noyant les candidats pertinents (tabulaire compris) sous des dizaines de candidats hors sujet
avant même le tri RRF. Comparé en réel sur 42 questions (corpus complet + fichiers tabulaires) :
marge 0.05 (ancien) 30/42, top 3 catégories (actuel) 34/42, top 1 + bonus fixe 28/42 (pire —
un bonus systématique pour la gagnante ET pour tabulaire_excel_csv leur vole des places même
sur des questions sans rapport avec elles).
"""
import os
# Le modèle est déjà en cache local (~450 Mo, déjà téléchargé) — sans ça, HuggingFaceEmbeddings
# tente quand même une requête réseau vers le Hub à chaque lancement (juste pour vérifier des
# métadonnées), qui peut traîner ou bloquer si la connexion est lente. Inutile ici.
os.environ["HF_HUB_OFFLINE"] = "1"

from pathlib import Path

import numpy as np
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.documents import Document

# Chemin absolu ancré sur ce fichier (pas relatif au dossier courant) : sinon, lancer ce
# script — ou ia_service.py qui l'appelle — depuis un dossier différent de la racine du
# projet crée silencieusement un AUTRE chroma_store vide au lieu de se connecter au vrai
# (bug réel constaté : 0 résultat retourné, sans aucune erreur).
CHROMA_DIR = str(Path(__file__).resolve().parent.parent / "chroma_store")
EMBED_MODEL = "intfloat/multilingual-e5-small"

# PLUSIEURS phrases descriptives par catégorie (pas une seule) — chaque catégorie a un angle
# "sujet technique" ET un angle "administratif/relationnel" séparé, sinon une question qui
# emprunte le vocabulaire d'un AUTRE domaine (ex : une question RH sur une formation SolidWorks,
# qui parle donc "SolidWorks", pas "RH") se fait voler par ce domaine-là.
# Testé empiriquement sur les 229 vraies questions du corpus (categories non-general) :
#   1 seule phrase/categorie : 219/229 (95.6%)
#   plusieurs phrases/categorie, meilleur score par categorie (max) : 229/229 (100%)
# Vraies phrases naturelles, pas des listes de mots-clés collés ("RH : congés, paie...") —
# testé empiriquement (cas Nadia Chraibi) que l'embedding capte mieux le sens d'une phrase
# naturelle qu'une notation télégraphique. Éviter les mots trop génériques, partagés entre
# plusieurs catégories ("formation" pour RH, "problème"/"outil" pour IT) — un mot générique
# dans UNE phrase peut faire gagner sa catégorie sur des questions qui n'ont rien à voir,
# juste parce que ce mot apparaît aussi ailleurs (constaté en réel à 2 reprises).
PHRASES_REFERENCE = {
    "rh": [
        "Cette question concerne la gestion administrative du personnel, comme les congés, le télétravail, le recrutement, la paie ou l'intégration des nouveaux employés.",
        "Cette question concerne l'accueil et l'intégration des nouveaux stagiaires ou employés, comme le matériel fourni, le tuteur assigné ou la présentation générale de l'entreprise.",
        "Cette question concerne la gestion administrative des formations professionnelles, comme leur durée, leur caractère certifiant ou non, ou le public concerné, indépendamment du sujet technique de la formation.",
        "Cette question concerne la gestion administrative des accès et badges des employés ou stagiaires, comme leur activation, leur perte, leur vol ou leur renouvellement.",
    ],
    "it": [
        "Cette question concerne la sécurité informatique et le support technique, comme les mots de passe, le VPN, le Wi-Fi, les logiciels ou le dépannage des appareils professionnels (ordinateurs, tablettes, imprimantes).",
        "Cette question concerne une procédure de dépannage informatique : vérifier la version d'un logiciel, installer une mise à jour logicielle, ou résoudre un problème de connexion à un compte, une application ou un réseau informatique.",
        "Cette question concerne les règles d'utilisation acceptable des équipements et du réseau informatique de l'entreprise, comme les restrictions de contenu, l'utilisation personnelle des appareils ou les activités interdites en ligne.",
    ],
    "finance": [
        "Cette question concerne la gestion financière de l'entreprise, comme les remboursements, les notes de frais, les budgets ou la facturation.",
    ],
    "production": [
        "Cette question concerne l'atelier de fabrication, comme les machines, la qualité, les incidents techniques ou les formations techniques aux outils.",
        "Cette question concerne le traitement d'une non-conformité ou d'une réclamation qualité signalée par un client sur une pièce produite.",
    ],
    "commercial": [
        "Cette question concerne la relation avec les clients et la communication externe, comme les commandes, les fournisseurs, les délais, les réseaux sociaux ou les relations presse.",
        "Cette question concerne un fournisseur de l'entreprise, les matériaux ou produits qu'il livre, ses délais de livraison ou ses conditions contractuelles.",
    ],
    "legal": [
        "Cette question concerne les aspects juridiques de l'entreprise, comme les contrats, la confidentialité, la conformité réglementaire, la propriété intellectuelle ou les litiges.",
    ],
    "general": [
        "Cette question concerne l'organisation générale de l'entreprise, comme l'organigramme, les départements ou les startups incubées.",
    ],
}


def _similarite_cosinus(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def build_retriever(
    k_tabulaire: int = 3,
    k_qa: int = 6,
    k_politique: int = 3,
) -> RunnableLambda:
    # embeddings (le modèle, ~450 Mo) est chargé UNE fois ici, réutilisé à chaque recherche —
    # c'est la partie coûteuse, pas besoin de la refaire à chaque question.
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    # Vecteurs de TOUTES les phrases de référence, calculés UNE fois ici (pas à chaque
    # question) — une LISTE de vecteurs par catégorie, pas un seul.
    vecteurs_reference = {
        categorie: [embeddings.embed_query(phrase) for phrase in phrases]
        for categorie, phrases in PHRASES_REFERENCE.items()
    }
    # Renvoie les N_CATEGORIES catégories les plus proches (pas juste la gagnante) — chercher
    # UNIQUEMENT la gagnante a été testé et perd des vraies réponses (cas réel : question sur
    # une clause de confidentialité, vocabulaire proche de RH — "collaborateur", "départ" —
    # alors que le fait est en réalité dans "Legal", jamais trouvé si on ne cherche que RH).
    # Remplace l'ancienne approche par MARGE_AMBIGUITE (écart de score < seuil) : à mesure que
    # le corpus grossissait, les scores des 7 catégories devenaient trop proches les uns des
    # autres pour qu'une marge fixe filtre quoi que ce soit (~6.9 catégories sur 7 cherchées en
    # moyenne, seuil = 0.05, plus aucun filtrage réel) — noyant les vrais candidats pertinents
    # (tabulaire compris) sous des dizaines de candidats hors sujet dans le tri global.
    # Testé empiriquement en réel (42 questions, corpus complet + nouveaux fichiers tabulaires) :
    #   marge d'ambiguïté 0.05 (ancien)     : 30/42
    #   top 3 catégories les plus proches (ce choix) : 34/42
    #   top 1 + bonus fixe pour la gagnante : 28/42 (pire que l'ancien — un bonus systématique
    #     pour la catégorie gagnante ET pour tabulaire_excel_csv leur vole des places au
    #     détriment de vraies réponses d'autres catégories, même sur des questions sans aucun
    #     rapport avec elles)
    N_CATEGORIES = 3
    def deviner_categories(vecteur_question: list[float]) -> list[str]:
        # Score d'une catégorie = MEILLEURE similarité parmi TOUTES ses phrases de référence
        # (pas une moyenne) — chaque phrase couvre un angle différent du sujet, une question
        # ne matche généralement bien qu'un seul angle à la fois.
        scores = {
            categorie: max(_similarite_cosinus(vecteur_question, v) for v in vecteurs)
            for categorie, vecteurs in vecteurs_reference.items()
        }
        categories_triees = sorted(scores, key=scores.get, reverse=True)
        return categories_triees[:N_CATEGORIES]

    # similarity_search_with_relevance_scores renvoie (Document, score) — score entre 0 et 1,
    # PLUS HAUT = PLUS PERTINENT (contrairement à similarity_search_with_score, qui renvoie
    # une distance où plus bas = plus proche — on préfère cette version pour éviter la confusion).
    def retrieve(query: str, k_total: int = 6) -> list[Document]:
        # Contrairement à embeddings, les connexions Chroma(...) sont recréées à CHAQUE
        # recherche (léger : juste une connexion, pas un rechargement du modèle) — sinon, un
        # ré-import de document (delete_collection() + from_documents() dans les scripts
        # d'ingestion) donne un NOUVEL identifiant interne à la collection, et une connexion
        # gardée depuis le démarrage du serveur pointerait vers l'ancien, déjà supprimé (bug
        # réel constaté : "Collection ... does not exist" pendant qu'un upload de document
        # tournait en arrière-plan).
        vecteur_question = embeddings.embed_query(query)
        categories = set(deviner_categories(vecteur_question))
        # "general" est un filet de sécurité PARTAGÉ (contenu jamais étiqueté par l'agent) —
        # toujours interrogé EN PLUS des catégories devinées (bug réel constaté avant :
        # l'exclure rendait invisible tout contenu plus ancien, jamais catégorisé, même pour
        # une question évidente comme le télétravail).
        categories.add("general")

        tabulaire_store = Chroma(
            collection_name="tabulaire_excel_csv",
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        )
        politique_store = Chroma(
            collection_name="politique_pdf",
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        )

        listes_par_collection = [
            tabulaire_store.similarity_search_with_relevance_scores(query, k=k_tabulaire),
            politique_store.similarity_search_with_relevance_scores(query, k=k_politique),
        ]
        for categorie in categories:
            qa_store = Chroma(
                collection_name=f"qa_{categorie}",
                embedding_function=embeddings,
                persist_directory=CHROMA_DIR,
            )
            listes_par_collection.append(qa_store.similarity_search_with_relevance_scores(query, k=k_qa))

        # Fusion par RANG (Reciprocal Rank Fusion), PAS par score brut — bug réel constaté :
        # le score cosinus n'est pas comparable entre collections de styles de texte différents.
        # tabulaire_excel_csv contient des phrases synthétiques ("Cette entrée a les
        # caractéristiques suivantes : X vaut Y"), loin du langage naturel des paires Q/R des
        # collections qa_* — un candidat tabulaire CORRECT et 1er dans sa propre collection
        # (score 0.79) se faisait évincer du top k_total par des candidats qa_* HORS SUJET mais
        # mieux scorés dans l'absolu (0.84), juste parce que leur style de phrase ressemble
        # davantage à une question. Constaté sur une vraie question ("action de résolution sur
        # CNC_Machine_01") : la bonne réponse disparaissait entièrement du contexte donné au LLM.
        # RRF ignore la valeur absolue du score et ne regarde que le RANG au sein de sa propre
        # collection (déjà triée par similarity_search_with_relevance_scores) — un rang 1 pèse
        # pareil, peu importe la collection d'origine, donc aucune collection n'est structurellement
        # désavantagée par son style de texte. K_RRF=60 est la constante standard de la méthode
        # (Cormack et al., 2009), pas ajustée pour ce corpus précis.
        K_RRF = 60
        candidats_rrf = [
            (document, 1.0 / (K_RRF + rang))
            for liste in listes_par_collection
            for rang, (document, _score_brut) in enumerate(liste, start=1)
        ]
        candidats_tries = sorted(candidats_rrf, key=lambda paire: paire[1], reverse=True)
        resultats = [document for document, score in candidats_tries[:k_total]]

        # Pour toute réponse SCINDÉE (bloc trop long à l'ingestion, voir decouper_par_bloc
        # dans ingest_txt.py), remplace le fragment retrouvé par le texte ORIGINAL complet
        # (stocké tel quel dans les métadonnées à l'ingestion) — sinon un résultat retenu peut
        # n'être qu'un FRAGMENT de la réponse, avec un chevauchement qui ressemble à plusieurs
        # réponses redondantes plutôt qu'à des morceaux ordonnés d'une seule (bug réel constaté :
        # même en récupérant les 3 morceaux séparément, le LLM n'en recomposait qu'un fragment
        # tronqué au lieu de la réponse complète). Dédoublonne par groupe_id : si 2 fragments du
        # même groupe apparaissent dans le top k_total, un seul texte complet est gardé.
        resultats_finaux = []
        groupes_deja_ajoutes = set()
        for document in resultats:
            groupe_id = document.metadata.get("groupe_id")
            if not groupe_id:
                resultats_finaux.append(document)
                continue
            if groupe_id in groupes_deja_ajoutes:
                continue
            groupes_deja_ajoutes.add(groupe_id)
            resultats_finaux.append(Document(page_content=document.metadata["texte_complet"], metadata=document.metadata))

        return resultats_finaux

    return RunnableLambda(retrieve)
