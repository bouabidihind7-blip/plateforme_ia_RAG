from datetime import datetime


# Cette fonction détermine si la question contient du texte, une image, ou les deux.
def determiner_modalite(question_brute):
    # On vérifie si le champ "texte" existe dans la question brute.
    texte_present = "texte" in question_brute

    # On vérifie si le champ "image" existe dans la question brute.
    image_presente = "image" in question_brute

    # On récupère le champ "texte" s’il existe, sinon Python retourne None.
    texte = question_brute.get("texte")

    # On récupère le champ "image" s’il existe, sinon Python retourne None.
    image = question_brute.get("image")

    # Si le champ texte existe et le champ image contient une vraie image, la question est texte + image.
    if texte_present and image:
        return "texte_image"

    # Si le champ texte existe, même vide, la question est textuelle.
    # Si le texte est vide, le statut indiquera ensuite "texte_manquant".
    if texte_present:
        return "texte"

    # Si le champ image existe et contient une vraie image, la question est une image.
    if image_presente and image:
        return "image"

    # Si aucun des deux n’existe, on ne peut pas déterminer la modalité.
    return "inconnue"


# Cette fonction transforme le type brut du formulaire vers notre type standard.
def determiner_type_question(question_brute):
    # On récupère le type brut fourni par la source, par exemple "radio", "checkbox" ou "text".
    type_brut = question_brute.get("type_brut")

    # On récupère les options s’il y en a. Si elles n’existent pas, on utilise une liste vide.
    options = question_brute.get("options", [])

    # "radio" signifie que l’utilisateur peut choisir une seule option.
    if type_brut == "radio":
        return "choix_unique"

    # "checkbox" signifie que l’utilisateur peut choisir plusieurs options.
    if type_brut == "checkbox":
        return "choix_multiple"

    # "notation" signifie que l’utilisateur choisit une note, par exemple 1 à 5 étoiles.
    if type_brut == "notation":
        return "notation"

    # "echelle_lineaire" signifie que l’utilisateur choisit une valeur sur une échelle.
    if type_brut == "echelle_lineaire":
        return "echelle_lineaire"

    # "date" signifie que l’utilisateur doit répondre avec une date.
    if type_brut == "date":
        return "date"

    # "heure" signifie que l’utilisateur doit répondre avec une heure.
    if type_brut == "heure":
        return "heure"

    # "grille_choix_multiple" signifie qu’on a des lignes et des colonnes avec cases à cocher.
    if type_brut == "grille_choix_multiple":
        return "grille_choix_multiple"

    # "grille_choix_unique" signifie qu’on a des lignes et des colonnes avec un seul choix par ligne.
    if type_brut == "grille_choix_unique":
        return "grille_choix_unique"

    # "depot_fichier" signifie que la question attend un fichier envoyé par l’utilisateur.
    # C’est explicitement hors périmètre du projet (voir project_notes/project_plan.md),
    # donc on le reconnaît à part plutôt que de le confondre avec du texte_libre.
    if type_brut == "depot_fichier":
        return "depot_fichier"

    # "classement" signifie que l’utilisateur doit ordonner une liste d’éléments
    # (type "Ranking" de Microsoft Forms, qui n’existe pas dans Google Forms).
    if type_brut == "classement":
        return "classement"

    # Si aucune option n’existe, on considère que la réponse attendue est du texte libre.
    if not options:
        return "texte_libre"

    # Si on ne reconnaît pas le cas, on retourne "type_inconnu".
    return "type_inconnu"


