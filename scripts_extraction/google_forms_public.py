# sys permet de lire le lien donné dans le terminal.
import sys

# json permet de transformer le texte interne de Google Forms en données Python.
import json

# re permet de chercher la variable qui contient les données du formulaire dans le HTML.
import re

# urllib.request permet de télécharger la page HTML du formulaire public,
# ainsi que les images des questions (des URLs publiques, sans authentification).
import urllib.request
import urllib.error

# Path permet de construire le chemin du dossier où les images sont téléchargées.
from pathlib import Path

# On réutilise notre fonction qui transforme un formulaire brut en formulaire standard.
from extraction_questions import extraire_formulaire


# Dossier où les images des questions sont téléchargées avant d'être passées à l'OCR.
# Chemin RELATIF (pas de .resolve()) volontairement : un chemin absolu propre à une machine
# précise (ex : "/home/hind/...") ne veut plus rien dire une fois le JSON utilisé ailleurs
# (autre machine, serveur). Même convention que ocr_utils.py, où "image_utilisee" est déjà
# relatif — les scripts sont censés être lancés depuis la racine du projet.
DOSSIER_IMAGES_TELECHARGEES = Path("scripts_extraction/images_formulaires")


# Cette fonction télécharge le HTML du formulaire public.
def telecharger_html(url):
    # On ajoute un User-Agent pour se présenter comme un navigateur simple.
    requete = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )
    # On ouvre le lien et on lit le HTML retourné par Google Forms.
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            return reponse.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as erreur:
        # Un 401 sur un formulaire "public" a une cause très probable et bien connue :
        # Google exige que tout le monde soit connecté dès qu'un formulaire contient une
        # question de type "dépôt de fichier", même pour juste consulter la page — ce
        # réglage ne peut pas être désactivé par le créateur du formulaire. Ce n'est donc
        # pas un bug de notre côté : ce formulaire est structurellement impossible à lire
        # sans être connecté.
        if erreur.code == 401:
            raise ValueError(
                "Accès refusé (401) pour ce formulaire. Cause la plus probable : ce "
                "formulaire contient une question de type dépôt de fichier, ce qui oblige "
                "Google à exiger une connexion pour voir la page, même en lecture seule. "
                "Ce cas ne peut pas être traité par le scraping public — voir "
                "project_notes/project_plan.md."
            ) from erreur

        raise ValueError(
            f"Impossible de télécharger le formulaire (erreur HTTP {erreur.code}) : {erreur}."
        ) from erreur


# Dossier où la session du navigateur connecté est sauvegardée sur le disque, pour ne pas
# avoir à se reconnecter à chaque exécution (même principe que le cache de jeton OAuth).
DOSSIER_SESSION_NAVIGATEUR = Path(__file__).resolve().parent / "session_navigateur_google"


# ATTENTION — NE FONCTIONNE PAS AVEC GOOGLE, gardé volontairement pour la documentation :
#
# Cette fonction devait télécharger le HTML d'un formulaire via un vrai navigateur
# automatisé (Playwright) connecté à un compte Google, pour contourner le blocage 401 des
# formulaires contenant une question de dépôt de fichier (voir telecharger_html).
#
# Testé en conditions réelles : Google détecte que la tentative de connexion vient d'un
# navigateur piloté automatiquement et la refuse ("Couldn't sign you in - This browser or
# app may not be secure"). C'est une mesure de sécurité anti-bot volontaire de Google.
#
# Décision : on n'a PAS cherché à contourner cette détection (fragile, contraire à l'esprit
# des conditions d'utilisation de Google, risque de blocage de compte). Un formulaire
# contenant une question de dépôt de fichier reste donc définitivement inaccessible par
# scraping automatisé — voir project_notes/project_plan.md pour la solution retenue
# (traitement manuel, ou demander l'accès éditeur au créateur du formulaire).
def telecharger_html_connecte(url):
    from playwright.sync_api import sync_playwright

    DOSSIER_SESSION_NAVIGATEUR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        # launch_persistent_context garde la session (cookies, connexion) sur le disque
        # entre deux exécutions, comme le cache de jeton pour Google/Microsoft.
        # headless=False : la fenêtre reste visible, pour permettre la connexion manuelle.
        contexte = playwright.chromium.launch_persistent_context(
            str(DOSSIER_SESSION_NAVIGATEUR),
            headless=False,
        )

        page = contexte.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")

        html = page.content()

        # Si les données attendues ne sont pas trouvées, on suppose qu'une connexion
        # manuelle est nécessaire : on laisse la fenêtre ouverte et on attend que
        # l'utilisateur confirme dans le terminal une fois connecté et sur la bonne page.
        if "FB_PUBLIC_LOAD_DATA_" not in html:
            input(
                "Connecte-toi si nécessaire dans la fenêtre du navigateur ouverte, "
                "assure-toi d'être bien sur la page du formulaire, "
                "puis appuie sur Entrée ici pour continuer..."
            )
            html = page.content()

        contexte.close()

        return html


