# Importe FastAPI pour créer l’application backend.
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Query
# Importe CORSMiddleware pour autoriser le frontend à appeler le backend.
from fastapi.middleware.cors import CORSMiddleware
# Importe StaticFiles pour servir le frontend depuis ce même serveur (voir bas de fichier) —
# évite d'avoir besoin d'un deuxième tunnel ngrok/serveur juste pour les fichiers statiques.
from fastapi.staticfiles import StaticFiles
# Importe IntegrityError pour détecter un formulaire déjà importé (contrainte UNIQUE).
from sqlalchemy.exc import IntegrityError

# os.getenv() lit les variables d'environnement, load_dotenv() charge backend/.env.
import os
import sys
import threading
from pathlib import Path
from dotenv import load_dotenv

_RACINE_PROJET = Path(__file__).resolve().parent.parent.parent

# Même schéma que database.py/ia_service.py : chaque fichier qui a besoin de variables
# d'environnement charge explicitement backend/.env lui-même, sans dépendre de l'ordre
# des imports pour que ce soit déjà fait.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
# Importe le modèle qui décrit la structure correcte d’un formulaire reçu.
from backend.app.schemas.formulaire import FormulaireEntree
# Importe le modèle qui vérifie le statut envoyé pour une réponse.
from backend.app.schemas.reponse import StatutReponseModification
# Importe la fonction qui enregistre le formulaire dans PostgreSQL.
from backend.app.services.formulaire_service import  enregistrer_formulaire, lister_formulaires
from backend.app.services.ia_service import extraire_formulaire_depuis_url
from backend.app.services.traitement_service import traiter_questions_textuelles
from backend.app.services.reponse_service import (
    lister_reponses_proposees,
    lister_reponses_par_formulaire,
    lister_historique_formulaire,
   modifier_statut_reponse,
)

# Même principe que dans ia_service.py (rag/retriever.py) : rag/ n'est pas un package du
# backend, donc on l'ajoute au chemin de recherche des modules Python pour pouvoir importer
# ses scripts d'ingestion directement, sans les dupliquer ici.
sys.path.append(str(_RACINE_PROJET / "rag"))
import standardiser_document
import ingest_txt
import ingest_tabulaire

# Crée l’application principale.
app = FastAPI(title="Plateforme IA de réponses aux formulaires")


