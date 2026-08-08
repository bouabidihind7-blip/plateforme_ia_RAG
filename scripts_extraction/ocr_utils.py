from pathlib import Path

import cv2
import easyocr
import numpy as np


# On garde le lecteur EasyOCR en mémoire pour éviter de recharger le modèle à chaque appel.
_reader = None

# Si la première passe (rapide) atteint déjà ce score, on ne teste pas les variantes coûteuses.
SEUIL_SCORE_SUFFISANT = 0.85

# En dessous de ce score après la passe rapide, on tente les variantes coûteuses (x4...) :
# on a des chances réelles d'améliorer le résultat. Au-dessus, d'après nos tests
# (test1/test2/test3 dans images_test/), les variantes coûteuses n'apportent quasiment
# jamais de gain : le résultat de la passe rapide était déjà la meilleure variante trouvée
# même après avoir tout testé, donc les tester coûte du temps pour rien. Le résultat sera
# de toute façon signalé pour validation humaine s'il ne dépasse pas SEUIL_SCORE_SUFFISANT.
SEUIL_TENTATIVE_VARIANTES_COUTEUSES = 0.55


def obtenir_reader(gpu: bool = False):
    # On utilise une variable globale pour réutiliser le même lecteur EasyOCR.
    global _reader

    # Si le lecteur n’existe pas encore, on le crée.
    if _reader is None:
        _reader = easyocr.Reader(["fr", "en"], gpu=gpu)

    # Si le lecteur existe déjà, on le retourne directement.
    return _reader


def corriger_inclinaison(image_gris):
    # Inverse les couleurs pour rendre les zones de texte plus faciles à détecter.
    inverse = cv2.bitwise_not(image_gris)

    # Transforme l’image inversée en noir/blanc pour repérer les pixels du texte.
    seuil = cv2.threshold(
        inverse,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    # Trouve les coordonnées des pixels blancs détectés.
    coords = cv2.findNonZero(seuil)

    # Si aucun pixel utile n’est trouvé, on retourne l’image sans modification.
    if coords is None:
        return image_gris

    # Calcule l’angle du plus petit rectangle qui contient le texte détecté.
    angle = cv2.minAreaRect(coords)[-1]

    # Corrige la valeur de l’angle selon la convention utilisée par OpenCV.
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Si l’image est presque droite, on évite de la modifier inutilement.
    if abs(angle) < 0.5:
        return image_gris

    # Récupère la hauteur et la largeur de l’image.
    hauteur, largeur = image_gris.shape[:2]

    # Calcule le centre de l’image pour faire la rotation autour du centre.
    centre = (largeur // 2, hauteur // 2)

    # Crée la matrice mathématique qui décrit la rotation à appliquer.
    matrice = cv2.getRotationMatrix2D(centre, angle, 1.0)

    # Applique la rotation et retourne l’image redressée.
    return cv2.warpAffine(
        image_gris,
        matrice,
        (largeur, hauteur),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )


def isoler_texte_par_luminosite(image_gris, texte_clair: bool):
    # Transforme l’image en noir/blanc avec un seuil automatique.
    seuil = cv2.threshold(
        image_gris,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    # Si le texte est clair sur un fond sombre, on inverse le résultat.
    if texte_clair:
        seuil = cv2.bitwise_not(seuil)

    return seuil


def _sauver(dossier_sortie: Path, nom_image: str, image_preparee, suffixe: str, chemins: list):
    # Prépare le chemin de sortie avec un suffixe clair.
    chemin = dossier_sortie / f"{nom_image}_{suffixe}.png"

    # Enregistre l’image préparée sur le disque.
    cv2.imwrite(str(chemin), image_preparee)

    # Ajoute cette version dans la liste des images à tester.
    chemins.append(str(chemin))

    # Retourne l’image pour pouvoir continuer les traitements dessus.
    return image_preparee


def preparer_contexte_pretraitement(chemin_image: str):
    # Lit l’image avec OpenCV.
    image = cv2.imread(chemin_image)

    # Si l’image n’est pas lisible, on ne peut rien préparer.
    if image is None:
        return None

    # Crée le dossier où on va enregistrer les versions préparées.
    dossier_sortie = Path("scripts_extraction/images_test/pretraitements")
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    # Récupère le nom de l’image sans extension.
    nom_image = Path(chemin_image).stem

    # Cette liste contient les versions rapides : celles qu’on teste toujours en premier.
    chemins_rapides = [chemin_image]

    def sauver(image_preparee, suffixe: str):
        return _sauver(dossier_sortie, nom_image, image_preparee, suffixe, chemins_rapides)

    # Convertit l’image couleur en niveaux de gris.
    gris = sauver(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), "gris")

    # Réduit le bruit avant le seuillage.
    debruite = sauver(cv2.fastNlMeansDenoising(gris, h=10), "debruite")

    # Redresse l’image si le texte est légèrement incliné.
    redresse = sauver(corriger_inclinaison(debruite), "redresse")

    # Améliore le contraste localement avec CLAHE.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    # Rend les lettres un peu plus nettes.
    noyau_nettete = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0]
    ])

    # Passe rapide : seulement le facteur x2, avec les prétraitements les plus fiables.
    # x4 et les variantes de luminosité/netteté sont coûteux et souvent redondants,
    # donc on ne les calcule que si cette passe rapide ne suffit pas.
    agrandie_x2 = sauver(
        cv2.resize(
            redresse,
            None,
            fx=2,
            fy=2,
            interpolation=cv2.INTER_LANCZOS4
        ),
        "agrandie_x2"
    )

    contraste_x2 = sauver(clahe.apply(agrandie_x2), "contraste_x2")

    sauver(
        cv2.threshold(
            contraste_x2,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1],
        "otsu_x2"
    )

    sauver(
        cv2.adaptiveThreshold(
            contraste_x2,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15
        ),
        "adaptatif_x2"
    )

    # Ce contexte contient tout ce qu’il faut pour préparer les variantes supplémentaires
    # plus tard, sans refaire le gris/débruitage/redressement depuis le début.
    return {
        "chemins_rapides": chemins_rapides,
        "dossier_sortie": dossier_sortie,
        "nom_image": nom_image,
        "redresse": redresse,
        "contraste_x2": contraste_x2,
        "clahe": clahe,
        "noyau_nettete": noyau_nettete,
    }