# Cette fonction déduit le type de réponse attendu à partir du type de question.
def determiner_type_reponse(type_question):
    # Une question texte libre attend une réponse sous forme de texte.
    if type_question == "texte_libre":
        return "texte"

    # Une question à choix unique attend une seule option comme réponse.
    if type_question == "choix_unique":
        return "option_unique"

    # Une question à choix multiple attend plusieurs options comme réponse.
    if type_question == "choix_multiple":
        return "options_multiples"

    # Une notation attend une seule valeur choisie.
    if type_question == "notation":
        return "option_unique"

    # Une échelle linéaire attend une seule valeur choisie.
    if type_question == "echelle_lineaire":
        return "option_unique"

    # Une question date attend une date.
    if type_question == "date":
        return "date"

    # Une question heure attend une heure.
    if type_question == "heure":
        return "heure"

    # Une grille à choix multiples attend plusieurs choix organisés par ligne.
    if type_question == "grille_choix_multiple":
        return "grille_options_multiples"

    # Une grille à choix unique attend un choix par ligne.
    if type_question == "grille_choix_unique":
        return "grille_option_unique"

    # Un dépôt de fichier est hors périmètre : aucun type de réponse ne sera généré par l’IA.
    if type_question == "depot_fichier":
        return "hors_perimetre"

    # Un classement attend la liste des éléments dans l’ordre choisi par l’utilisateur.
    if type_question == "classement":
        return "options_multiples"

    # Si le type de question est inconnu, on ne peut pas déterminer le type de réponse.
    return "inconnu"


# Cette fonction transforme les options simples en options structurées.
# question_id sert à construire un identifiant stable par option (ex: "q2_opt1"),
# selon la même convention que test_documents/formulaire_test.json.
def formater_options(options_brutes, question_id):
    # On prépare une liste vide qui contiendra les options propres.
    options_formatees = []

    # enumerate permet de parcourir les options avec leur position.
    # start=1 veut dire que la première option aura l’ordre 1, pas 0.
    for ordre, texte_option in enumerate(options_brutes, start=1):
        # On ajoute chaque option sous forme de dictionnaire standard.
        options_formatees.append({
            "option_id": f"{question_id}_opt{ordre}",
            "texte": texte_option
        })

    # On retourne la liste finale des options formatées.
    return options_formatees


# Sous ce seuil de confiance OCR, on considère le texte extrait trop incertain pour être
# envoyé à l’IA sans validation humaine (voir project_notes/project_plan.md, section OCR).
SEUIL_CONFIANCE_OCR_FIABLE = 0.6


# Cette fonction détermine si la question extraite est prête ou si elle contient une erreur.
def determiner_statut_extraction(modalite, type_question, texte, options, grille, ocr=None):
    # Un dépôt de fichier est volontairement hors périmètre du projet : ce n’est pas une erreur
    # d’extraction, donc on le signale distinctement plutôt que de le confondre avec du contenu manquant.
    if type_question == "depot_fichier":
        return "hors_perimetre"

    # Si aucun texte et aucune image n’existent, la question n’est pas exploitable.
    if modalite == "inconnue":
        return "contenu_manquant"

    # Pour une question textuelle simple, le texte ne doit pas être vide.
    # Exception : une grille peut parfois ne pas avoir de titre principal,
    # mais rester exploitable grâce à ses lignes et colonnes.
    if modalite == "texte" and not texte and type_question not in ["grille_choix_multiple", "grille_choix_unique"]:
        return "texte_manquant"

    # Pour une question qui dépend d’une image, on vérifie que l’OCR a bien fonctionné
    # et que sa confiance est suffisante avant de considérer la question comme prête.
    if modalite in ["image", "texte_image"]:
        if not ocr or not ocr.get("texte_extrait"):
            return "ocr_echec"

        if ocr.get("score_confiance", 0) < SEUIL_CONFIANCE_OCR_FIABLE:
            return "ocr_incertain"

    # Si le type de question n’est pas reconnu, le script ne sait pas comment la traiter.
    if type_question == "type_inconnu":
        return "type_inconnu"

    # Une question à choix doit contenir au moins une option.
    if type_question in ["choix_unique", "choix_multiple", "notation", "echelle_lineaire", "classement"] and not options:
        return "options_manquantes"

    # Une grille doit contenir des lignes et des colonnes.
    if type_question in ["grille_choix_multiple", "grille_choix_unique"]:
        if not grille:
            return "grille_manquante"

        if not grille.get("lignes") or not grille.get("colonnes"):
            return "grille_incomplete"

    # Si aucune erreur n’a été trouvée, la question est prête.
    return "prete"