# Cette fonction récupère la variable FB_PUBLIC_LOAD_DATA_ dans le HTML.
def extraire_donnees_google_depuis_html(html):
    # Google Forms met souvent les données du formulaire dans cette variable JavaScript.
    resultat = re.search(
        r"var FB_PUBLIC_LOAD_DATA_ = (.*?);</script>",
        html,
        re.DOTALL
    )

    # Si la variable n’existe pas, on ne peut pas extraire le formulaire avec cette méthode.
    # C’est le signal le plus probable que Google a changé la structure de la page HTML.
    if not resultat:
        raise ValueError(
            "Impossible de trouver FB_PUBLIC_LOAD_DATA_ dans le HTML. "
            "Google a probablement changé la structure de la page, ou le lien ne pointe pas "
            "vers un formulaire public valide."
        )
    

    # Le contenu trouvé ressemble à du JSON, donc on le transforme en listes Python.
    try:
        return json.loads(resultat.group(1))
    except json.JSONDecodeError as erreur:
        # Le contenu trouvé n’est pas un JSON valide : le format interne a changé.
        raise ValueError(
            f"FB_PUBLIC_LOAD_DATA_ trouvé mais son contenu n’est pas un JSON valide ({erreur}). "
            "Google a probablement changé la structure interne des données."
        ) from erreur


# Cette fonction convertit le type numérique Google Forms vers notre type brut simple.
def convertir_type_google(type_google):
    # 0 correspond généralement à une réponse courte.
    if type_google == 0:
        return "text"

    # 1 correspond généralement à un paragraphe.
    if type_google == 1:
        return "text"

    # 2 correspond généralement à un choix unique avec boutons radio.
    if type_google == 2:
        return "radio"

    # 3 correspond généralement à une liste déroulante.
    # Même si l’affichage est différent, la réponse attendue reste une seule option.
    if type_google == 3:
        return "radio"

    # 4 correspond généralement à des cases à cocher.
    # L’utilisateur peut sélectionner plusieurs options.
    if type_google == 4:
        return "checkbox"

    # 5 correspond généralement à une échelle linéaire.
    if type_google == 5:
        return "echelle_lineaire"

    # 6 correspond généralement à une grille à choix unique.
    if type_google == 6:
        return "grille_choix_unique"

    # 7 correspond généralement à une grille à cases à cocher.
    if type_google == 7:
        return "grille_choix_multiple"

    # 9 correspond généralement à une date.
    if type_google == 9:
        return "date"

    # 10 correspond généralement à une heure.
    if type_google == 10:
        return "heure"

    # 18 correspond généralement à une notation.
    if type_google == 18:
        return "notation"

    # Si on ne connaît pas encore ce type, on garde une valeur inconnue.
    return "inconnu"


