# Tests de régression pour les parties déterministes de ia_service.py (pas d'appel à Gemini
# ici — construire_prompt/normaliser_choix/detecter_langue_formulaire sont de la pure logique
# Python). Chaque test correspond à un vrai bug trouvé et corrigé en testant l'agent sur des
# vrais formulaires (voir les commentaires dans ia_service.py pour le détail de chaque cas).

from app.services.ia_service import construire_prompt, normaliser_choix, detecter_langue_formulaire


def construire_question(**overrides):
    # Question minimale valide par défaut, à surcharger au besoin dans chaque test.
    question = {
        "texte_pour_ia": "Question de test",
        "ocr": None,
        "type_question": "texte_libre",
        "options": [],
        "grille": None,
        "question_precedente": None,
    }
    question.update(overrides)
    return question


# --- construire_prompt ---

def test_grille_choix_multiple_precise_plusieurs_colonnes_par_ligne():
    question = construire_question(
        texte_pour_ia="Quels contenus regardez-vous ?",
        type_question="grille_choix_multiple",
        grille={
            "lignes": [{"ordre": 1, "texte": "Netflix"}],
            "colonnes": [{"texte": "Films"}, {"texte": "Séries"}],
        },
    )
    prompt = construire_prompt(question)
    assert "UNE OU PLUSIEURS colonnes" in prompt


def test_grille_choix_unique_precise_une_seule_colonne_par_ligne():
    question = construire_question(
        texte_pour_ia="Notez chaque critère",
        type_question="grille_choix_unique",
        grille={
            "lignes": [{"ordre": 1, "texte": "Accueil"}, {"ordre": 2, "texte": "Rapidité"}],
            "colonnes": [{"texte": "Bien"}, {"texte": "Moyen"}],
        },
    )
    prompt = construire_prompt(question)
    assert "UNE SEULE colonne" in prompt


def test_date_laisse_le_modele_adapter_la_precision():
    question = construire_question(texte_pour_ia="Year of Birth:", type_question="date")
    prompt = construire_prompt(question)
    assert "AAAA-MM-JJ" in prompt
    assert "l'année à 4 chiffres" in prompt


def test_heure_impose_le_format_24h():
    question = construire_question(texte_pour_ia="Heure de début", type_question="heure")
    prompt = construire_prompt(question)
    assert "HH:MM" in prompt


def test_classement_demande_tous_les_elements_dans_lordre():
    question = construire_question(
        texte_pour_ia="Classez ces critères",
        type_question="classement",
        options=[{"option_id": "o1", "texte": "Prix"}, {"option_id": "o2", "texte": "Qualité"}],
    )
    prompt = construire_prompt(question)
    assert "TOUS ces éléments" in prompt
    assert "dans l'ordre" in prompt


def test_choix_multiple_precise_plusieurs_reponses_possibles():
    question = construire_question(
        texte_pour_ia="Quels outils utilisez-vous ?",
        type_question="choix_multiple",
        options=[{"option_id": "o1", "texte": "Word"}, {"option_id": "o2", "texte": "Excel"}],
    )
    prompt = construire_prompt(question)
    assert "PLUSIEURS réponses" in prompt


def test_option_qui_renvoie_vers_other_recoit_une_instruction_ciblee():
    # Bug réel (formulaire Microsoft) : une option "Yes, please specify... in the Other box
    # below." fait elle-même référence à la case "Other" — demander au modèle de repérer ça
    # tout seul de façon abstraite a échoué 2 fois sur 3 (testé en réel) ; on détecte donc le
    # cas directement dans le code, à partir des vraies options de la question.
    question = construire_question(
        texte_pour_ia="Would you like to share more?",
        type_question="choix_multiple",
        options=[
            {"option_id": "o1", "texte": "Yes, please specify the topic in the Other box below."},
            {"option_id": "o2", "texte": "No"},
            {"option_id": "o3", "texte": "Other"},
        ],
    )
    prompt = construire_prompt(question)
    assert "Yes, please specify the topic in the Other box below." in prompt
    assert "precision_autre" in prompt


