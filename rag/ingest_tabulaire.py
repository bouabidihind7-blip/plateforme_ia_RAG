"""
Ingère les documents TABULAIRES (Excel et CSV) de rag_documents/ dans Chroma.
Excel et CSV se traitent de façon identique une fois lus (les deux deviennent un
DataFrame pandas) — seule la fonction de lecture change, donc un seul fichier partagé
plutôt qu'un fichier par format.
Un Document par LIGNE de tableau (pas de découpage à taille fixe — chaque ligne est déjà
un fait autonome).
À relancer à chaque changement d'un des fichiers source : python rag/ingest_tabulaire.py
"""
import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
# Le modèle est déjà en cache local (~1 Go, déjà téléchargé) — sans ça, HuggingFaceEmbeddings
# tente quand même une requête réseau vers le Hub à chaque lancement (juste pour vérifier des
# métadonnées), qui peut traîner ou bloquer si la connexion est lente. Inutile ici.
os.environ["HF_HUB_OFFLINE"] = "1"

from pathlib import Path
import pandas as pd
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

_RACINE_PROJET = Path(__file__).resolve().parent.parent
CHROMA_DIR = str(_RACINE_PROJET / "chroma_store")
COLLECTION = "tabulaire_excel_csv"
# Testé empiriquement sur nos cas problématiques (Nadia Chraibi, SolarNow) : ce modèle
# donne des scores cohérents (0 à 1) ET classe correctement la bonne réponse en 1re
# position — contrairement à all-MiniLM-L6-v2 (anglais, SolarNow classé 9e/23) et à
# paraphrase-multilingual-MiniLM-L12-v2 (scores négatifs incohérents). Voir MTEB leaderboard
# (huggingface.co/spaces/mteb/leaderboard) — plus gros modèle (~1 Go), donc plus précis.
EMBED_MODEL = "intfloat/multilingual-e5-small"

# Dossier scanné automatiquement (voir main()) — pas de liste de fichiers codée en dur.
# Pas de DirectoryLoader ici : il appliquerait un loader générique (ex. CSVLoader) qui
# redonnerait le format "colonne: valeur" qu'on a corrigé — on garde notre découverte
# de fichiers ET notre propre logique de transformation (ligne_vers_phrase) ensemble.
# Chemin absolu (voir commentaire sur CHROMA_DIR) : sinon, appeler main() depuis le process
# FastAPI (route d'upload) lirait le mauvais dossier, silencieusement.
RAG_DOCUMENTS_DIR = _RACINE_PROJET / "rag_documents"


# Déduit le format ("excel" ou "csv") depuis l'extension du fichier — évite d'avoir à le
# préciser à la main pour chaque fichier trouvé automatiquement.
def format_depuis_extension(chemin: Path) -> str:
    if chemin.suffix == ".xlsx":
        return "excel"
    elif chemin.suffix == ".csv":
        return "csv"
    else:
        raise ValueError(f"Extension non gérée : {chemin.suffix}")


# Lit un fichier tabulaire (Excel ou CSV) et renvoie un dict {nom_feuille: DataFrame} —
# un Excel a de vraies feuilles nommées ; un CSV n'en a qu'une seule, à qui on donne le
# nom du fichier lui-même pour rester cohérent.
def lire_tableau(chemin: str, format_fichier: str, nom_source: str) -> dict:
    if format_fichier == "excel":
        return pd.read_excel(chemin, sheet_name=None)
    elif format_fichier == "csv":
        # comment="#" ignore la ligne d'avertissement "# CONTENU EXEMPLE..." en tête de fichier.
        return {nom_source: pd.read_csv(chemin, comment="#")}
    else:
        raise ValueError(f"Format non géré : {format_fichier}")


# Transforme une ligne en phrase générique — testé empiriquement (Nadia Chraibi, SolarNow) :
# avec multilingual-e5-large-instruct, cette formulation, bien que pas une vraie phrase
# écrite à la main, suffit largement (score 0.820/0.788, presque identique aux templates
# écrits à la main testés avant : 0.851/0.801). Générique : marche pour N'IMPORTE QUEL
# tableau, colonnes inconnues à l'avance — pas de template à écrire pour chaque nouveau
# fichier, contrairement à l'ancienne version (un if/elif par tableau connu).
def ligne_vers_phrase(ligne: pd.Series) -> str:
    parties = [f"{colonne} vaut {valeur}" for colonne, valeur in ligne.items()]
    return "Cette entrée a les caractéristiques suivantes : " + ", ".join(parties) + "."


# Transforme chaque ligne de chaque feuille d'UN fichier en Document indépendant — même
# logique peu importe que ça vienne d'un Excel ou d'un CSV, puisque les deux sont déjà
# des DataFrames à ce stade.
def load_tabular_documents(chemin: str, format_fichier: str) -> list[Document]:
    nom_source = os.path.basename(chemin)
    feuilles = lire_tableau(chemin, format_fichier, nom_source)

    docs = []
    for nom_feuille, tableau in feuilles.items():
        for index_ligne, ligne in tableau.iterrows():
            contenu = ligne_vers_phrase(ligne)

            docs.append(Document(
                page_content=contenu,
                metadata={
                    "source": nom_source,
                    "feuille": nom_feuille,
                    "ligne": int(index_ligne),
                },
            ))

    return docs


def main():
    # Découverte automatique — trouve TOUS les .xlsx et .csv du dossier, pas besoin de les
    # lister à la main. Un nouveau fichier ajouté à rag_documents/ est pris en compte au
    # prochain lancement, sans toucher au code.
    fichiers = sorted(RAG_DOCUMENTS_DIR.glob("*.xlsx")) + sorted(RAG_DOCUMENTS_DIR.glob("*.csv"))
    print(f"  {len(fichiers)} fichier(s) trouvé(s) dans {RAG_DOCUMENTS_DIR}/ : "
          + ", ".join(f.name for f in fichiers))

    print("Loading tabular documents...")
    docs = []
    for fichier in fichiers:
        format_fichier = format_depuis_extension(fichier)
        docs_fichier = load_tabular_documents(str(fichier), format_fichier)
        print(f"  {len(docs_fichier)} lignes chargées depuis {fichier.name}.")
        docs.extend(docs_fichier)

    print(f"  {len(docs)} lignes au total.")

    print("Initialising embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    # Reset avant réinsertion, pour éviter d'accumuler des doublons à chaque relance.
    Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    ).delete_collection()

    print(f"Embedding and storing in Chroma collection '{COLLECTION}'...")
    # Pas Chroma.from_documents() : même raison que dans ingest_txt.py — préfixe "passage: "
    # requis par e5-small pour l'embedding, mais jamais stocké dans le texte affiché au LLM.
    textes = [d.page_content for d in docs]
    vecteurs = embeddings.embed_documents([f"passage: {t}" for t in textes])
    vectorstore = Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )
    vectorstore._collection.add(
        ids=[str(i) for i in range(len(docs))],
        embeddings=vecteurs,
        documents=textes,
        metadatas=[d.metadata for d in docs],
    )
    print(f"  Done. {vectorstore._collection.count()} vectors stored.")


if __name__ == "__main__":
    main()
