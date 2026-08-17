"""
Ingère TOUS les .txt de rag_documents/ — DirectoryLoader convient ici (contrairement à
Excel/CSV) car on n'a pas de logique personnalisée à appliquer par fichier, juste
charger + découper, ce que TextLoader fait très bien seul.
Découpe par bloc Q/R (ligne vide = frontière) plutôt que par RecursiveCharacterTextSplitter
directement — sinon deux blocs courts de catégories différentes pourraient être recollés
dans le même chunk (voir decouper_par_bloc). RecursiveCharacterTextSplitter ne sert plus
qu'en filet de sécurité, si un bloc dépasse quand même chunk_size.
Contrairement à avant, ne met PLUS tout dans une seule collection 'qa_txt' — chaque chunk
est routé vers UNE des 6 collections par sujet (qa_rh/qa_it/qa_finance/qa_production/
qa_commercial/qa_general), selon la ligne "Catégorie : ..." que l'agent de standardisation
(agent_standardisation.py) ajoute à chaque bloc — pour que le retriever puisse chercher
dans une seule collection ciblée au lieu de tout le corpus à chaque question.
À relancer à chaque changement/ajout d'un fichier .txt : python rag/ingest_txt.py
"""

import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
# Le modèle est déjà en cache local (~450 Mo, déjà téléchargé) — sans ça, HuggingFaceEmbeddings
# tente quand même une requête réseau vers le Hub à chaque lancement (juste pour vérifier des
# métadonnées), qui peut traîner ou bloquer si la connexion est lente. Inutile ici.
os.environ["HF_HUB_OFFLINE"] = "1"
import re
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

# Chemins absolus ancrés sur ce fichier (voir retriever.py) : sinon, appeler main() depuis
# un dossier différent de la racine du projet (ex. le process FastAPI, pour la route
# d'upload) lirait/écrirait au mauvais endroit, silencieusement.
_RACINE_PROJET = Path(__file__).resolve().parent.parent
CHROMA_DIR = str(_RACINE_PROJET / "chroma_store")
RAG_DOCUMENTS_DIR = str(_RACINE_PROJET / "rag_documents")
EMBED_MODEL = "intfloat/multilingual-e5-small"

# Mêmes 7 catégories que agent_standardisation.py — liste FIXE, pas à inventer, jamais de
# variante accentuée dedans (Chroma interdit les accents dans un nom de collection — bug réel
# constaté : "qa_général" invalide). "general" sert aussi de filet de sécurité pour les
# fichiers plus anciens, écrits avant l'ajout de la ligne "Catégorie :" (aucune étiquette
# trouvée = general, pas une erreur).
CATEGORIES_CONNUES = {"rh", "it", "finance", "production", "commercial", "legal", "general"}
MOTIF_CATEGORIE = re.compile(r"^Catégorie\s*:\s*(.+)$", re.MULTILINE)

CHUNK_SIZE = 350
CHUNK_OVERLAP = 50
# Testé empiriquement : 250/30 éliminait le mélange de paires Q/R courtes mais cassait les
# réponses plus longues (~500-700 caractères) en plein milieu de phrase, rendant certaines
# réponses IA incomplètes ou introuvables (vérifié en réel : réponse tronquée sur "processus
# de candidature", "information non disponible" sur "remboursement des frais"). 350/50 est le
# meilleur compromis trouvé : toujours 0 mélange sur les entrées courtes, ET garde intactes 2
# réponses longues sur 3 (contre 0/3 à 250/30) — au-delà (450+), le mélange réapparaît (7 à 12
# chunks) sans gain supplémentaire. Une réponse VRAIMENT longue (700+ caractères) doit être
# découpée en plusieurs sous-questions dans le document lui-même — aucun chunk_size ne peut la
# garder entière sans réintroduire le mélange ailleurs.


MOTIF_BLOC_QR = re.compile(r"^(Q\s*:.*?)\n(R\s*:.*)$", re.DOTALL)

splitter_secours = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n", ".", " ", ""],
)


# Découpe un bloc Q/R trop long en gardant la question en préfixe de CHAQUE morceau — sinon
# splitter_secours.split_text() traite "Q :...\nR :..." comme un seul texte et peut couper
# pile sur le \n entre les deux, séparant la réponse de sa question dans deux chunks
# différents (bug réel constaté sur un bloc de 410 caractères : le chunk retrouvé ne contenait
# plus que "Q :", sans "R :" — le LLM répondait "information non disponible" alors que la
# réponse existait bel et bien dans le document).
def _decouper_bloc_trop_long(texte: str) -> list[str]:
    correspondance = MOTIF_BLOC_QR.match(texte)
    if not correspondance:
        return splitter_secours.split_text(texte)
    ligne_q, ligne_r = correspondance.group(1), correspondance.group(2)
    # Budget réduit du "Q : ...\n" déjà réattaché à chaque morceau — sinon le morceau de R
    # (calculé seul, sans compter la question qu'on va lui recoller) reste sous CHUNK_SIZE et
    # le splitter ne coupe rien, alors que le résultat final (Q + R recollés) dépasse quand
    # même CHUNK_SIZE (bug réel constaté : bloc de 410 caractères ressorti intact, alors que
    # cette fonction n'est censée s'activer QUE pour rester sous la limite).
    budget_reponse = max(CHUNK_SIZE - len(ligne_q) - 1, 50)
    splitter_reponse = RecursiveCharacterTextSplitter(
        chunk_size=budget_reponse,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[".", " ", ""],
    )
    return [f"{ligne_q}\n{sous_reponse}" for sous_reponse in splitter_reponse.split_text(ligne_r)]