def test_aucune_instruction_other_si_aucune_option_ne_le_mentionne():
    question = construire_question(
        texte_pour_ia="Votre couleur préférée",
        type_question="choix_unique",
        options=[{"option_id": "o1", "texte": "Bleu"}, {"option_id": "o2", "texte": "Rouge"}],
    )
    prompt = construire_prompt(question)
    assert "precision_autre" not in prompt


def test_echelle_lineaire_sans_zero_interdit_les_valeurs_hors_liste():
    # Bug réel : "Nombre d'adolescents" (échelle 1 à 10, pas de "0") répondait "0" (invalide),
    # puis "Aucun(e)" (toujours invalide) — la vraie réponse doit venir de la liste elle-même.
    question = construire_question(
        texte_pour_ia="Nombre d'adolescents",
        type_question="echelle_lineaire",
        options=[{"option_id": f"o{i}", "texte": str(i)} for i in range(1, 11)],
    )
    prompt = construire_prompt(question)
    assert "OBLIGATOIREMENT avec l'une de ces valeurs exactes" in prompt
    assert "la valeur la plus basse" in prompt


def test_choix_unique_simple_liste_juste_les_options():
    question = construire_question(
        texte_pour_ia="Votre couleur préférée",
        type_question="choix_unique",
        options=[{"option_id": "o1", "texte": "Bleu"}, {"option_id": "o2", "texte": "Rouge"}],
    )
    prompt = construire_prompt(question)
    assert "Choix possibles : Bleu, Rouge." in prompt


def test_ocr_est_ajoute_au_prompt():
    question = construire_question(
        texte_pour_ia="Que dit l'image ?",
        ocr={"texte_extrait": "Attention travaux"},
    )
    prompt = construire_prompt(question)
    assert "Attention travaux" in prompt


def test_contexte_precedent_ajoute_si_question_actuelle_a_un_point_dinterrogation():
    # Bug réel : "Lesquels ?" après "Êtes-vous à l'aise avec les outils informatiques ?"
    # répondait avec des langues parlées au lieu d'outils informatiques, faute de contexte.
    question = construire_question(
        texte_pour_ia="Lesquels ?",
        question_precedente="Êtes-vous à l'aise avec les outils informatiques ?",
    )
    prompt = construire_prompt(question)
    assert "Êtes-vous à l'aise avec les outils informatiques ?" in prompt


def test_contexte_precedent_ajoute_pour_formulation_si_oui():
    # Bug réel : "If yes, please explain" après une question médicale répondue "No" a
    # halluciné un texte de candidature à un stage, sans aucun rapport avec le formulaire.
    question = construire_question(
        texte_pour_ia="If yes, please explain",
        question_precedente="Does your child have any medical conditions?",
    )
    prompt = construire_prompt(question)
    assert "Does your child have any medical conditions?" in prompt


def test_contexte_precedent_absent_si_question_est_une_simple_etiquette():
    # Bugs réels : "Team size" après "major challenges", "Course" après "Year of Completion"
    # et "School" après "team name" dérivaient tous vers le sujet de la question précédente,
    # alors que ces trois questions sont complètes et sans ambiguïté toutes seules.
    for texte in ("Team size", "Course", "School"):
        question = construire_question(
            texte_pour_ia=texte,
            question_precedente="Year of Completion",
        )
        prompt = construire_prompt(question)
        assert "Year of Completion" not in prompt, f"le contexte n'aurait pas dû être ajouté pour {texte!r}"


def test_titre_formulaire_ajoute_a_toutes_les_questions():
    # Bug réel : "Commentaires libres" (dernière question, sans "?" donc sans
    # question_precedente) répondait avec un texte de candidature à un emploi, faute de savoir
    # que le formulaire était en réalité une enquête de satisfaction sur une formation.
    question = construire_question(
        texte_pour_ia="Commentaires libres",
        titre_formulaire="Enquête de satisfaction - Formation en alternance",
    )
    prompt = construire_prompt(question)
    assert "Enquête de satisfaction - Formation en alternance" in prompt