# Cette fonction extrait les options d’une question Google Forms si elles existent.
def extraire_options_google(question_google):
    # Les options sont souvent dans question_google[4][0][1].
    try:
        options_google = question_google[4][0][1]
    except (TypeError, IndexError):
        return []

    # Si Google ne donne pas d’options, on retourne une liste vide.
    if not options_google:
        return []

    # Chaque option Google est souvent une liste dont le premier élément est le texte.
    options = []

    # On parcourt les options récupérées depuis Google.
    for option in options_google:
        if not (isinstance(option, list) and option):
            continue

        # L'option "Autre" (texte libre) a toujours un texte vide (option[0]) en interne —
        # elle se reconnaît par un 1 à l'index 4, absent des options fixes normales (vérifié
        # en réel : ["", null, null, null, 1]). Sans ce cas, elle était silencieusement
        # ignorée, alors qu'un répondant réel peut la choisir.
        est_option_autre = len(option) >= 5 and option[4] == 1

        if option[0]:
            options.append(option[0])
        elif est_option_autre:
            options.append("Autre")

    # On retourne les options sous forme simple.
    return options


# Cette fonction extrait les lignes et colonnes d’une grille Google Forms.
# texte_question sert de secours pour une ligne au texte vide (vu en réel : une grille à une
# seule ligne où Google n'assigne aucun texte à cette ligne, le texte de la QUESTION elle-même
# servant visiblement de label côté affichage — sans ce secours, grille_lignes.texte violerait
# sa contrainte NOT NULL/non-vide en base).
def extraire_grille_google(question_google, texte_question=None):
    # Une grille Google contient plusieurs sous-questions : une par ligne.
    try:
        blocs_lignes_google = question_google[4]
    except (TypeError, IndexError) as erreur:
        raise ValueError(
            f"Structure de grille Google Forms inattendue : impossible de lire les lignes ({erreur})."
        ) from erreur

    # Si Google ne donne pas de lignes, la grille est vide.
    if not blocs_lignes_google:
        return None

    # Cette liste contiendra les lignes de la grille.
    lignes = []

    # Cette liste contiendra les colonnes de la grille.
    colonnes = []

    # On parcourt les lignes internes de Google Forms.
    for ordre_ligne, bloc_ligne in enumerate(blocs_lignes_google, start=1):
        # Le texte de la ligne est souvent dans bloc_ligne[3][0].
        try:
            texte_ligne = bloc_ligne[3][0]
        except (TypeError, IndexError) as erreur:
            raise ValueError(
                f"Structure de grille Google Forms inattendue à la ligne {ordre_ligne} : "
                f"impossible de lire son texte ({erreur})."
            ) from erreur

        # On ajoute la ligne dans notre format standard.
        lignes.append({
            "ordre": ordre_ligne,
            "texte": texte_ligne or texte_question or "Ligne sans titre"
        })

        # Les colonnes sont souvent répétées dans chaque ligne, dans bloc_ligne[1].
        colonnes_google = bloc_ligne[1]

        # On extrait les colonnes une seule fois. Pas de champ "ordre" ici (contrairement aux
        # lignes) : les colonnes d'une grille sont l'équivalent des options d'une question à
        # choix — leur ordre exact compte moins que celui des lignes, qui sont chacune une
        # sous-question à part entière (même raisonnement que pour les options).
        if not colonnes and colonnes_google:
            for colonne in colonnes_google:
                if isinstance(colonne, list) and colonne and colonne[0]:
                    colonnes.append({
                        "texte": colonne[0]
                    })

    # On retourne une structure à deux dimensions : lignes + colonnes.
    return {
        "lignes": lignes,
        "colonnes": colonnes
    }


