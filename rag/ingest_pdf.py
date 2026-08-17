"""
Ingère TOUS les .pdf de rag_documents/ dans la collection Chroma 'politique'.
DirectoryLoader convient ici (comme pour ingest_txt.py) — pas de logique personnalisée
par fichier à appliquer, juste charger + découper.
PDFPlumberLoader (pas PyPDFLoader) — testé empiriquement : PyPDFLoader aplatit le tableau
du barème de congés (chaque cellule sur sa propre ligne, "Moins d'1 an"/"18"/"0" séparés,
plus de lien entre eux), alors que PDFPlumberLoader garde chaque ligne du tableau groupée
("Moins d'1 an 18 0"). Vaut le coût supplémentaire maintenant qu'il y a un vrai tableau.
Applique RecursiveCharacterTextSplitter pour découper le long document en chunks.
À relancer à chaque changement/ajout d'un fichier .pdf : python rag/ingest_pdf.py
"""
import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
# Le modèle est déjà en cache local (~1 Go, déjà téléchargé) — sans ça, HuggingFaceEmbeddings
# tente quand même une requête réseau vers le Hub à chaque lancement (juste pour vérifier des
# métadonnées), qui peut traîner ou bloquer si la connexion est lente. Inutile ici.
os.environ["HF_HUB_OFFLINE"] = "1"

from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, PDFPlumberLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Chemins absolus ancrés sur ce fichier (voir retriever.py) : sinon, appeler main() depuis
# un dossier différent de la racine du projet (ex. le process FastAPI, pour la route
# d'upload) lirait/écrirait au mauvais endroit, silencieusement.
_RACINE_PROJET = Path(__file__).resolve().parent.parent
CHROMA_DIR = str(_RACINE_PROJET / "chroma_store")
COLLECTION = "politique_pdf"
RAG_DOCUMENTS_DIR = str(_RACINE_PROJET / "rag_documents")
EMBED_MODEL = "intfloat/multilingual-e5-small"

CHUNK_SIZE = 250
CHUNK_OVERLAP = 30
# Testé empiriquement sur politique_entreprise.pdf (sections numérotées courtes) : à 500/200,
# 5 chunks sur 13 mélangeaient 2 sections différentes (ex. fin de "3. Télétravail" collée au
# début de "4. ..."). 250/30 élimine complètement le mélange (0/N) — même réglage que
# ingest_txt.py, pour la même raison (chevauchement trop grand par rapport à la taille d'un
# sujet).


def main():
    print("Loading PDF files...")
    # Comme pour ingest_txt.py : DirectoryLoader trouve tous les .pdf lui-même, et délègue
    # la lecture de CHAQUE fichier trouvé à PDFPlumberLoader (loader_cls).
    loader = DirectoryLoader(
        RAG_DOCUMENTS_DIR,
        glob="*.pdf",
        loader_cls=PDFPlumberLoader,
    )
    pages = loader.load()
    print(f"  {len(pages)} page(s) chargée(s), depuis : "
          + ", ".join(sorted(set(os.path.basename(p.metadata["source"]) for p in pages))))

    print(f"Chunking (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ",""],
    )
    chunks = splitter.split_documents(pages)

    # "source" est déjà rempli automatiquement par PDFPlumberLoader (le vrai chemin du
    # fichier) — simplifié ici au nom du fichier seul, plus lisible.
    for i, chunk in enumerate(chunks):
        chunk.metadata["source"] = os.path.basename(chunk.metadata["source"])
        chunk.metadata["chunk_index"] = i

    print(f"  {len(chunks)} chunks produced.")

    print("Initialising embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    # Reset avant réinsertion, pour éviter d'accumuler des doublons à chaque relance.
    Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    ).delete_collection()

    print(f"Embedding and storing in Chroma collection '{COLLECTION}'...")
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION,
        persist_directory=CHROMA_DIR,
    )
    print(f"  Done. {vectorstore._collection.count()} vectors stored.")


if __name__ == "__main__":
    main()
