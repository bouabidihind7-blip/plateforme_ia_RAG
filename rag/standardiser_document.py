"""
Standardise un document (potentiellement gros/complexe) en paires Q/R, via Docling (extraction
+ structure) + découpage en lots + agent_standardisation.py, plutôt qu'un seul appel LLM direct
sur tout le texte. PAS spécifique au PDF : DocumentConverter() détecte le format tout seul
(vérifié : PDF, DOCX, DOC, PPTX, HTML, ODT... tous supportés nativement par Docling, aucun code
particulier à écrire par format) — un seul pipeline pour tous les documents à mise en page
(PDF/Word/PowerPoint...), pas un script par format.

Pourquoi le découpage en lots est nécessaire (pas juste une optimisation) : testé en réel
qu'un long document envoyé en UN SEUL appel Gemini perd massivement du contenu par résumé
implicite du modèle (cas mesuré : 56K caractères source -> seulement 40 paires Q/R produites,
alors que le même contenu, découpé en lots de ~3000 caractères, en a produit 564+). Un modèle
plus fort (gemini-3.5-flash vs flash-lite) n'a que partiellement compensé (40 -> 59), donc ce
n'est pas un problème de qualité de modèle, mais de longueur de contexte en une seule passe.

Reprend Docling plutôt que PDFPlumberLoader (utilisé par agent_standardisation.extraire_texte
pour les PDF courts) : Docling détecte la vraie structure (titres, tableaux, hiérarchie),
utile pour découper aux bonnes frontières (par section, jamais en plein milieu d'un tableau).

Reprend d'un même dossier temporaire PAR DOCUMENT (pas partagé) : permet de reprendre un
traitement interrompu (crash, plantage réseau, arrêt manuel) sans perdre les lots déjà faits,
et sans risque de mélanger les lots de deux documents différents traités à des moments
différents.

Usage : python rag/standardiser_document.py <chemin_document> <chemin_sortie_txt>
"""
import os
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TORCHDYNAMO_DISABLE"] = "1"  # voir le commentaire équivalent dans les autres scripts rag/

import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from docling.document_converter import DocumentConverter

from agent_standardisation import standardiser_texte

BATCH_SIZE = 3000
CONCURRENCE_MAX = 4

# Détecte une table des matières via son signal le plus fiable : des points de suite ("....")
# entre le titre et le numéro de page. Délibérément PAS "dernière colonne = un nombre seul" —
# testé en réel que ce critère plus large signale à tort de vrais tableaux de données (ex :
# délais de livraison fournisseurs), perdant leur contenu silencieusement.
MOTIF_LIGNE_TDM = re.compile(r"^\|.*\.{4,}.*\|\s*\d{1,4}\s*\|$")


def _est_bloc_tdm(bloc: str) -> bool:
    lignes = bloc.strip().splitlines()
    lignes_tdm = [l for l in lignes if MOTIF_LIGNE_TDM.match(l.strip())]
    return len(lignes) > 0 and len(lignes_tdm) / len(lignes) > 0.5


# Découpe le markdown Docling par titres de section ("## ") — respecte la structure réelle du
# document plutôt qu'un découpage par nombre de caractères aveugle. Filtre les tables des
# matières (aucune info utile, juste du bruit pour l'agent).
def decouper_en_unites(markdown: str) -> list[str]:
    blocs = re.split(r"\n(?=## )", markdown)
    return [b.strip() for b in blocs if b.strip() and not _est_bloc_tdm(b)]


# Regroupe les unités (sections) en lots d'environ BATCH_SIZE caractères — chaque lot est un
# appel LLM séparé, donc jamais assez long pour déclencher la perte de contenu par résumé
# implicite (voir le commentaire en tête de fichier). Une unité seule plus grande que
# BATCH_SIZE forme son propre lot (jamais coupée en plein milieu d'une section).
def regrouper_en_lots(unites: list[str]) -> list[str]:
    lots, lot_courant = [], ""
    for unite in unites:
        if lot_courant and len(lot_courant) + len(unite) > BATCH_SIZE:
            lots.append(lot_courant)
            lot_courant = unite
        else:
            lot_courant = f"{lot_courant}\n\n{unite}" if lot_courant else unite
    if lot_courant:
        lots.append(lot_courant)
    return lots


# Traite UN lot : passe (skip) s'il a déjà été standardisé lors d'une exécution précédente
# (reprise après interruption), sinon appelle l'agent et sauvegarde immédiatement le résultat —
# pas seulement en mémoire, pour que la reprise fonctionne même après un crash en plein milieu.
def traiter_lot(indice: int, lot: str, dossier_temp: Path) -> str:
    chemin_sortie_lot = dossier_temp / f"lot_{indice:03d}.txt"
    if chemin_sortie_lot.exists():
        return chemin_sortie_lot.read_text(encoding="utf-8")
    resultat = standardiser_texte(lot)
    chemin_sortie_lot.write_text(resultat, encoding="utf-8")
    return resultat


def main(chemin_document: str, chemin_sortie: str) -> None:
    print(f"Docling : extraction de {chemin_document}...")
    document = DocumentConverter().convert(chemin_document).document
    markdown = document.export_to_markdown()

    unites = decouper_en_unites(markdown)
    lots = regrouper_en_lots(unites)
    print(f"  {len(unites)} unité(s) -> {len(lots)} lot(s) d'environ {BATCH_SIZE} caractères.")

    # Dossier temporaire PAR DOCUMENT (nom dérivé du fichier source) — voir le commentaire en
    # tête de fichier sur la reprise après interruption.
    nom_document = Path(chemin_document).stem
    dossier_temp = Path(chemin_sortie).parent / f".lots_temp_{nom_document}"
    dossier_temp.mkdir(exist_ok=True)

    print(f"Standardisation de {len(lots)} lot(s) (jusqu'à {CONCURRENCE_MAX} en parallèle)...")
    with ThreadPoolExecutor(max_workers=CONCURRENCE_MAX) as executeur:
        resultats = list(executeur.map(
            lambda paire: traiter_lot(paire[0], paire[1], dossier_temp),
            enumerate(lots),
        ))

    resultat_final = "\n\n".join(resultats)
    Path(chemin_sortie).write_text(resultat_final, encoding="utf-8")
    print(f"  -> {chemin_sortie} ({len(resultat_final)} caractères produits)")

    # Nettoyage des lots temporaires UNIQUEMENT après succès complet — sinon une interruption
    # juste après cette ligne perdrait la possibilité de reprendre.
    for fichier_lot in dossier_temp.glob("lot_*.txt"):
        fichier_lot.unlink()
    dossier_temp.rmdir()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage : python rag/standardiser_document.py <chemin_document> <chemin_sortie_txt>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