# Cette fonction vérifie qu’un élément Google Forms est une vraie question,
# et pas un titre de section, une image décorative ou un saut de page.
# La plupart de ces éléments n’ont pas de bloc de type à l’index 3, MAIS pas tous :
# - type 8 : titre de section sans image (ex : "Section sans titre", "INFORMATIONS
#   GENERALES", trouvés sur un vrai questionnaire externe) — un vrai titre, mais aucune
#   réponse attendue.
# - type 11 : titre de section AVEC image (ex : "Week 8 — Due Date...", trouvé sur un
#   autre formulaire externe).
# - type 12 : bloc vidéo intégrée (YouTube), vérifié en réel (ex : "Votre réparateur à
#   domicile" avec une vidéo YouTube) — même problème que 8/11, un titre décoratif sans
#   réponse attendue, qui se faisait halluciner une fausse réponse par l'IA sans ce filtre.
# Les trois ont un type non-None tout en n’étant pas des questions — sans cette exclusion,
# ils se retrouvaient traités comme de fausses questions texte (parfois même "prêtes" à
# tort, avec le titre de section comme si c’était une vraie réponse texte attendue).
TYPES_GOOGLE_NON_QUESTIONS = {8, 11, 12}


def est_une_vraie_question(question_google) -> bool:
    if not (
        isinstance(question_google, list)
        and len(question_google) > 3
        and question_google[3] is not None
        and question_google[3] not in TYPES_GOOGLE_NON_QUESTIONS
    ):
        return False

    # Google réutilise aussi le type 6 (grille à choix unique) pour de simples titres de
    # section en gras (ex : "Section 1: Basic Information", parfois précédé d'un emoji), sans
    # aucune donnée de grille — vérifié en réel sur 6 titres de section consécutifs et sur un
    # texte informatif isolé ("Nous vous appellerons..."), tous avec question_google[4] à None.
    # Un vrai type 6 a toujours au moins une ligne dans [4] — sans cette exclusion, ces titres
    # se retrouvaient comptés comme de fausses questions "grille_manquante".
    if question_google[3] == 6 and question_google[4] is None:
        return False

    return True


# Cette fonction indique si une question Google est obligatoire.
# Le flag obligatoire (0 ou 1) se trouve à l’index 2 de chaque sous-question,
# dans question_google[4][0][2] pour une question simple. Pour une grille,
# question_google[4] contient une sous-question par ligne : on considère la
# grille obligatoire si au moins une de ses lignes l’est.
def question_est_obligatoire(question_google) -> bool:
    try:
        sous_questions = question_google[4]
    except (TypeError, IndexError):
        return False

    if not sous_questions:
        return False

    for sous_question in sous_questions:
        try:
            if sous_question[2] == 1:
                return True
        except (TypeError, IndexError):
            continue

    return False


# Une question à cases à cocher (checkbox) peut avoir une règle de validation qui limite
# le nombre de sélections. Repéré en réel : une question "Filière" avec des cases à cocher
# imposait "exactement 1" — donc fonctionnellement un choix unique, malgré des cases à cocher
# à l'écran. Sans cette détection, l'IA pourrait croire qu'elle peut cocher plusieurs options
# alors qu'une seule est acceptée. La règle est encodée dans question_google[4][0][4], sous
# la forme [[7, 204, ["1"]]] — 7 et 204 semblent être des codes internes Google pour "nombre
# de sélections", 204 signifiant "exactement" (constaté en réel, non documenté officiellement).
# On ne détecte QUE ce cas précis "exactement 1" : on n'a qu'un seul exemple vérifié, donc on
# ne généralise pas à "au moins N"/"au plus N" sans autre preuve concrète.
def question_checkbox_est_choix_unique(question_google) -> bool:
    try:
        regle_validation = question_google[4][0][4]
        code_type, code_sous_type, valeurs = regle_validation[0][:3]
        return code_type == 7 and code_sous_type == 204 and valeurs == ["1"]
    except (TypeError, IndexError, ValueError):
        return False