# Découpe le texte d'UN fichier en blocs Q/R (séparés par une ligne vide), extrait la
# catégorie de chacun, et ne fait appel à RecursiveCharacterTextSplitter QUE si un bloc
# dépasse quand même chunk_size (rare, filet de sécurité) — pour ne jamais fusionner deux
# blocs de catégories différentes dans un même chunk, ce qu'un split "chunk_size direct"
# ferait sans distinction.
def decouper_par_bloc(document: Document) -> list[Document]:
    nom_fichier = os.path.basename(document.metadata["source"])
    blocs_bruts = [b.strip() for b in document.page_content.split("\n\n") if b.strip()]

    resultats = []
    for indice_bloc, bloc in enumerate(blocs_bruts):
        correspondance = MOTIF_CATEGORIE.search(bloc)
        # Normalise (minuscule + accents retirés, ex. "Général" -> "general") AVANT de
        # vérifier l'appartenance à CATEGORIES_CONNUES — sinon "général" (accentué, ce que
        # l'agent écrit en français) ne matcherait jamais la valeur canonique "general".
        valeur_normalisee = (
            correspondance.group(1).strip().lower().replace("é", "e") if correspondance else None
        )

        if valeur_normalisee in CATEGORIES_CONNUES:
            categorie = valeur_normalisee
            texte = MOTIF_CATEGORIE.sub("", bloc, count=1).strip()
        else:
            # Pas d'étiquette, ou étiquette non reconnue (fichiers plus anciens, écrits avant
            # cette règle) : filet de sécurité "general", plutôt que de perdre le contenu ou planter.
            categorie = "general"
            texte = bloc

        sous_textes = [texte] if len(texte) <= CHUNK_SIZE else _decouper_bloc_trop_long(texte)
        # groupe_id + texte_complet : uniquement quand le bloc a dû être scindé (plusieurs
        # morceaux) — permet au retriever de substituer le texte ORIGINAL complet à n'importe
        # quel morceau retrouvé, au lieu de renvoyer des fragments qui se chevauchent (à cause
        # de CHUNK_OVERLAP) et qui, présentés tels quels au LLM, ressemblent à plusieurs
        # réponses redondantes plutôt qu'à des morceaux ordonnés d'UNE seule réponse — bug réel
        # constaté : même en récupérant les 3 morceaux, le LLM n'en recomposait qu'un fragment
        # tronqué au lieu de la réponse complète.
        groupe_id = f"{nom_fichier}#{indice_bloc}" if len(sous_textes) > 1 else None
        for sous_texte in sous_textes:
            metadonnees = {"source": nom_fichier, "categorie": categorie}
            if groupe_id:
                metadonnees["groupe_id"] = groupe_id
                metadonnees["texte_complet"] = texte
            resultats.append(Document(page_content=sous_texte, metadata=metadonnees))

    return resultats
def main():
    print("Loading TXT files...")
    # DirectoryLoader trouve tous les .txt du dossier lui-même, et délègue la lecture de
    # CHAQUE fichier trouvé à TextLoader (loader_cls) — plus besoin de connaître le nom
    # exact d'un fichier à l'avance, contrairement à avant (TXT_PATH codé en dur).
    loader = DirectoryLoader(
        RAG_DOCUMENTS_DIR,
        glob="*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    
    documents = loader.load()
    print(f"  {len(documents)} document(s) chargé(s) : "
          + ", ".join(os.path.basename(d.metadata["source"]) for d in documents))

    print(f"Chunking par bloc Q/R (chunk_size={CHUNK_SIZE} en filet de sécurité)...")
    chunks = []
    for document in documents:
        chunks.extend(decouper_par_bloc(document))

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i

    print(f"  {len(chunks)} chunks produced.")

    repartition = {}
    for chunk in chunks:
        repartition[chunk.metadata["categorie"]] = repartition.get(chunk.metadata["categorie"], 0) + 1
    print(f"  Répartition par catégorie : {repartition}")

    print("Initialising embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    # Un chunk par catégorie -> une collection par catégorie (qa_rh, qa_it, ...) — reset
    # de CHAQUE collection avant réinsertion, pour éviter d'accumuler des doublons.
    for categorie in CATEGORIES_CONNUES:
        nom_collection = f"qa_{categorie}"
        chunks_categorie = [c for c in chunks if c.metadata["categorie"] == categorie]

        Chroma(
            collection_name=nom_collection,
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        ).delete_collection()

        if not chunks_categorie:
            continue

        print(f"Embedding and storing {len(chunks_categorie)} chunk(s) in Chroma collection '{nom_collection}'...")
        # Pas Chroma.from_documents() (qui embedderait page_content TEL QUEL) : e5-small est
        # entraîné avec un préfixe "passage: " pour tout texte comparé à une question (voir le
        # même commentaire dans retriever.py) — mais ce préfixe ne doit JAMAIS apparaître dans
        # le texte stocké/montré au LLM, seulement dans le texte donné au modèle pour calculer
        # le vecteur. D'où les 2 étapes séparées : embedder le texte préfixé, stocker l'original.
        textes = [c.page_content for c in chunks_categorie]
        vecteurs = embeddings.embed_documents([f"passage: {t}" for t in textes])
        vectorstore = Chroma(
            collection_name=nom_collection,
            embedding_function=embeddings,
            persist_directory=CHROMA_DIR,
        )
        vectorstore._collection.add(
            ids=[str(c.metadata["chunk_index"]) for c in chunks_categorie],
            embeddings=vecteurs,
            documents=textes,
            metadatas=[c.metadata for c in chunks_categorie],
        )
        print(f"  Done. {vectorstore._collection.count()} vectors stored.")


if __name__ == "__main__":
    main()


