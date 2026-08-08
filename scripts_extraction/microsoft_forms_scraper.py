# Ce fichier lit un formulaire Microsoft Forms en chargeant sa page publique dans un vrai
# navigateur automatisé (Playwright), puis en lisant directement le HTML affiché — au lieu
# d'appeler une API cachée (piste explorée puis abandonnée : endpoint non documenté,
# nécessite un tenant Azure et une inscription d'application, jamais fonctionnel).
#
# Gros avantage de cette approche : aucune authentification OAuth/Azure nécessaire.
# On charge la page comme le ferait n'importe quel visiteur avec le lien public.
#
# Microsoft Forms affiche discrètement le type de chaque question dans un texte caché aux
# yeux (mais lu par les lecteurs d'écran, pour l'accessibilité) juste après son titre —
# par exemple "Single line text.", "Date.", "Single choice.", "Ranking.", "Net Promoter
# Score." On s'appuie sur ce texte pour déterminer le type de chaque question de façon
# fiable, plutôt que de deviner à partir de la structure HTML brute.

import re
import sys
import json
import urllib.request

from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from extraction_questions import extraire_formulaire


# Même dossier que google_forms_public.py : pas besoin de deux emplacements différents
# pour stocker les images téléchargées depuis les formulaires (dossier gitignored).
# Chemin RELATIF (pas de .resolve()) volontairement, même raison que google_forms_public.py :
# un chemin absolu propre à cette machine ne veut plus rien dire ailleurs.
DOSSIER_IMAGES_TELECHARGEES = Path("scripts_extraction/images_formulaires")