# Pour une grille, le type Google général (question_google[3]) ne suffit PAS à distinguer
# choix unique et cases à cocher par ligne : vérifié en réel sur un formulaire de test avec
# 4 grilles, les 4 avaient le même type général (7), qu'elles soient à choix unique (ronds ⊙)
# ou à cases à cocher (carrés ☑). Le vrai signal se trouve dans le dernier élément de chaque
# ligne (question_google[4][0][-1]) : [1] pour cases à cocher, TOUT LE RESTE pour choix unique
# — vérifié en réel avec une 3e valeur possible, [] (liste vide), rencontrée sur un formulaire
# où les 4 grilles étaient bien à choix unique (ronds ⊙) malgré ce indicateur différent de [0].
# On ne teste donc plus l'égalité stricte à [0], seulement l'absence de [1].
def grille_est_choix_unique(question_google) -> bool:
    try:
        indicateur = question_google[4][0][-1]
        return indicateur != [1]
    except (TypeError, IndexError):
        return False


# Quand le créateur du formulaire ne rédige pas de message d'erreur personnalisé, Google
# n'enregistre AUCUN message dans les données brutes (le message par défaut, ex : "Please
# enter a number greater than 12", est généré par le JavaScript de Google au moment de
# l'affichage — vérifié en réel, absent des données serveur). On reconstruit donc nous-mêmes
# un texte à partir des codes (catégorie, sous-type), mais UNIQUEMENT pour les combinaisons
# qu'on a réellement vues et vérifiées sur un vrai formulaire de test couvrant 20 règles —
# jamais de supposition sur une combinaison jamais rencontrée : mieux vaut renvoyer aucune
# contrainte que d'en inventer une fausse pour l'IA.
GENERATEURS_CONTRAINTE_GOOGLE = {
    (1, 1): lambda v: f"doit être un nombre supérieur à {v[0]}",
    (1, 2): lambda v: f"doit être un nombre supérieur ou égal à {v[0]}",
    (1, 3): lambda v: f"doit être un nombre inférieur à {v[0]}",
    (1, 4): lambda v: f"doit être un nombre inférieur ou égal à {v[0]}",
    (1, 5): lambda v: f"doit être un nombre égal à {v[0]}",
    (1, 6): lambda v: f"doit être un nombre différent de {v[0]}",
    (1, 7): lambda v: f"doit être un nombre entre {v[0]} et {v[1]}",
    (1, 8): lambda v: f"doit être un nombre en dehors de l'intervalle {v[0]} - {v[1]}",
    (1, 9): lambda v: "doit être un nombre entier",
    (1, 10): lambda v: "doit être un nombre",
    (2, 100): lambda v: f"doit contenir le texte : {v[0]}",
    (2, 101): lambda v: f"ne doit pas contenir le texte : {v[0]}",
    (2, 102): lambda v: "doit être une adresse e-mail valide",
    (2, 103): lambda v: "doit être une URL valide",
    (6, 202): lambda v: f"doit contenir au maximum {v[0]} caractères",
    (6, 203): lambda v: f"doit contenir au minimum {v[0]} caractères",
}


# Une question texte peut avoir une règle de validation de réponse (nombre, longueur de texte,
# expression régulière, e-mail, URL...), configurée par le créateur via "Validation des
# réponses" dans l'éditeur. On lit d'abord le message d'erreur personnalisé s'il existe
# (question_google[4][0][4][0][3], le plus fiable), sinon on retombe sur une reconstruction
# à partir des codes (voir GENERATEURS_CONTRAINTE_GOOGLE) — utile à l'IA : elle doit savoir
# qu'un format précis est attendu avant de générer une réponse, même sans message personnalisé.
def extraire_contrainte_google(question_google):
    try:
        regle_validation = question_google[4][0][4][0]
    except (TypeError, IndexError):
        return None

    # Message personnalisé écrit par le créateur : la source la plus fiable, on la privilégie.
    if len(regle_validation) > 3 and regle_validation[3]:
        return regle_validation[3]

    # Sinon, on tente une reconstruction à partir des codes, seulement si on la connaît déjà.
    try:
        categorie, sous_type, valeurs = regle_validation[0], regle_validation[1], regle_validation[2]
        generateur = GENERATEURS_CONTRAINTE_GOOGLE.get((categorie, sous_type))
        return generateur(valeurs) if generateur else None
    except (TypeError, IndexError):
        return None