def test_titre_formulaire_absent_ne_plante_pas():
    question = construire_question(texte_pour_ia="Commentaires libres")
    prompt = construire_prompt(question)
    assert prompt == "Commentaires libres"


# --- normaliser_choix ---

def test_normaliser_choix_ignore_la_casse_et_la_ponctuation_finale():
    # Bug réel : l'agent répondait "Oui." (avec un point) alors que l'option exacte est "Oui".
    question = construire_question(
        type_question="choix_multiple",
        options=[{"option_id": "o1", "texte": "Oui"}],
    )
    assert normaliser_choix("Oui.", question) == "Oui"


def test_normaliser_choix_restaure_le_prefixe_de_lettre_omis():
    # Bug réel (quiz) : l'agent répondait "Only with permission from the teacher." sans le
    # préfixe de lettre "C.   " que l'option réelle contient.
    question = construire_question(
        type_question="choix_unique",
        options=[
            {"option_id": "o1", "texte": "A.   Whenever I want to."},
            {"option_id": "o2", "texte": "C.   Only with permission from the teacher."},
        ],
    )
    resultat = normaliser_choix("Only with permission from the teacher.", question)
    assert resultat == "C.   Only with permission from the teacher."


def test_normaliser_choix_corrige_un_prefixe_garde_mais_mal_espace():
    # Bug réel (quiz labo) : l'option réelle contient plusieurs espaces après la lettre
    # ("D.   ..."), tel qu'extrait de Google Forms — l'agent garde le préfixe mais avec un
    # seul espace ("D. ..."), ce qui ne matchait ni l'égalité stricte ni l'ancien repli
    # (qui ne gérait que le préfixe totalement omis).
    question = construire_question(
        type_question="choix_unique",
        options=[
            {"option_id": "o1", "texte": "A.   Wear safety goggles."},
            {"option_id": "o2", "texte": "D.   It helps prevent accidents.."},
        ],
    )
    resultat = normaliser_choix("D. It helps prevent accidents.", question)
    assert resultat == "D.   It helps prevent accidents.."


def test_normaliser_choix_traite_chaque_valeur_dune_liste_choix_multiple():
    question = construire_question(
        type_question="choix_multiple",
        options=[
            {"option_id": "o1", "texte": "Word"},
            {"option_id": "o2", "texte": "Excel"},
        ],
    )
    resultat = normaliser_choix("word, excel.", question)
    assert resultat == "Word, Excel"


def test_normaliser_choix_garde_la_valeur_si_aucune_option_ne_correspond():
    question = construire_question(
        type_question="choix_unique",
        options=[{"option_id": "o1", "texte": "Oui"}, {"option_id": "o2", "texte": "Non"}],
    )
    assert normaliser_choix("Peut-être", question) == "Peut-être"


def test_normaliser_choix_ne_touche_pas_aux_types_composes():
    # classement/grilles produisent des chaînes "ligne: colonne" composées, pas une seule
    # option — normaliser_choix ne doit rien y toucher.
    question = construire_question(type_question="classement", options=[{"option_id": "o1", "texte": "Prix"}])
    assert normaliser_choix("Prix, Qualité", question) == "Prix, Qualité"


def test_normaliser_choix_ne_fait_rien_sans_options():
    question = construire_question(type_question="choix_unique", options=[])
    assert normaliser_choix("Une réponse libre", question) == "Une réponse libre"


# --- detecter_langue_formulaire ---

def test_detecter_langue_formulaire_francais():
    questions = [
        construire_question(texte_pour_ia="Quel est votre nom ?"),
        construire_question(texte_pour_ia="Quelle est votre adresse email ?"),
    ]
    assert detecter_langue_formulaire(questions) == "fr"


def test_detecter_langue_formulaire_anglais():
    questions = [
        construire_question(texte_pour_ia="What is your name?"),
        construire_question(texte_pour_ia="What is your email address?"),
    ]
    assert detecter_langue_formulaire(questions) == "en"


def test_detecter_langue_formulaire_sans_questions_renvoie_none():
    assert detecter_langue_formulaire([]) is None