# Cette fonction télécharge l'image d'une question et retourne son chemin local (ou None
# si le téléchargement échoue). Testé en réel : l'URL Microsoft (hive.forms.usercontent.
# microsoft/images/...) se télécharge sans authentification, avec un simple User-Agent —
# comme pour Google Forms, une image qui ne se télécharge pas ne doit jamais faire planter
# le reste de l'extraction du formulaire.
def telecharger_image_question(url_image: str, identifiant: str):
    if not url_image:
        return None

    DOSSIER_IMAGES_TELECHARGEES.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER_IMAGES_TELECHARGEES / f"{identifiant}.png"

    requete = urllib.request.Request(
        url_image,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            chemin.write_bytes(reponse.read())
    except Exception as erreur:
        print(
            f"Avertissement : impossible de télécharger l'image de la question "
            f"{identifiant} : {erreur}",
            file=sys.stderr
        )
        return None

    return str(chemin)


# Cette fonction retrouve l'identifiant stable d'une question. Il n'est PAS sur le bloc
# "questionItem" lui-même (qui n'a pas d'attribut id), mais sur un élément imbriqué dont
# l'id commence par "QuestionId_".
def extraire_id_question(bloc_question) -> str:
    element_id = bloc_question.find(id=re.compile(r"^QuestionId_"))

    return element_id.get("id") if element_id else None


# Un formulaire Microsoft Forms peut être découpé en plusieurs sections ("pages"), et
# Microsoft bloque le passage à la section suivante tant que les questions obligatoires
# de la section actuelle n'ont pas de réponse (message affiché : "X question(s) need to
# be completed before going to next page"). On doit donc remplir des réponses factices
# pour avancer et voir les sections suivantes — ces réponses ne sont JAMAIS soumises,
# on ne clique jamais sur le bouton final "Submit".
# Cette fonction essaie plusieurs façons de répondre à une question, une par une, selon
# ce qu'elle trouve dans son type de champ (texte, choix, échelle, notation, classement...).
def remplir_reponse_factice(bloc_question) -> None:
    # Un champ texte peut avoir une règle de validation de contenu (ex : "le texte doit
    # contenir tel mot"), en plus du simple "obligatoire". Repéré en réel : un message
    # d'erreur "Please enter text that contains adi" affiché À L'INTÉRIEUR du bloc de la
    # question concernée (vérifié : jamais dans le bloc d'une autre question). Sans cette
    # détection, remplir toujours "test" échoue indéfiniment sur ce genre de champ, et le
    # parcours du formulaire reste bloqué sur cette section pour toujours. On adapte donc
    # la valeur factice pour satisfaire cette contrainte précise quand elle est détectée.
    valeur_texte_factice = "test"
    alerte_validation = bloc_question.locator('[role="alert"]')
    if alerte_validation.count() > 0:
        message_erreur = alerte_validation.first.text_content() or ""
        correspondance = re.search(r"contains (\w+)", message_erreur, re.IGNORECASE)
        if correspondance:
            valeur_texte_factice = f"test {correspondance.group(1)}"

    # On essaie chaque méthode dans un délai court : le but est juste de satisfaire la
    # validation "obligatoire" pour avancer, pas d'obtenir une réponse précise. Si une
    # méthode échoue (élément caché, désactivé...), on l'ignore et on essaie la suivante
    # plutôt que de faire planter tout le parcours du formulaire pour une seule question.
    tentatives = [
        # Une question date utilise aussi un champ texte, donc il faut la
        # détecter et la remplir en premier, avec une vraie date (pas "test", que le
        # champ rejette silencieusement et laisse vide).
        ('[data-automation-id="dateContainer"] input', "fill_date"),
        # On cible l'attribut data-automation-id plutôt que [type="text"] : certains
        # formulaires rendent ce champ SANS attribut type du tout (le navigateur le
        # traite quand même comme du texte par défaut, mais un sélecteur CSS [type="text"]
        # ne matche que si l'attribut est écrit explicitement dans le HTML — ce qui a fait
        # échouer silencieusement le remplissage sur un vrai formulaire testé).
        ('[data-automation-id="textInput"], textarea', "fill"),
        # On cible l'input radio réel à l'intérieur de choiceItem (pas le conteneur) avec
        # un vrai clic, pas dispatch_event : sur un vrai formulaire testé, dispatch_event
        # sur le conteneur ne mettait jamais aria-checked à vrai, ce qui bloquait la
        # validation "obligatoire" sans qu'aucune erreur ne soit levée.
        ('[data-automation-id="choiceItem"] input[type="radio"]', "click"),
        # Chaque cellule NPS contient un vrai <input type="radio"> caché sous une
        # étiquette visible : on cible directement cet input, pas le conteneur.
        ('[data-automation-id="npsCell"] input[type="radio"]', "click"),
        # Les niveaux d'une notation (étoiles, trophées...) sont des éléments role="radio"
        # (souvent des <span>, pas forcément des <button>).
        ('[role="radio"]', "click"),
        # Pour un classement, le bouton "monter" du tout premier élément est désactivé
        # (il ne peut pas monter plus haut) : on cherche plutôt un bouton encore actif,
        # peu importe lequel — le but est de déclencher une interaction, pas d'obtenir
        # un ordre précis.
        ('[data-automation-id="rankingItem"] button:not([disabled])', "click"),
    ]

    for selecteur, action in tentatives:
        elements = bloc_question.locator(selecteur)

        if elements.count() == 0:
            continue

        try:
            if action == "fill_date":
                elements.first.scroll_into_view_if_needed(timeout=3000)
                elements.first.fill("01/15/2026", timeout=3000)
            elif action == "fill":
                elements.first.scroll_into_view_if_needed(timeout=3000)
                elements.first.fill(valeur_texte_factice, timeout=3000)
            else:
                # dispatch_event envoie l'événement "click" directement au navigateur,
                # sans passer par les vérifications de visibilité de Playwright — utile
                # ici car certains éléments (cellules NPS, boutons du classement) sont
                # considérés "non visibles" par Playwright alors qu'ils fonctionnent
                # normalement pour un vrai utilisateur (affichés seulement au survol,
                # ou dans un conteneur avec un positionnement particulier).
                elements.first.dispatch_event("click")

            return
        except Exception:
            # Cette méthode n’a pas fonctionné pour cette question : on essaie la suivante.
            continue


# Certaines questions à choix unique se présentent comme un menu déroulant personnalisé
# (bouton role="button" avec aria-haspopup="listbox") plutôt que des boutons radio visibles
# directement dans le HTML. Contrairement aux autres questions, ses options n'existent tout
# simplement PAS dans le HTML tant qu'on n'a pas cliqué pour ouvrir le menu — donc impossible
# à lire en analysant juste le HTML statique après coup, comme pour les autres types.
#
# Piège rencontré en conditions réelles : une fois ouvertes, toutes les options "role=option"
# de la page (celles de CE menu, mais aussi celles d'une question de classement ailleurs sur
# la même page) se retrouvent mélangées dans une seule recherche globale. La méthode fiable :
# comparer les options présentes juste avant et juste après le clic — seules les nouvelles
# apparues appartiennent au menu qu'on vient d'ouvrir.
def extraire_options_menus_deroulants_page(page) -> dict:
    options_par_question = {}

    boutons_menu = page.locator('[aria-haspopup="listbox"]')

    for index in range(boutons_menu.count()):
        bouton = boutons_menu.nth(index)

        # aria-labelledby référence l'identifiant de la question (premier des deux ids listés).
        aria_labelledby = bouton.get_attribute("aria-labelledby") or ""
        question_id = aria_labelledby.split(" ")[0] if aria_labelledby else None

        if not question_id:
            continue

        avant = set(page.locator('[role="option"]').all_text_contents())

        try:
            bouton.click(timeout=3000)
            page.wait_for_timeout(500)
        except Exception:
            continue

        apres = set(page.locator('[role="option"]').all_text_contents())
        nouvelles_options = [texte for texte in (apres - avant) if texte]

        if nouvelles_options:
            options_par_question[question_id] = nouvelles_options

        # On referme le menu avant de passer au suivant, pour ne pas fausser la comparaison
        # "avant/après" du prochain menu déroulant (et pour laisser la page dans un état propre).
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

    return options_par_question


# Cette fonction parcourt toutes les sections du formulaire (en remplissant des réponses
# factices pour avancer), et retourne le HTML rendu de chaque section visitée, ainsi que
# les options des menus déroulants rencontrés (voir extraire_options_menus_deroulants_page).
def telecharger_pages_rendues(url: str, nombre_max_pages: int = 20):
    pages_html = []
    options_menus_deroulants = {}

    with sync_playwright() as playwright:
        navigateur = playwright.chromium.launch(headless=True)
        page = navigateur.new_page()

        try:
            # "networkidle" n'est pas fiable sur cette page : Microsoft Forms garde une
            # activité réseau en arrière-plan (télémétrie...) qui empêche le réseau de
            # devenir vraiment silencieux. On se base plutôt sur "domcontentloaded"
            # (rapide et fiable) suivi d'une attente d'un vrai signal de chargement plutôt
            # qu'une pause fixe — vérifié en réel : les liens "ShareFormPage.aspx" (avec
            # sharetoken) peuvent rester sur un écran "Loading…" 10 à 12 secondes avant
            # d'afficher le formulaire, largement plus que les 3 secondes fixes utilisées
            # avant, ce qui donnait 0 question de façon aléatoire selon la vitesse du réseau
            # ce jour-là. On attend soit une vraie question, soit la page de garde
            # "Start now", avec un délai généreux ; si ni l'un ni l'autre n'apparaît (lien
            # réellement cassé/vide), on continue quand même après le délai au lieu de
            # planter, pour ne pas casser les formulaires qui ont 0 question à juste titre.
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector(
                    '[data-automation-id="questionItem"], button:has-text("Start now")',
                    timeout=20000,
                )
            except Exception:
                pass
            page.wait_for_timeout(1000)

            # Certains formulaires affichent une page de garde (titre, description, bouton
            # "Start now") avant la première question — repéré sur un formulaire réel où
            # l'extraction ne trouvait aucune question du tout tant qu'on ne cliquait pas
            # dessus. D'autres formulaires n'en ont pas : on ne clique que si elle existe.
            bouton_demarrer = page.get_by_role("button", name="Start now")
            if bouton_demarrer.count() > 0:
                bouton_demarrer.first.click()
                page.wait_for_timeout(2000)

            for _ in range(nombre_max_pages):
                options_menus_deroulants.update(extraire_options_menus_deroulants_page(page))
                pages_html.append(page.content())

                bouton_suivant = page.get_by_role("button", name="Next")

                # Si aucun bouton "Next" n'existe, on est arrivé à la dernière section.
                if bouton_suivant.count() == 0:
                    break

                bouton_suivant.first.click()
                page.wait_for_timeout(800)

                # Si un message d'erreur de validation apparaît, la page n'a pas changé :
                # il faut remplir les questions obligatoires restantes, puis réessayer.
                if page.locator('[role="alert"]').count() > 0:
                    questions_page = page.locator('[data-automation-id="questionItem"]')

                    for index_question in range(questions_page.count()):
                        remplir_reponse_factice(questions_page.nth(index_question))

                    page.wait_for_timeout(500)
                    bouton_suivant.first.click()
                    page.wait_for_timeout(800)

                page.wait_for_timeout(700)
        finally:
            navigateur.close()

    return pages_html, options_menus_deroulants


# Cette table fait correspondre le texte d'accessibilité affiché par Microsoft Forms
# à notre type brut interne. À enrichir au fur et à mesure qu'on rencontre de nouveaux
# types (on ne connaît pas la liste complète à l'avance, pas de documentation officielle).
TYPE_LABEL_VERS_TYPE_BRUT = {
    "single line text": "text",
    "multi line text": "text",
    "date": "date",
    "time": "heure",
    "single choice": "radio",
    "multiple choice": "checkbox",
    "net promoter score": "echelle_lineaire",
    "rating": "notation",
    "ranking": "classement",
    # Microsoft appelle "Likert" sa grille à choix unique par ligne (un tableau avec
    # radiogroup par ligne, comme "Give me ur op" x Kdrama/Summer Strike/... testé en réel).
    "likert": "grille_choix_unique",
}


# Cette fonction convertit le texte de type affiché par Microsoft vers notre type brut.
def convertir_type_microsoft(libelle_type: str) -> str:
    cle = libelle_type.strip().rstrip(".").lower()

    return TYPE_LABEL_VERS_TYPE_BRUT.get(cle, "inconnu")


# Cette fonction extrait les lignes et colonnes d'une grille Microsoft ("Likert").
# Vérifié en réel le 2026-07-29 : Microsoft utilise DEUX structures HTML différentes pour
# le même type de question, apparemment selon le cas (peut-être le nombre de lignes) —
# une grille à une seule ligne a été vue avec l'ancienne structure, une grille à deux lignes
# avec la nouvelle, sur des formulaires différents. On gère donc les deux, la nouvelle d'abord.
def extraire_grille_microsoft(bloc_question):
    lignes, colonnes = _extraire_grille_microsoft_nouvelle_structure(bloc_question)

    if not lignes or not colonnes:
        lignes, colonnes = _extraire_grille_microsoft_ancienne_structure(bloc_question)

    if not lignes or not colonnes:
        return None

    return {"lignes": lignes, "colonnes": colonnes}


# Nouvelle structure : chaque ligne est un likerSubQuestion, contenant plusieurs likerOption
# (une par colonne pour cette ligne). Le libellé (ligne ou colonne) est toujours dans le
# premier <span class="text-format-content"> rencontré à cet endroit.
def _extraire_grille_microsoft_nouvelle_structure(bloc_question):
    lignes_elements = bloc_question.find_all(attrs={"data-automation-id": "likerSubQuestion"})

    lignes = []
    colonnes = []

    for ordre, ligne in enumerate(lignes_elements, start=1):
        # Le libellé de la ligne est le tout premier texte trouvé dans la sous-question,
        # avant qu'on rentre dans ses options (find() s'arrête à la première correspondance).
        libelle_ligne = ligne.find(class_="text-format-content")
        texte_ligne = libelle_ligne.get_text(strip=True) if libelle_ligne else None

        if texte_ligne:
            lignes.append({"ordre": ordre, "texte": texte_ligne})

        # Les colonnes sont répétées dans chaque ligne (une fois par likerOption) : comme pour
        # les grilles Google, on ne les extrait qu'une seule fois, depuis la première ligne.
        if not colonnes:
            options_elements = ligne.find_all(attrs={"data-automation-id": "likerOption"})
            for option in options_elements:
                libelle_colonne = option.find(class_="text-format-content")
                texte_colonne = libelle_colonne.get_text(strip=True) if libelle_colonne else None

                if texte_colonne:
                    colonnes.append({"texte": texte_colonne})

    return lignes, colonnes


# Ancienne structure : un <table> avec les colonnes dans l'en-tête (likerTableTh) et une
# ligne <tr> par item à évaluer (likerTableTr), dont le libellé est dans un <th>
# (likerStatementTd).
def _extraire_grille_microsoft_ancienne_structure(bloc_question):
    colonnes_elements = bloc_question.find_all(attrs={"data-automation-id": "likerTableTh"})
    colonnes = [
        {"texte": element.get_text(strip=True)}
        for element in colonnes_elements
        if element.get_text(strip=True)
    ]

    lignes_elements = bloc_question.find_all(attrs={"data-automation-id": "likerTableTr"})
    lignes = []

    for ordre, ligne in enumerate(lignes_elements, start=1):
        libelle_ligne = ligne.find(attrs={"data-automation-id": "likerStatementTd"})
        texte_ligne = libelle_ligne.get_text(strip=True) if libelle_ligne else None

        if texte_ligne:
            lignes.append({"ordre": ordre, "texte": texte_ligne})

    return lignes, colonnes


# Cette fonction transforme un bloc HTML de question (data-automation-id="questionItem")
# en question brute compatible avec notre pipeline. options_menus_deroulants contient les
# options des menus déroulants personnalisés déjà capturées en direct dans Playwright (voir
# extraire_options_menus_deroulants_page), indexées par question_id — ces options n'existent
# jamais dans le HTML statique, contrairement à toutes les autres.
def convertir_question_html(bloc_question, options_menus_deroulants=None) -> dict:
    if options_menus_deroulants is None:
        options_menus_deroulants = {}

    titre_element = bloc_question.find(attrs={"data-automation-id": "questionTitle"})

    texte = None
    libelle_type = None
    obligatoire = False

    if titre_element:
        # Le vrai texte de la question est dans un span dédié, séparé du texte
        # d'accessibilité décrivant le type (sinon les deux se retrouvent collés).
        span_texte = titre_element.find(class_="text-format-content")
        texte = span_texte.get_text(strip=True) if span_texte else None

        obligatoire = titre_element.find(attrs={"data-automation-id": "requiredStar"}) is not None

        span_type = titre_element.find(attrs={"aria-hidden": "true"})
        libelle_type = span_type.get_text(strip=True) if span_type else None

    type_brut = convertir_type_microsoft(libelle_type) if libelle_type else "inconnu"

    # Une question texte peut avoir une contrainte de validation (ex : "doit être un nombre",
    # "doit contenir tel mot") configurée par le créateur du formulaire ("Restrictions" dans
    # l'éditeur). Microsoft affiche cette consigne directement dans l'attribut placeholder du
    # champ (ex : placeholder="The value must be a number"), à la place du texte générique
    # "Enter your answer" utilisé quand il n'y a aucune contrainte — pas besoin de déclencher
    # une erreur de validation pour l'obtenir, elle est présente dès le chargement de la page.
    # Cette info est utile pour l'IA : elle doit savoir qu'un format précis est attendu avant
    # de générer une réponse, pas juste n'importe quel texte.
    contrainte = None
    if type_brut == "text":
        champ_texte = bloc_question.find(attrs={"data-automation-id": "textInput"})
        if champ_texte:
            indice = champ_texte.get("placeholder")
            if indice and indice != "Enter your answer":
                contrainte = indice

    # L'identifiant stable de la question n'est pas sur le bloc "questionItem" lui-même,
    # mais sur un élément imbriqué dont l'id commence par "QuestionId_". Calculé ici (avant
    # les options) car le repli sur les menus déroulants en a besoin pour se retrouver.
    element_id = bloc_question.find(id=lambda valeur: valeur and valeur.startswith("QuestionId_"))
    question_id = element_id.get("id") if element_id else None

    # Les options d'une question à choix sont dans des blocs "choiceItem". get_text(strip=True)
    # colle sans espace le texte de balises HTML adjacentes (vérifié en réel : "the Other box"
    # devenait "theOtherbox") — separator=" " insère un espace entre chaque fragment, puis on
    # réduit les espaces multiples que ça peut introduire (ex : avant une ponctuation).
    options_elements = bloc_question.find_all(attrs={"data-automation-id": "choiceItem"})
    options = [
        " ".join(element.get_text(separator=" ", strip=True).split())
        for element in options_elements
    ]

    # Une question à choix unique peut se présenter comme un menu déroulant personnalisé
    # (bouton "role=button" avec aria-haspopup="listbox") plutôt que des boutons radio
    # visibles directement — dans ce cas il n'y a aucun "choiceItem" dans le HTML statique.
    # Les options ont déjà été capturées en direct dans Playwright avant cet appel.
    if type_brut == "radio" and not options and question_id in options_menus_deroulants:
        options = options_menus_deroulants[question_id]

    # Une question à choix (radio ou checkbox) peut proposer une option "Other" avec un champ
    # de texte libre à côté, en plus des choix fixes. Elle n'est pas un "choiceItem" comme les
    # autres options (structure HTML séparée, sans data-automation-value) — sans ce traitement,
    # elle est invisible pour l'extraction ci-dessus, alors qu'un répondant réel pourrait la
    # choisir (vérifié en réel : le champ associé est un data-automation-id="textInput" avec
    # placeholder="Other", absent des questions texte_libre classiques puisqu'on ne regarde
    # ici que les questions radio/checkbox).
    if type_brut in ("radio", "checkbox") and bloc_question.find(attrs={"data-automation-id": "textInput"}):
        options.append("Other")

    # Une question "Net Promoter Score" n'a pas de "choiceItem" : ses valeurs possibles
    # sont représentées par des cellules numérotées ("npsCell"). On reconstruit les
    # options nous-mêmes à partir du nombre de cellules trouvées.
    if type_brut == "echelle_lineaire" and not options:
        cellules_nps = bloc_question.find_all(attrs={"data-automation-id": "npsCell"})
        if cellules_nps:
            options = [str(valeur) for valeur in range(len(cellules_nps))]

    # Une question "Notation" (Rating, étoiles/trophées/coeurs...) n'a pas de "choiceItem"
    # non plus : chaque niveau est un élément avec role="radio" (contrairement au NPS,
    # la notation commence à 1, pas à 0).
    if type_brut == "notation" and not options:
        elements_notation = bloc_question.find_all(attrs={"role": "radio"})
        if elements_notation:
            options = [str(valeur) for valeur in range(1, len(elements_notation) + 1)]

    # Une question "Classement" (Ranking) n'a pas de "choiceItem" non plus : le texte de
    # chaque élément à classer est dans un bloc "rankingItemContent" séparé (pas imbriqué
    # dans "rankingItem", qui ne contient que les boutons monter/descendre).
    if type_brut == "classement" and not options:
        elements_classement = bloc_question.find_all(attrs={"data-automation-id": "rankingItemContent"})
        options = [element.get_text(strip=True) for element in elements_classement]

    # Une grille ("Likert") a des lignes et des colonnes au lieu de simples options :
    # les colonnes jouent le même rôle que des options (comme pour les grilles Google).
    grille = None
    if type_brut == "grille_choix_unique":
        grille = extraire_grille_microsoft(bloc_question)
        if grille and not options:
            options = [colonne["texte"] for colonne in grille["colonnes"]]

    # Une question peut contenir une image insérée par le créateur du formulaire, en plus
    # (ou à la place) de son texte. Contrairement à Google Forms, l'image est une vraie
    # balise <img> directement dans le HTML rendu, avec une URL téléchargeable sans
    # authentification (vérifié en réel) — pas besoin de la retrouver par proximité dans
    # le texte brut de la page.
    image = None
    element_image = bloc_question.find("img")
    if element_image and element_image.get("src") and question_id:
        image = telecharger_image_question(element_image["src"], identifiant=question_id)

    return {
        "question_id": question_id,
        "texte": texte,
        "type_brut": type_brut,
        "options": options,
        "grille": grille,
        "image": image,
        "obligatoire": obligatoire,
        "contrainte": contrainte,
    }


# Cette fonction transforme le HTML de toutes les sections du formulaire en formulaire brut.
# pages_html est une liste : une entrée par section visitée (voir telecharger_pages_rendues).
def convertir_formulaire_html(pages_html: list, url: str, options_menus_deroulants=None) -> dict:
    if options_menus_deroulants is None:
        options_menus_deroulants = {}

    premiere_page = BeautifulSoup(pages_html[0], "html.parser")

    titre_element = premiere_page.find(attrs={"data-automation-id": "formTitle"})
    titre = titre_element.get_text(strip=True) if titre_element else None

    # On identifie les questions déjà vues par leur identifiant, pour éviter les doublons
    # si jamais une même question apparaissait sur deux captures (ex : avant/après un clic
    # "Next" qui n'a pas encore changé la page au moment de la capture).
    # Important : le bloc "questionItem" lui-même n'a pas d'attribut "id" — l'identifiant
    # stable est sur un élément imbriqué, dont l'id commence par "QuestionId_".
    questions_brutes = []
    identifiants_vus = set()

    for html_page in pages_html:
        soup = BeautifulSoup(html_page, "html.parser")
        blocs_questions = soup.find_all(attrs={"data-automation-id": "questionItem"})

        for bloc in blocs_questions:
            element_id = bloc.find(id=lambda valeur: valeur and valeur.startswith("QuestionId_"))
            identifiant = element_id.get("id") if element_id else None

            # On ne déduplique que si on a un vrai identifiant : plusieurs questions
            # sans identifiant trouvé ne doivent pas s’écraser les unes les autres.
            if identifiant is not None:
                if identifiant in identifiants_vus:
                    continue
                identifiants_vus.add(identifiant)

            questions_brutes.append(convertir_question_html(bloc, options_menus_deroulants))

    return {
        "source": {
            "type": "microsoft_forms_scraping",
            "url": url
        },
        "titre": titre,
        "description": None,
        "questions": questions_brutes
    }


# Cette fonction fait tout le pipeline depuis un lien Microsoft Forms public.
def extraire_formulaire_microsoft(url: str) -> dict:
    pages_html, options_menus_deroulants = telecharger_pages_rendues(url)

    formulaire_brut = convertir_formulaire_html(pages_html, url, options_menus_deroulants)

    return extraire_formulaire(formulaire_brut)


# Cette partie s'exécute seulement si on lance ce fichier directement dans le terminal.
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Utilisation : python scripts_extraction/microsoft_forms_scraper.py URL_DU_FORMULAIRE")
        sys.exit(1)

    resultat = extraire_formulaire_microsoft(sys.argv[1])

    print(json.dumps(resultat, indent=2, ensure_ascii=False))