# Cette fonction construit le texte qui sera envoyé à l’IA.
# Pour la plupart des questions, c’est juste le texte de la question.
# Mais pour une grille, le titre général est parfois vide (Google Forms affiche alors
# "Question" par défaut sans que ce soit rempli) : dans ce cas, on reconstruit un texte
# utile à partir des lignes et colonnes, sinon l’IA n’aurait aucune information exploitable.
# Pour une question image ou texte_image, le texte OCR complète (ou remplace) le texte saisi.
def construire_texte_pour_ia(texte, type_question, grille, modalite=None, ocr=None, contrainte=None):
    if type_question in ["grille_choix_unique", "grille_choix_multiple"] and grille:
        lignes = [ligne["texte"] for ligne in grille.get("lignes", []) if ligne.get("texte")]
        colonnes = [colonne["texte"] for colonne in grille.get("colonnes", []) if colonne.get("texte")]

        if lignes and colonnes:
            prefixe = texte or "Grille sans titre"

            return (
                f"{prefixe} — pour chacun de : {', '.join(lignes)}, "
                f"choisir parmi : {', '.join(colonnes)}."
            )

    # Récupère le texte lu dans l’image par l’OCR, s’il existe.
    texte_ocr = ocr.get("texte_extrait") if ocr else None

    # Question uniquement image : le texte pour l’IA vient entièrement de l’OCR.
    if modalite == "image":
        resultat = texte_ocr or None
    # Question texte + image : on combine les deux sources quand l’OCR a trouvé quelque chose.
    elif modalite == "texte_image" and texte_ocr:
        resultat = f"{texte} {texte_ocr}" if texte else texte_ocr
    else:
        resultat = texte

    # Une contrainte de validation (ex : "the value must be a number") doit être visible par
    # l’IA : sans elle, l’IA pourrait générer une réponse qui a l’air correcte mais qui ne
    # respecte pas le format exigé par le formulaire (repéré en réel sur Microsoft Forms,
    # voir microsoft_forms_scraper.py).
    if contrainte and resultat:
        return f"{resultat} (contrainte : {contrainte})"

    return resultat