# Cette fonction retrouve l’URL de l’image appartenant à UNE question précise.
#
# Important : l’identifiant d’image présent dans les données brutes (question_google[9])
# n’est PAS réutilisable pour construire une URL de téléchargement — on l’a vérifié en
# comparant avec le HTML réel. La seule façon fiable de récupérer l’image est de lire
# directement les balises <img> déjà présentes dans la page.
#
# Piège rencontré en conditions réelles : associer les images aux questions "dans l’ordre
# d’apparition dans la page" est FAUX — sur un vrai formulaire testé, l’ordre des images
# trouvées dans le HTML ne correspondait pas à l’ordre des questions (une image de
# décoration du thème du formulaire s’est retrouvée mélangée avec les vraies images de
# questions, et deux questions ont fini avec les images de l’autre). La méthode fiable :
# chercher l’image située juste après l’identifiant numérique de LA question elle-même
# dans le HTML (question_google[0]), puisque chaque question et son image sont rendues
# proches l’une de l’autre dans la page.
def trouver_url_image_pour_question(html, identifiant_google):
    position = html.find(str(identifiant_google))

    if position == -1:
        return None

    # On ne cherche que dans une fenêtre raisonnable après l’identifiant, pour éviter de
    # remonter accidentellement l’image d’une autre question plus loin dans la page.
    fenetre = html[position:position + 5000]

    # [^"\\ )] exclut aussi la parenthèse fermante : une vraie URL de ce type n’en contient
    # jamais, sa présence signale qu’on a dérivé dans un "background-image: url(...)" CSS.
    correspondance = re.search(
        r"https?://lh7-rt\.googleusercontent\.com/formsz/[^\"\\ )]*",
        fenetre
    )

    if not correspondance:
        return None

    url = correspondance.group()

    # Une vraie URL d’image de ce type dépasse rarement 400 caractères (constaté en
    # conditions réelles) : au-delà, c’est le signe que la regex a quand même dérivé.
    if len(url) > 400:
        return None

    return url


# Cette fonction vérifie si une question brute Google contient une image insérée
# par le créateur du formulaire (présente à l’index 9 des données de la question).
def question_a_une_image(question_google) -> bool:
    try:
        return bool(question_google[9])
    except (TypeError, IndexError):
        return False