def creer_versions_supplementaires(contexte: dict) -> list:
    # Variantes plus coûteuses (luminosité, netteté, inversion, agrandissement x4).
    # On ne les calcule que si la passe rapide n’a pas donné un score suffisant.
    dossier_sortie = contexte["dossier_sortie"]
    nom_image = contexte["nom_image"]
    redresse = contexte["redresse"]
    contraste_x2 = contexte["contraste_x2"]
    clahe = contexte["clahe"]
    noyau_nettete = contexte["noyau_nettete"]

    chemins = []

    def sauver(image_preparee, suffixe: str):
        return _sauver(dossier_sortie, nom_image, image_preparee, suffixe, chemins)

    # Recalcule le seuillage Otsu du x2 pour en tirer les variantes de luminosité et l’inversion.
    otsu_x2 = cv2.threshold(
        contraste_x2,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    # Isole les cas où le texte est clair sur un fond sombre (x2).
    sauver(isoler_texte_par_luminosite(contraste_x2, texte_clair=True), "clair_sur_sombre_x2")

    # Isole les cas où le texte est sombre sur un fond clair (x2).
    sauver(isoler_texte_par_luminosite(contraste_x2, texte_clair=False), "sombre_sur_clair_x2")

    # Rend les lettres un peu plus nettes (x2).
    sauver(cv2.filter2D(contraste_x2, -1, noyau_nettete), "nette_x2")

    # Inverse la version Otsu (x2).
    sauver(cv2.bitwise_not(otsu_x2), "inverse_x2")

    # x4 aide surtout le texte très petit ; c’est la variante la plus coûteuse,
    # donc elle reste réservée aux cas où la passe rapide échoue.
    agrandie_x4 = sauver(
        cv2.resize(
            redresse,
            None,
            fx=4,
            fy=4,
            interpolation=cv2.INTER_LANCZOS4
        ),
        "agrandie_x4"
    )

    contraste_x4 = sauver(clahe.apply(agrandie_x4), "contraste_x4")

    otsu_x4 = sauver(
        cv2.threshold(
            contraste_x4,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1],
        "otsu_x4"
    )

    sauver(
        cv2.adaptiveThreshold(
            contraste_x4,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            15
        ),
        "adaptatif_x4"
    )

    sauver(isoler_texte_par_luminosite(contraste_x4, texte_clair=True), "clair_sur_sombre_x4")
    sauver(isoler_texte_par_luminosite(contraste_x4, texte_clair=False), "sombre_sur_clair_x4")
    sauver(cv2.filter2D(contraste_x4, -1, noyau_nettete), "nette_x4")
    sauver(cv2.bitwise_not(otsu_x4), "inverse_x4")

    return chemins


def lire_image_avec_easyocr(reader, chemin_image: str) -> dict:
    # Lit l’image avec EasyOCR et retourne les morceaux de texte détectés.
    resultats = reader.readtext(
        chemin_image,
        detail=1,
        paragraph=False,
        contrast_ths=0.1,
        adjust_contrast=0.5,
        text_threshold=0.6,
        low_text=0.35,
        # Certaines images (ex : jauges, schémas) contiennent du texte tourné à 90°/180°/270°
        # à côté de texte horizontal (ex : "LOW"/"HIGH" verticaux autour d'un cadran "CORTISOL"
        # horizontal). Sans ça, EasyOCR ne teste que l'orientation horizontale et rate ce texte.
        # Testé en réel : coût de temps modeste (+44% sur un cas), capture du texte en plus.
        rotation_info=[90, 180, 270],
    )

    # Si aucun texte n’est détecté, on retourne un résultat vide.
    if not resultats:
        return {
            "texte_extrait": "",
            "score_confiance": 0,
            "nb_mots": 0,
            "erreur": "Aucun texte détecté dans l'image",
            "image_utilisee": chemin_image
        }

    textes = []
    scores = []

    # Chaque résultat contient : position du texte, texte détecté, score de confiance.
    for resultat in resultats:
        texte = resultat[1]
        score = resultat[2]

        textes.append(texte)
        scores.append(score)

    # Assemble tous les morceaux détectés dans une seule phrase.
    texte_final = " ".join(textes)

    # Calcule la confiance moyenne.
    score_moyen = sum(scores) / len(scores)

    return {
        "texte_extrait": texte_final,
        "score_confiance": score_moyen,
        "nb_mots": len(textes),
        "erreur": None,
        "image_utilisee": chemin_image
    }


def calculer_score_pondere(resultat: dict) -> float:
    # Compte le nombre de caractères extraits.
    nb_caracteres = len(resultat["texte_extrait"])

    # Si aucun texte n’est extrait, le résultat ne vaut rien.
    if nb_caracteres == 0:
        return 0

    # Donne un petit bonus aux résultats qui contiennent plus de texte.
    bonus_longueur = min(nb_caracteres / 50, 1.0)

    # Combine la confiance OCR et la quantité de texte détecté.
    return resultat["score_confiance"] * (0.7 + 0.3 * bonus_longueur)


def tester_variantes(
    reader,
    chemins_images: list,
    meilleur_resultat=None,
    meilleur_score: float = -1,
    seuil_arret: float = None,
):
    # Teste OCR sur chaque chemin donné et garde le meilleur résultat rencontré,
    # y compris un éventuel meilleur résultat déjà trouvé lors d’une passe précédente.
    for chemin in chemins_images:
        resultat = lire_image_avec_easyocr(reader, chemin)

        # Calcule un score qui tient compte de la confiance et de la quantité de texte.
        score = calculer_score_pondere(resultat)

        # Si ce résultat est meilleur que les précédents, on le garde.
        if score > meilleur_score:
            meilleur_score = score
            meilleur_resultat = resultat

        # Si un seuil d’arrêt est fourni et que la confiance brute (pas le score pondéré,
        # voir extraire_texte_image) l’a déjà atteint, inutile de tester les variantes
        # restantes : on gagne du temps sans perdre en fiabilité sur les cas déjà résolus.
        if seuil_arret is not None and meilleur_resultat["score_confiance"] >= seuil_arret:
            break

    return meilleur_resultat, meilleur_score


def extraire_texte_image(chemin_image: str, gpu: bool = False) -> dict:
    # Récupère le lecteur EasyOCR sans le recréer à chaque fois.
    reader = obtenir_reader(gpu=gpu)

    # Prépare les versions rapides de l’image (et garde le contexte pour la suite si besoin).
    contexte = preparer_contexte_pretraitement(chemin_image)

    # Si l’image n’est pas lisible, on tente quand même l’OCR sur le fichier original.
    if contexte is None:
        return lire_image_avec_easyocr(reader, chemin_image)

    # Teste d’abord seulement les variantes rapides (original, gris, débruitée, redressée, x2).
    meilleur_resultat, meilleur_score = tester_variantes(reader, contexte["chemins_rapides"])

    # Si ce premier résultat est déjà suffisamment bon, on s’arrête ici :
    # ça évite de calculer et de tester les variantes coûteuses (x4, netteté, inversion...).
    # Important : on compare la confiance brute d’EasyOCR, pas le score pondéré.
    # Le score pondéré pénalise les textes courts (bonus de longueur), donc une question
    # courte mais lue avec une très bonne confiance ne devrait pas être considérée incertaine.
    if meilleur_resultat["score_confiance"] >= SEUIL_SCORE_SUFFISANT:
        return meilleur_resultat

    # Si la passe rapide a déjà donné un résultat raisonnable, ce n’est pas la peine
    # de tenter les variantes coûteuses : le gain est presque toujours nul, et le résultat
    # sera signalé pour validation humaine de toute façon (voir extraction_questions.py).
    # On ne tente les variantes coûteuses que quand la passe rapide a vraiment échoué.
    if meilleur_resultat["score_confiance"] >= SEUIL_TENTATIVE_VARIANTES_COUTEUSES:
        return meilleur_resultat

    # Sinon, on prépare et on teste les variantes supplémentaires plus coûteuses.
    # On garde le même seuil d’arrêt ici : dès qu’une variante coûteuse atteint une
    # confiance suffisante, on arrête sans tester les variantes x4 restantes.
    chemins_supplementaires = creer_versions_supplementaires(contexte)

    meilleur_resultat, meilleur_score = tester_variantes(
        reader,
        chemins_supplementaires,
        meilleur_resultat,
        meilleur_score,
        seuil_arret=SEUIL_SCORE_SUFFISANT
    )

    return meilleur_resultat