# Autorise le(s) frontend(s) à communiquer avec ce backend — lu depuis .env (comme DB_HOST
# dans database.py), pas codé en dur, pour que chaque environnement (dev chez un développeur,
# production en entreprise) puisse avoir sa propre adresse sans jamais toucher ce fichier
# partagé. Plusieurs origines possibles à la fois, séparées par des virgules dans .env.
origines_autorisees = os.getenv("FRONTEND_URL", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origines_autorisees,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route simple utilisée pour vérifier que le backend fonctionne — déplacée de "/" vers "/api"
# pour laisser "/" au frontend (voir StaticFiles monté en bas de ce fichier).
@app.get("/api")
def accueil():
    return {"message": "Bienvenue sur l'API"}


# Route utilisée pour recevoir un formulaire envoyé au backend.
# POST signifie qu’on envoie des données au backend.
# status_code=201 signifie que la ressource a été reçue/créée avec succès.
@app.post("/formulaires", status_code=201)
def recevoir_formulaire(formulaire: FormulaireEntree):
    # Le formulaire est déjà validé automatiquement par Pydantic ici.

    # Enregistre le formulaire validé dans PostgreSQL.
    formulaire_db_id = enregistrer_formulaire(formulaire)

    return {
        "message": "Formulaire enregistré avec succès",
        "id": formulaire_db_id,
        "formulaire_id": formulaire.formulaire_id,
        "nombre_questions": len(formulaire.questions),
    }



@app.post("/traitements/questions-textuelles")
def lancer_traitement_questions_textuelles(formulaire_id: int, modele_ia: str = "gemini-3.1-flash-lite"):
    # Lance le traitement du formulaire précisé, avec le modèle IA choisi dans l’URL.
    resultats = traiter_questions_textuelles(formulaire_id, modele_ia)

    return {
        "message": "Traitement terminé",
        "modele_ia": modele_ia,
        "nombre_reponses": len(resultats),
        "resultats": resultats,
    }


@app.get("/reponses")
def lire_reponses():
    reponses = lister_reponses_proposees()

    return {
        "nombre_reponses": len(reponses),
        "reponses": reponses,
    }


@app.patch("/reponses/{reponse_id}/statut")
def changer_statut_reponse(
    reponse_id: int,
    modification: StatutReponseModification,
):
    # Modifie le statut dans PostgreSQL.
    reponse = modifier_statut_reponse(
        reponse_id=reponse_id,
        statut=modification.statut,
        commentaire=modification.commentaire,
        valeur=modification.valeur,
    )

    # Si l’id n’existe pas, aucune réponse n’a été modifiée.
    if reponse is None:
        return {
            "message": "Réponse introuvable",
            "reponse_id": reponse_id,
        }

    # Retourne la réponse mise à jour.
    return {
        "message": "Statut modifié avec succès",
        "reponse": reponse,
    }


@app.get("/formulaires")
def lire_formulaires():
    # Liste tous les formulaires importés — utilisé par la page historique.html pour
    # afficher un titre cliquable par formulaire, avant de choisir lequel consulter.
    formulaires = lister_formulaires()

    return {
        "nombre_formulaires": len(formulaires),
        "formulaires": formulaires,
    }


@app.get("/formulaires/{formulaire_id}/reponses")
def lire_reponses_formulaire(formulaire_id: int):
    # Récupère seulement les réponses liées à ce formulaire.
    reponses = lister_reponses_par_formulaire(formulaire_id)

    return {
        "formulaire_id": formulaire_id,
        "nombre_reponses": len(reponses),
        "reponses": reponses,
    }


@app.get("/formulaires/{formulaire_id}/historique")
def lire_historique_formulaire(formulaire_id: int):
    # Récupère TOUTES les réponses de ce formulaire (pas seulement la dernière par question).
    historique = lister_historique_formulaire(formulaire_id)

    return {
        "formulaire_id": formulaire_id,
        "nombre_reponses": len(historique),
        "historique": historique,
    }

# source.type (produit par l'extraction) ne s'écrit pas exactement pareil que fournisseur
# (attendu par FormulaireEntree/la contrainte SQL) — cette table fait la correspondance.
FOURNISSEUR_PAR_TYPE_SOURCE = {
    "google_forms_public": "google_forms",
    "microsoft_forms_scraping": "microsoft_forms",
}


@app.post("/formulaires/depuis-url", status_code=201)
def recevoir_formulaire_depuis_url(url: str, documents_associes: list[str] | None = Query(default=None)):
    # Étape 1 : extrait le formulaire (détecte Google/Microsoft toute seule).
    formulaire_brut = extraire_formulaire_depuis_url(url)

    # Étape 2 : construit un FormulaireEntree validé — l'extraction ne produit ni
    # formulaire_id, ni un fournisseur dans le format exact attendu, donc on les
    # complète nous-mêmes ici, à partir de ce que l'extraction a réellement trouvé.
    formulaire = FormulaireEntree(
        formulaire_id=url,
        fournisseur=FOURNISSEUR_PAR_TYPE_SOURCE[formulaire_brut["source"]["type"]],
        titre=formulaire_brut["titre"],
        source=formulaire_brut["source"],
        description=formulaire_brut.get("description"),
        date_extraction=formulaire_brut.get("date_extraction"),
        statut_extraction=formulaire_brut.get("statut_extraction"),
        questions=formulaire_brut["questions"],
        documents_associes=documents_associes,
    )

    # Étape 3 : enregistre le formulaire validé — même fonction que POST /formulaires.
    # Un même lien déjà importé viole la contrainte UNIQUE (fournisseur, identifiant_externe) —
    # voulu, pas un bug (voir uq_formulaire_fournisseur_identifiant). Sans ce try/except, cette
    # IntegrityError remontait en erreur 500 non gérée, qui ne passe pas par le middleware CORS
    # (ServerErrorMiddleware, en dehors du CORS, génère la réponse) : le navigateur bloquait alors
    # la réponse et fetch() plantait côté frontend avant même de lire le code HTTP. Un 409 (déjà
    # géré par FastAPI) passe normalement par le CORS et laisse le frontend afficher un message clair.
    #
    # IMPORTANT : cette table n'est pas la seule à avoir une contrainte — enregistrer_formulaire
    # insère aussi dans questions/options/grille_*, qui ont chacune leurs propres contraintes
    # (bug réel constaté : une question au contenu incomplet levait une IntegrityError totalement
    # différente, mais tombait dans ce même except et affichait à tort "déjà importé"). On regarde
    # donc le NOM de la contrainte violée pour ne renvoyer ce message que si c'est vraiment un
    # doublon ; toute autre violation renvoie son vrai message.
    try:
        formulaire_db_id = enregistrer_formulaire(formulaire)
    except IntegrityError as erreur:
        nom_contrainte = getattr(getattr(erreur.orig, "diag", None), "constraint_name", None)
        if nom_contrainte == "uq_formulaire_fournisseur_identifiant":
            raise HTTPException(
                status_code=409,
                detail="Ce formulaire a déjà été importé.",
            )
        raise HTTPException(
            status_code=422,
            detail=f"Le formulaire contient des données invalides ({nom_contrainte or 'contrainte inconnue'}).",
        )

    return {
        "message": "Formulaire importé et enregistré avec succès",
        "id": formulaire_db_id,
        "formulaire_id": formulaire.formulaire_id,
        "nombre_questions": len(formulaire.questions),
    }


RAG_DOCUMENTS_DIR = _RACINE_PROJET / "rag_documents"


# Tous les formats "à mise en page" que Docling sait nativement décoder (vérifié dans
# DocumentConverter().allowed_formats) — une seule liste, réutilisée pour le glob() ci-dessous
# ET pour EXTENSIONS_VERS_INGESTION, pour ne jamais avoir à mettre à jour 2 endroits séparés
# si un format est ajouté/retiré un jour.
EXTENSIONS_MISE_EN_PAGE = [".pdf", ".docx", ".doc", ".pptx", ".html", ".odt"]


# Compteur d'ingestions RAG actuellement en cours en arrière-plan (documents à mise en page ET
# fichiers txt/xlsx/csv) — bug réel constaté : un document tout juste uploadé pouvait être
# interrogé par "Start processing" AVANT que son indexation en arrière-plan soit terminée, le
# RAG cherchant alors dans une base pas encore à jour (aucun résultat trouvé, réponse "information
# non disponible" alors que l'information existe bien). Le frontend interroge GET
# /documents-rag/statut pour savoir s'il faut attendre avant de lancer un traitement.
# threading.Lock() : plusieurs tâches d'arrière-plan peuvent s'exécuter en parallèle
# (ThreadPoolExecutor interne de FastAPI), incrémenter/décrémenter un entier partagé sans
# verrou n'est pas garanti atomique.
_verrou_indexation = threading.Lock()
_indexations_en_cours = 0


def _executer_avec_suivi_indexation(fonction, *args):
    global _indexations_en_cours
    with _verrou_indexation:
        _indexations_en_cours += 1
    try:
        fonction(*args)
    finally:
        with _verrou_indexation:
            _indexations_en_cours -= 1


@app.get("/documents-rag/statut")
def statut_indexation_documents():
    return {"indexation_en_cours": _indexations_en_cours > 0}


# Liste les documents RAG déjà uploadés, pour que le frontend propose une case à cocher par
# document au moment d'importer un formulaire (voir formulaires.documents_associes en base et
# retrieve(sources_autorisees=...) dans retriever.py). "source" est la valeur EXACTE stockée
# dans les métadonnées Chroma (voir ingest_txt.py/ingest_tabulaire.py) — c'est elle qu'il faut
# renvoyer telle quelle à POST /formulaires/depuis-url, pas "nom_original" (juste pour l'affichage).
@app.get("/documents-rag")
def lister_documents_rag():
    documents = []
    for chemin in sorted(RAG_DOCUMENTS_DIR.iterdir()):
        if chemin.name.endswith(":Zone.Identifier") or chemin.name.startswith("format_standard_"):
            continue
        if chemin.suffix.lower() in EXTENSIONS_MISE_EN_PAGE or chemin.suffix.lower() == ".txt":
            source = f"format_standard_{chemin.stem}.txt"
        else:
            # .xlsx/.csv : la métadonnée "source" est le nom du fichier original tel quel
            # (voir ingest_tabulaire.py), pas un format_standard_*.txt dérivé.
            source = chemin.name
        documents.append({"nom_original": chemin.name, "source": source})
    return {"documents": documents}


# Un seul pipeline pour tous les documents à mise en page (voir retriever.py et
# standardiser_document.py — DocumentConverter() de Docling détecte le format tout seul, tous
# les formats de EXTENSIONS_MISE_EN_PAGE partagent donc exactement le même chemin, pas un
# script par format) : Docling + découpage en lots + agent_standardisation, jamais un appel
# direct sur tout le texte (qui perd du contenu sur un document volumineux), puis
# ingest_txt.main() pour l'embedding.
# Prend la liste EXACTE des documents à traiter (pas un scan de tout rag_documents/) — bug
# réel constaté : un scan complet, à chaque upload, retraitait aussi les 11 PDF DÉJÀ
# standardisés sous d'autres noms historiques (ex. format_standard_aup.txt pour
# acceptable-use-policy.pdf, pas format_standard_acceptable-use-policy.txt) : la convention de
# nommage automatique ne matchait jamais ces anciens fichiers, donc "chemin_sortie.exists()"
# était toujours faux pour eux — 4 doublons complets recréés (nouveaux appels Gemini réels,
# temps et quota gaspillés) avant même d'atteindre le document réellement envoyé par
# l'utilisateur. Chaque upload ne doit standardiser QUE ce qu'il vient d'envoyer.
def standardiser_et_ingerer_document(chemins_documents: list[Path]):
    for chemin_document in chemins_documents:
        chemin_sortie = RAG_DOCUMENTS_DIR / f"format_standard_{chemin_document.stem}.txt"
        if not chemin_sortie.exists():
            standardiser_document.main(str(chemin_document), str(chemin_sortie))
    ingest_txt.main()


# Associe chaque extension supportée à la fonction d'ingestion du bon script — un Excel/CSV
# passe par ingest_tabulaire.main() (les deux formats partagent déjà le même script), un TXT
# par ingest_txt.main(). Les formats à mise en page (EXTENSIONS_MISE_EN_PAGE) n'ont PAS
# d'entrée ici : contrairement à ingest_txt.main()/ingest_tabulaire.main() (rescans complets,
# sans coût IA, donc sûrs à relancer sur tout le dossier), standardiser_et_ingerer_document()
# a un vrai coût (appels Gemini) et doit recevoir la liste précise des fichiers concernés —
# gérée séparément dans la route ci-dessous, pas via ce dictionnaire de fonctions sans argument.
EXTENSIONS_VERS_INGESTION = {
    **{extension: None for extension in EXTENSIONS_MISE_EN_PAGE},
    ".txt": ingest_txt.main,
    ".xlsx": ingest_tabulaire.main,
    ".csv": ingest_tabulaire.main,
}


@app.post("/documents-rag", status_code=201)
async def recevoir_document_rag(
    taches_arriere_plan: BackgroundTasks,
    fichiers: list[UploadFile] = File(...),
    remplacer: bool = False,
):
    # Valide TOUS les fichiers avant d'en écrire un seul sur le disque — sinon, un format
    # invalide ou un doublon au milieu du lot laisserait les fichiers précédents déjà
    # sauvegardés pour rien.
    doublons = []
    for fichier in fichiers:
        extension = Path(fichier.filename).suffix.lower()
        if extension not in EXTENSIONS_VERS_INGESTION:
            raise HTTPException(
                status_code=422,
                detail=f"Format non supporté pour '{fichier.filename}' — "
                       f"seuls {', '.join(sorted(EXTENSIONS_VERS_INGESTION))} sont acceptés.",
            )

        if (RAG_DOCUMENTS_DIR / fichier.filename).exists():
            doublons.append(fichier.filename)

    # remplacer=False (valeur par défaut, premier essai) : on liste TOUS les doublons trouvés
    # (pas juste le premier) et on laisse le frontend demander confirmation à l'utilisateur
    # avant d'écraser quoi que ce soit. remplacer=True (renvoyé après confirmation) : on
    # ignore ce contrôle et on écrase directement.
    if doublons and not remplacer:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Ces documents existent déjà.",
                "doublons": doublons,
            },
        )

    # Sauvegarde chaque fichier dans rag_documents/ — le même dossier que les scripts
    # d'ingestion scannent déjà (jusqu'ici rempli à la main).
    # fonctions_a_lancer (set) : pour .txt/.xlsx/.csv, un rescan complet est sûr et gratuit,
    # donc dédoublonner par fonction suffit (2 CSV -> ingest_tabulaire.main() une seule fois).
    # documents_mise_en_page (liste) : pour PDF/DOCX/..., on garde le chemin EXACT de chaque
    # fichier reçu dans CETTE requête — jamais un rescan de tout le dossier (voir le commentaire
    # sur standardiser_et_ingerer_document plus haut pour le bug réel que ça causait).
    fonctions_a_lancer = set()
    documents_mise_en_page = []
    for fichier in fichiers:
        extension = Path(fichier.filename).suffix.lower()
        destination = RAG_DOCUMENTS_DIR / fichier.filename
        destination.write_bytes(await fichier.read())
        if extension in EXTENSIONS_MISE_EN_PAGE:
            documents_mise_en_page.append(destination)
        else:
            fonctions_a_lancer.add(EXTENSIONS_VERS_INGESTION[extension])

    # add_task() ne lance PAS la fonction maintenant — elle est mise de côté et exécutée
    # seulement APRÈS que la réponse ait été envoyée au frontend. C'est ça qui rend l'upload
    # rapide : l'utilisateur reçoit "201 OK" tout de suite, l'indexation (lente) tourne après,
    # sans qu'il ait à attendre devant son écran.
    for fonction_ingestion in fonctions_a_lancer:
        taches_arriere_plan.add_task(_executer_avec_suivi_indexation, fonction_ingestion)
    if documents_mise_en_page:
        taches_arriere_plan.add_task(
            _executer_avec_suivi_indexation, standardiser_et_ingerer_document, documents_mise_en_page
        )

    return {
        "message": "Documents reçus — indexation en cours en arrière-plan",
        "noms_fichiers": [fichier.filename for fichier in fichiers],
    }


# Monté en dernier, sur "/" : Starlette teste les routes dans l'ordre où elles sont
# déclarées, donc toutes les routes API ci-dessus (déclarées avant) restent prioritaires —
# ce montage ne sert que ce qu'aucune route API n'a déjà pris en charge. html=True fait
# répondre index.html automatiquement sur "/".
app.mount("/", StaticFiles(directory=str(_RACINE_PROJET / "frontend"), html=True), name="frontend")