# Cette fonction télécharge l’image d’une question et retourne son chemin local
# (ou None si le téléchargement échoue). Une image qui ne se télécharge pas ne doit
# jamais faire planter le reste de l’extraction du formulaire.
def telecharger_image_question(url_image, identifiant):
    if not url_image:
        return None

    DOSSIER_IMAGES_TELECHARGEES.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_IMAGES_TELECHARGEES / f"{identifiant}.png"

    requete = urllib.request.Request(
        url_image,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            chemin.write_bytes(reponse.read())
    except Exception as erreur:
        print(
            f"Avertissement : impossible de télécharger l’image de la question "
            f"{identifiant} : {erreur}",
            file=sys.stderr
        )
        return None

    return str(chemin)


# Cette fonction transforme une question Google Forms en question brute de notre pipeline.
# url_image est l’URL de l’image associée à cette question, déjà repérée dans le HTML
# (ou None si la question n’a pas d’image).
def convertir_question_google(question_google, url_image=None):
    # Vérifie que la structure minimale attendue est présente avant d’indexer quoi que ce soit.
    if not isinstance(question_google, list) or len(question_google) < 4:
        raise ValueError(
            "Structure de question Google Forms inattendue : moins de 4 éléments trouvés. "
            "Google a peut-être changé le format de la page."
        )

    # Le texte de la question est généralement dans question_google[1]. On retire les
    # espaces en trop en début/fin : certains créateurs de formulaire en laissent par erreur
    # (vu en réel : "  Sélectionnez le(s) poste(s)...  "), sans que ça ait de sens à garder.
    texte = question_google[1].strip() if question_google[1] else question_google[1]

    # Le type Google est généralement dans question_google[3].
    type_google = question_google[3]

    # On convertit le type Google vers notre type brut : text, radio, checkbox...
    type_brut = convertir_type_google(type_google)

    # Une question à cases à cocher peut en réalité n'accepter qu'une seule réponse si le
    # créateur a fixé la validation "exactement 1" (voir question_checkbox_est_choix_unique).
    if type_brut == "checkbox" and question_checkbox_est_choix_unique(question_google):
        type_brut = "radio"

    # Une grille détectée comme "cases à cocher" est en réalité à choix unique si l'indicateur
    # de ligne le confirme (voir grille_est_choix_unique) : le type général de Google Forms ne
    # suffit pas à distinguer les deux pour les grilles.
    if type_brut == "grille_choix_multiple" and grille_est_choix_unique(question_google):
        type_brut = "grille_choix_unique"

    # On récupère les options si la question en contient.
    options = extraire_options_google(question_google)

    # On récupère la grille si la question est une grille.
    if type_brut in ["grille_choix_multiple", "grille_choix_unique"]:
        grille = extraire_grille_google(question_google)
    else:
        grille = None

    # Si une image a été repérée pour cette question, on la télécharge.
    # question_google[0] est l’identifiant numérique de la question, utilisé comme
    # nom de fichier pour garder un chemin stable et lisible.
    image = telecharger_image_question(url_image, identifiant=question_google[0])

    # On récupère si la question est obligatoire (astérisque rouge sur le vrai formulaire).
    obligatoire = question_est_obligatoire(question_google)

    # On récupère une éventuelle contrainte de validation (nombre, longueur, e-mail, URL...).
    contrainte = extraire_contrainte_google(question_google) if type_brut == "text" else None

    # On retourne une question brute compatible avec notre extracteur existant.
    return {
        "texte": texte,
        "type_brut": type_brut,
        "options": options,
        "grille": grille,
        "image": image,
        "obligatoire": obligatoire,
        "contrainte": contrainte
    }


# Cette fonction transforme les données Google Forms en formulaire brut.
# html est le HTML brut de la page, nécessaire pour y repérer les URLs d’images
# (voir trouver_url_image_pour_question).
def convertir_formulaire_google(donnees_google, url, html):
    # Vérifie que le bloc principal attendu existe avant d’aller plus loin.
    if not isinstance(donnees_google, list) or len(donnees_google) < 2:
        raise ValueError(
            "Structure Google Forms inattendue : le bloc principal (index 1) est absent. "
            "Google a probablement changé le format de la page."
        )

    # Dans les formulaires testés, les informations principales sont dans donnees_google[1].
    bloc_formulaire = donnees_google[1]

    # Vérifie qu’on peut bien retrouver le titre (index 8) et les questions (index 1).
    if not isinstance(bloc_formulaire, list) or len(bloc_formulaire) < 9:
        raise ValueError(
            "Structure Google Forms inattendue : bloc_formulaire ne contient pas assez "
            "d’éléments pour retrouver le titre et les questions. "
            "Google a probablement changé le format de la page."
        )

    # Le titre visible du formulaire est généralement dans bloc_formulaire[8] — vide (None)
    # quand le créateur n'a jamais nommé son formulaire (vérifié en réel). Google affiche alors
    # "Formulaire sans titre" dans la vraie balise <title> de la page — on reprend ce même texte
    # par défaut, plutôt que de laisser une valeur vide qui prêterait à confusion plus tard.
    titre = bloc_formulaire[8] or "Formulaire sans titre"

    # La description est généralement dans bloc_formulaire[0].
    description = bloc_formulaire[0]

    # Les questions sont généralement dans bloc_formulaire[1].
    questions_google = bloc_formulaire[1]

    if not isinstance(questions_google, list):
        raise ValueError(
            "Structure Google Forms inattendue : la liste de questions (bloc_formulaire[1]) "
            "n’est pas une liste. Google a probablement changé le format de la page."
        )

    # On écarte les éléments qui ne sont pas de vraies questions
    # (titres de section, sauts de page, images décoratives...).
    questions_google = [
        question_google
        for question_google in questions_google
        if est_une_vraie_question(question_google)
    ]

    # On convertit chaque question Google vers notre format brut.
    # Si un élément a une structure vraiment inattendue, on échoue avec un message clair
    # plutôt que de laisser une erreur Python cryptique remonter (IndexError, TypeError...).
    questions_brutes = []

    for position, question_google in enumerate(questions_google, start=1):
        # Détermine l’URL d’image à associer à cette question, s’il y en a une, en
        # cherchant directement autour de l’identifiant de CETTE question dans le HTML
        # (voir trouver_url_image_pour_question : associer par ordre d’apparition globale
        # dans la page ne fonctionne pas de façon fiable).
        url_image = None

        if question_a_une_image(question_google):
            url_image = trouver_url_image_pour_question(html, question_google[0])

        try:
            questions_brutes.append(convertir_question_google(question_google, url_image))
        except (TypeError, IndexError, ValueError) as erreur:
            raise ValueError(
                f"Impossible de lire la question numéro {position} du formulaire : {erreur} "
                "Google a probablement changé le format de la page."
            ) from erreur

    # On construit le formulaire brut compatible avec extraire_formulaire.
    return {
        "source": {
            "type": "google_forms_public",
            "url": url
        },
        "titre": titre,
        "description": description,
        "questions": questions_brutes
    }


# Cette fonction fait tout le pipeline depuis un lien Google Forms public.
def extraire_formulaire_google_public(url):
    # On télécharge le HTML du formulaire.
    html = telecharger_html(url)

    # On extrait les données internes de Google Forms.
    donnees_google = extraire_donnees_google_depuis_html(html)

    # On transforme les données Google en formulaire brut.
    formulaire_brut = convertir_formulaire_google(donnees_google, url, html)

    # On transforme le formulaire brut en JSON standard.
    return extraire_formulaire(formulaire_brut)


# Cette fonction fait le même pipeline, mais avec un navigateur connecté (voir
# telecharger_html_connecte). À utiliser quand extraire_formulaire_google_public échoue
# avec une erreur 401 (formulaire contenant probablement une question de dépôt de fichier).
def extraire_formulaire_google_public_connecte(url):
    html = telecharger_html_connecte(url)

    donnees_google = extraire_donnees_google_depuis_html(html)

    formulaire_brut = convertir_formulaire_google(donnees_google, url, html)

    return extraire_formulaire(formulaire_brut)


# Cette partie s’exécute seulement si on lance ce fichier directement dans le terminal.
if __name__ == "__main__":
    # Si aucun lien n’est donné, on explique comment utiliser le script.
    if len(sys.argv) < 2:
        print(
            "Utilisation : python scripts_extraction/google_forms_public.py URL_DU_FORMULAIRE "
            "[--connecte]"
        )
        print(
            "--connecte : tentative via navigateur connecté (Google bloque cette approche "
            "pour les formulaires avec dépôt de fichier, voir telecharger_html_connecte)."
        )
        sys.exit(1)

    # Le lien du formulaire est le premier argument après le nom du fichier.
    url_formulaire = sys.argv[1]

    # Si --connecte est passé en deuxième argument, on utilise la version avec navigateur.
    if "--connecte" in sys.argv[2:]:
        resultat = extraire_formulaire_google_public_connecte(url_formulaire)
    else:
        # On lance l’extraction complète (version anonyme, sans connexion).
        resultat = extraire_formulaire_google_public(url_formulaire)

    # On affiche le résultat en JSON lisible.
    print(json.dumps(resultat, indent=2, ensure_ascii=False))