# Cette fonction transforme une question brute en question standard JSON.
# ocr_precalcule permet de fournir un résultat OCR déjà calculé à l’avance (voir
# extraire_formulaire, qui traite les images de tout le formulaire en parallèle plutôt
# qu’une par une) — sinon, l’OCR est lancé ici directement pour cette seule question.
def extraire_question_textuelle(question_brute, ordre, ocr_precalcule=None):
    # On détermine si la question est texte, image, texte_image ou inconnue.
    modalite = determiner_modalite(question_brute)

    # On détermine le type de question : texte_libre, choix_unique, choix_multiple...
    type_question = determiner_type_question(question_brute)

    # On déduit automatiquement le type de réponse attendu.
    type_reponse_attendu = determiner_type_reponse(type_question)

    # On récupère le texte de la question.
    texte = question_brute.get("texte")

    # On récupère le chemin de l’image (un chemin local, pour l’instant).
    image = question_brute.get("image")

    # On récupère les options brutes ou une liste vide si elles n’existent pas.
    options_brutes = question_brute.get("options", [])

    # On récupère la grille si la question est une grille Google Forms.
    grille = question_brute.get("grille")

    # On récupère une éventuelle contrainte de validation (ex : "doit être un nombre"),
    # absente si la source ne la fournit pas (cas du scraping Google, par exemple).
    contrainte = question_brute.get("contrainte")

    # On récupère l’identifiant fourni par la source (Google, Microsoft...).
    # S’il n’est pas fourni (ex : scraping HTML public qui ne le donne pas), on en génère
    # un basé sur l’ordre, pour que chaque question ait quand même un identifiant stable
    # à l’intérieur de ce formulaire. Calculé ici (avant les options) car formater_options
    # en a besoin pour construire un option_id.
    question_id = question_brute.get("question_id") or f"q{ordre}"

    # On transforme les options simples en options structurées avec ordre + texte — sauf pour
    # une grille : ses "colonnes" (voir plus bas) contiennent déjà exactement le même texte,
    # doublon complet repéré en réel (ex : "options" = ["Eres yeager", "L", "Light", "Conan"]
    # identique à "grille.colonnes"). Pas besoin de le répéter deux fois dans le même JSON.
    if type_question in ["grille_choix_multiple", "grille_choix_unique"]:
        options = []
    else:
        options = formater_options(options_brutes, question_id)

    # Si la question dépend d’une image, on utilise le résultat OCR déjà calculé s’il est
    # fourni (voir extraire_formulaire), sinon on lance l’OCR ici pour cette seule image.
    # Import différé : ça évite de charger OpenCV/EasyOCR pour tous les formulaires
    # qui ne contiennent aucune question image (le cas le plus fréquent en test).
    ocr = None

    if modalite in ["image", "texte_image"] and image:
        if ocr_precalcule is not None:
            ocr = ocr_precalcule
        else:
            from ocr_utils import extraire_texte_image

            ocr = extraire_texte_image(image)

    # On détermine si la question est prête ou si elle contient une erreur précise.
    statut_extraction = determiner_statut_extraction(
        modalite=modalite,
        type_question=type_question,
        texte=texte,
        options=options,
        grille=grille,
        ocr=ocr
    )

    # On récupère si la question est obligatoire. Par défaut False si la source ne le précise pas
    # (c’est le cas du scraping HTML public, qui ne fournit pas cette information de façon fiable).
    obligatoire = question_brute.get("obligatoire", False)

    # On construit la question finale dans notre format JSON standard.
    question_standard = {
        "question_id": question_id,
        "ordre": ordre,
        "modalite": modalite,
        "texte": texte,
        "image": image,
        "ocr": ocr,
        "texte_pour_ia": construire_texte_pour_ia(texte, type_question, grille, modalite, ocr, contrainte),
        "type_question": type_question,
        "type_reponse_attendu": type_reponse_attendu,
        "obligatoire": obligatoire,
        "options": options,
        "grille": grille,
        "contrainte": contrainte,
        "statut_extraction": statut_extraction
    }

    # On retourne la question standard.
    return question_standard


# Cette fonction détermine le statut global du formulaire après extraction.
def determiner_statut_formulaire(questions):
    # Si le formulaire ne contient aucune question, il est considéré comme vide.
    if not questions:
        return "vide"

    # Les questions "hors_perimetre" (ex : dépôt de fichier) sont volontairement exclues :
    # ce n’est pas un échec d’extraction, donc elles ne doivent pas faire baisser le statut
    # global du formulaire vers "partiel" ou "erreur".
    questions_evaluables = [
        question for question in questions
        if question["statut_extraction"] != "hors_perimetre"
    ]

    # Si toutes les questions sont hors périmètre, il n’y a rien à évaluer : on considère
    # l’extraction comme prête (rien n’a échoué).
    if not questions_evaluables:
        return "prete"

    # On compte les questions qui sont prêtes, parmi celles qui sont évaluables.
    nombre_questions_pretes = sum(
        1 for question in questions_evaluables
        if question["statut_extraction"] == "prete"
    )

    # Si toutes les questions évaluables sont prêtes, le formulaire est prêt.
    if nombre_questions_pretes == len(questions_evaluables):
        return "prete"

    # Si aucune question évaluable n’est prête, le formulaire est en erreur.
    if nombre_questions_pretes == 0:
        return "erreur"

    # Si certaines questions sont prêtes et d’autres non, l’extraction est partielle.
    return "partiel"


# Cette fonction transforme un formulaire brut complet en formulaire standard JSON.
def extraire_formulaire(formulaire_brut):
    # On récupère la source du formulaire, ou une source vide si elle n’existe pas.
    # Pas de champ "fichier" : la plateforme ne reçoit que des liens de formulaire, jamais de
    # fichier importé — retiré, à rajouter le jour où ce cas existe vraiment.
    source = formulaire_brut.get("source", {
        "type": None,
        "url": None
    })

    # On récupère le titre du formulaire.
    titre = formulaire_brut.get("titre")

    # On récupère la description du formulaire.
    description = formulaire_brut.get("description")

    # On récupère les questions brutes, ou une liste vide si elles n’existent pas.
    questions_brutes = formulaire_brut.get("questions", [])

    # L’OCR est l’étape la plus lente du pipeline. Si plusieurs questions ont une image,
    # on les traite en parallèle (plusieurs images en même temps) plutôt qu’une par une,
    # pour réduire le temps total d’attente sur un formulaire avec plusieurs images.
    chemins_images_a_traiter = []

    for question_brute in questions_brutes:
        modalite = determiner_modalite(question_brute)
        image = question_brute.get("image")

        if modalite in ["image", "texte_image"] and image:
            chemins_images_a_traiter.append(image)

    resultats_ocr_par_image = {}

    # Certaines images (ex : capture d'écran avec énormément de petits éléments de texte,
    # comme une barre d'outils dense) peuvent faire boucler EasyOCR très longtemps — constaté
    # en réel sur un cas où même un timeout de 5 minutes appliqué au processus entier n'a pas
    # suffi à l'arrêter proprement. On limite donc le temps accordé à l'OCR d'UNE SEULE image :
    # au-delà, on abandonne cette image précise (statut ocr_echec) plutôt que de bloquer tout
    # le formulaire indéfiniment. Le thread bloqué peut continuer à tourner en arrière-plan
    # (Python ne permet pas d'arrêter un thread de force), mais comme ce script est un outil
    # en ligne de commande à courte durée de vie, il se termine avec le reste du processus.
    DELAI_MAX_OCR_SECONDES = 180

    if chemins_images_a_traiter:
        # Import différé : évite de charger OpenCV/EasyOCR pour les formulaires qui ne
        # contiennent aucune question image (le cas le plus fréquent en test).
        from ocr_utils import extraire_texte_image
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as DelaiOcrDepasse

        with ThreadPoolExecutor(max_workers=min(len(chemins_images_a_traiter), 4)) as executeur:
            futures_par_chemin = {
                executeur.submit(extraire_texte_image, chemin): chemin
                for chemin in chemins_images_a_traiter
            }

            for future, chemin in futures_par_chemin.items():
                try:
                    resultats_ocr_par_image[chemin] = future.result(timeout=DELAI_MAX_OCR_SECONDES)
                except DelaiOcrDepasse:
                    resultats_ocr_par_image[chemin] = {
                        "texte_extrait": "",
                        "score_confiance": 0,
                        "nb_mots": 0,
                        "erreur": f"OCR interrompu après {DELAI_MAX_OCR_SECONDES}s (image trop complexe à analyser)",
                        "image_utilisee": chemin
                    }

    # Cette liste va contenir les questions transformées vers notre format standard.
    questions_standard = []

    # On parcourt toutes les questions brutes avec leur ordre.
    for ordre, question_brute in enumerate(questions_brutes, start=1):
        image = question_brute.get("image")

        # On réutilise le résultat OCR déjà calculé en parallèle pour cette image,
        # s’il en existe un.
        ocr_precalcule = resultats_ocr_par_image.get(image) if image else None

        question_standard = extraire_question_textuelle(question_brute, ordre, ocr_precalcule)

        # On ajoute la question standard dans la liste finale.
        questions_standard.append(question_standard)

    # On détermine le statut global du formulaire.
    statut_extraction = determiner_statut_formulaire(questions_standard)

    # On construit le formulaire final dans notre format JSON standard.
    # date_extraction enregistre le moment où LE SCRIPT a lu le formulaire — différent d'un
    # éventuel horodatage d'insertion en base de données plus tard, utile pour savoir si le
    # formulaire source a pu changer depuis (constaté en réel plusieurs fois cette session).
    formulaire_standard = {
        "source": source,
        "titre": titre,
        "description": description,
        "date_extraction": datetime.now().isoformat(),
        "statut_extraction": statut_extraction,
        "questions": questions_standard
    }

    # On retourne le formulaire standard.
    return formulaire_standard
