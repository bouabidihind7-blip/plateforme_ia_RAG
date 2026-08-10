# text permet d’écrire des requêtes SQL manuellement.
from sqlalchemy import text

# Va dans le fichier backend/app/database.py
 # et prends la variable SessionLocal pour ouvrir une session avec postgre sql.
from backend.app.database import SessionLocal

# Va dans le fichier backend/app/schemas/formulaire.py
# et prends la classe FormulaireEntree
from backend.app.schemas.formulaire import FormulaireEntree

# Réutilise la même fonction de détection de langue que generer_reponses_formulaire —
# on veut calculer langue_formulaire exactement de la même façon, qu'on parte d'un JSON
# fraîchement extrait ou d'un formulaire relu depuis la base.
from backend.app.services.ia_service import detecter_langue_formulaire


# Enregistre un formulaire validé dans PostgreSQL.
def enregistrer_formulaire(formulaire: FormulaireEntree) -> int:
    # Ouvre une session avec PostgreSQL.
    # La session sera automatiquement fermée à la fin du bloc.
    with SessionLocal() as session:

        # Insère les informations générales du formulaire, y compris les champs ajoutés à
        # l'étape 1 (description/date_extraction/statut_extraction) — url_source vient de
        # source.url quand le formulaire a été importé via extraire_formulaire_depuis_url.
        resultat_formulaire = session.execute(
            text("""
                INSERT INTO formulaires (
                    identifiant_externe,
                    fournisseur,
                    titre,
                    description,
                    url_source,
                    date_extraction,
                    statut_extraction
                )
                VALUES (
                    :identifiant_externe,
                    :fournisseur,
                    :titre,
                    :description,
                    :url_source,
                    :date_extraction,
                    :statut_extraction
                )
                RETURNING id
            """),
            {
                "identifiant_externe": formulaire.formulaire_id,
                "fournisseur": formulaire.fournisseur,
                "titre": formulaire.titre,
                "description": formulaire.description,
                "url_source": formulaire.source.url if formulaire.source else None,
                "date_extraction": formulaire.date_extraction,
                "statut_extraction": formulaire.statut_extraction,
            },
        )

        # Récupère l’id interne généré par PostgreSQL pour ce formulaire.
        formulaire_db_id = resultat_formulaire.scalar_one()

        # Parcourt toutes les questions du formulaire.
        for question in formulaire.questions:

            # question.ocr est None pour une question sans image — dans ce cas, toutes les
            # colonnes ocr_* restent NULL en base, comme prévu par le schéma SQL.
            ocr = question.ocr

            # Insère une question dans la table questions, avec tous les champs ajoutés à
            # l'étape 1 (contrainte, texte_pour_ia, statut_extraction, ocr_*). Utilise
            # directement question.type_reponse_attendu (déjà calculé et validé par Pydantic à
            # l'étape 1) au lieu de le recalculer ici — un seul endroit qui décide, pas deux.
            resultat_question = session.execute(
                text("""
                    INSERT INTO questions (
                        identifiant_externe,
                        formulaire_id,
                        ordre,
                        modalite,
                        texte,
                        image,
                        type_question,
                        type_reponse_attendu,
                        obligatoire,
                        contrainte,
                        texte_pour_ia,
                        statut_extraction,
                        ocr_texte_extrait,
                        ocr_score_confiance,
                        ocr_nb_mots,
                        ocr_erreur,
                        ocr_image_utilisee
                    )
                    VALUES (
                        :identifiant_externe,
                        :formulaire_id,
                        :ordre,
                        :modalite,
                        :texte,
                        :image,
                        :type_question,
                        :type_reponse_attendu,
                        :obligatoire,
                        :contrainte,
                        :texte_pour_ia,
                        :statut_extraction,
                        :ocr_texte_extrait,
                        :ocr_score_confiance,
                        :ocr_nb_mots,
                        :ocr_erreur,
                        :ocr_image_utilisee
                    )
                    RETURNING id
                """),
                {
                    "identifiant_externe": question.question_id,
                    "formulaire_id": formulaire_db_id,
                    "ordre": question.ordre,
                    "modalite": question.modalite,
                    "texte": question.texte,
                    "image": question.image,
                    "type_question": question.type_question,
                    "type_reponse_attendu": question.type_reponse_attendu,
                    "obligatoire": question.obligatoire,
                    "contrainte": question.contrainte,
                    "texte_pour_ia": question.texte_pour_ia,
                    "statut_extraction": question.statut_extraction,
                    "ocr_texte_extrait": ocr.texte_extrait if ocr else None,
                    "ocr_score_confiance": ocr.score_confiance if ocr else None,
                    "ocr_nb_mots": ocr.nb_mots if ocr else None,
                    "ocr_erreur": ocr.erreur if ocr else None,
                    "ocr_image_utilisee": ocr.image_utilisee if ocr else None,
                },
            )

            # Récupère l’id interne généré pour cette question.
            question_db_id = resultat_question.scalar_one()

            # Parcourt les options de la question — reste vide pour les grilles (voir plus bas).
            for position, option in enumerate(question.options, start=1):

                # Insère une option dans la table options.
                session.execute(
                    text("""
                        INSERT INTO options (
                            identifiant_externe,
                            question_id,
                            ordre,
                            texte
                        )
                        VALUES (
                            :identifiant_externe,
                            :question_id,
                            :ordre,
                            :texte
                        )
                    """),
                    {
                        "identifiant_externe": option.option_id,
                        "question_id": question_db_id,
                        "ordre": position,
                        "texte": option.texte,
                    },
                )

            # Pour une grille, deux boucles SÉPARÉES et indépendantes — les colonnes sont
            # partagées par toutes les lignes, pas propres à chacune (voir grille_lignes/
            # grille_colonnes dans le schéma SQL : aucune des deux tables ne référence l'autre,
            # toutes les deux référencent seulement la question).
            if question.type_question in ("grille_choix_unique", "grille_choix_multiple") and question.grille:

                for grille_ligne in question.grille.lignes:
                    session.execute(
                        text("""
                            INSERT INTO grille_lignes (question_id, ordre, texte)
                            VALUES (:question_id, :ordre, :texte)
                        """),
                        {
                            "question_id": question_db_id,
                            "ordre": grille_ligne.ordre,
                            "texte": grille_ligne.texte,
                        },
                    )

                for grille_colonne in question.grille.colonnes:
                    session.execute(
                        text("""
                            INSERT INTO grille_colonnes (question_id, texte)
                            VALUES (:question_id, :texte)
                        """),
                        {
                            "question_id": question_db_id,
                            "texte": grille_colonne.texte,
                        },
                    )

        # Valide définitivement toutes les insertions.
        session.commit()

        # Retourne l’id interne du formulaire enregistré.
        return formulaire_db_id
# Recharge un formulaire déjà importé depuis PostgreSQL, sous EXACTEMENT la même forme que le
# JSON produit par extraire_formulaire_depuis_url — pour que construire_prompt/
# generer_reponses_formulaire (ia_service.py) fonctionnent sans aucune modification, qu'ils
# reçoivent des données fraîchement extraites ou relues depuis la base.
def charger_formulaire_pour_generation(formulaire_id: int) -> dict:
    with SessionLocal() as session:

        # Le titre et l'url source du formulaire — une seule requête, pas par question.
        # url_source alimente formulaire["source"]["url"], attendu par generer_reponses_formulaire
        # (ia_service.py) exactement comme pour un formulaire fraîchement extrait.
        ligne_formulaire = session.execute(
            text("SELECT titre, url_source FROM formulaires WHERE id = :formulaire_id"),
            {"formulaire_id": formulaire_id},
        ).mappings().one()
        titre_formulaire = ligne_formulaire["titre"]

        # Les questions de CE formulaire, triées par ordre — même filtre statut_extraction ==
        # "prete" que generer_reponses_formulaire, pour ignorer les questions incomplètes/
        # cassées exactement comme le fait déjà ia_service.py aujourd'hui.
        lignes_questions = session.execute(
            text("""
                SELECT
                    id,
                    identifiant_externe AS question_id,
                    texte_pour_ia,
                    type_question,
                    type_reponse_attendu,
                    ocr_texte_extrait,
                    ocr_score_confiance,
                    ocr_nb_mots,
                    ocr_erreur,
                    ocr_image_utilisee
                FROM questions
                WHERE formulaire_id = :formulaire_id
                AND statut_extraction = 'prete'
                ORDER BY ordre
            """),
            {"formulaire_id": formulaire_id},
        ).mappings().all()

        questions = []
        for ligne in lignes_questions:
            question = {
                # id_interne : l'id PostgreSQL réel, à part de "question_id" (l'identifiant
                # externe, ex: "q1") — nécessaire pour ré-écrire dans reponses_proposees après
                # génération, dont la clé étrangère pointe vers cet id interne, pas l'externe.
                # ia_service.py n'utilise jamais cette clé, elle ne le gêne pas.
                "id_interne": ligne["id"],
                "question_id": ligne["question_id"],
                "texte_pour_ia": ligne["texte_pour_ia"],
                "type_question": ligne["type_question"],
                "type_reponse_attendu": ligne["type_reponse_attendu"],
                # Toujours "prete" ici : déjà filtré par la requête SQL au-dessus (WHERE
                # statut_extraction = 'prete') — remis dans le dict juste pour que
                # generer_reponses_formulaire (ia_service.py) retrouve la même clé qu'il
                # attend, sans avoir à interroger la base une deuxième fois pour la relire.
                "statut_extraction": "prete",
                "options": None,
                "grille": None,
            }

            # ocr : None si la question n'a pas d'image (les 5 colonnes ocr_* sont alors
            # toutes NULL) — sinon, on les rassemble en un seul dictionnaire imbriqué, comme
            # l'attend construire_prompt (question["ocr"]["texte_extrait"]).
            if ligne["ocr_texte_extrait"] is not None:
                question["ocr"] = {
                    "texte_extrait": ligne["ocr_texte_extrait"],
                    "score_confiance": ligne["ocr_score_confiance"],
                    "nb_mots": ligne["ocr_nb_mots"],
                    "erreur": ligne["ocr_erreur"],
                    "image_utilisee": ligne["ocr_image_utilisee"],
                }
            else:
                question["ocr"] = None

            # Une requête séparée pour les options de CETTE question précise (vide pour une
            # grille, comme d'habitude).
            options = session.execute(
                text("""
                    SELECT texte FROM options
                    WHERE question_id = :question_id
                    ORDER BY ordre
                """),
                {"question_id": ligne["id"]},
            ).mappings().all()
            question["options"] = [{"texte": option["texte"]} for option in options]

            # Pour une grille, deux requêtes séparées de plus — lignes et colonnes,
            # indépendantes l'une de l'autre, exactement comme pour l'écriture à l'Étape 3.
            if ligne["type_question"] in ("grille_choix_unique", "grille_choix_multiple"):
                grille_lignes = session.execute(
                    text("""
                        SELECT ordre, texte FROM grille_lignes
                        WHERE question_id = :question_id
                        ORDER BY ordre
                    """),
                    {"question_id": ligne["id"]},
                ).mappings().all()
                grille_colonnes = session.execute(
                    text("""
                        SELECT texte FROM grille_colonnes
                        WHERE question_id = :question_id
                    """),
                    {"question_id": ligne["id"]},
                ).mappings().all()
                question["grille"] = {
                    "lignes": [{"ordre": l["ordre"], "texte": l["texte"]} for l in grille_lignes],
                    "colonnes": [{"texte": c["texte"]} for c in grille_colonnes],
                }

            questions.append(question)

        # langue_formulaire et question_precedente ne sont stockées nulle part en base — on
        # les calcule ici de la même façon que generer_reponses_formulaire les calcule pour un
        # formulaire fraîchement extrait.
        langue_formulaire = detecter_langue_formulaire(questions)
        for index, question in enumerate(questions):
            question["question_precedente"] = (
                questions[index - 1]["texte_pour_ia"] if index > 0 else None
            )
            question["langue_formulaire"] = langue_formulaire
            question["titre_formulaire"] = titre_formulaire

        return {
            "titre": titre_formulaire,
            "source": {"url": ligne_formulaire["url_source"]},
            "questions": questions,
        }


# Renvoie l'identifiant externe (question_id) de chaque question de CE formulaire qui a déjà
# une réponse UTILISABLE (pas rejetée) de CE modèle précis — pour éviter de rappeler Gemini et
# de créer des doublons si le traitement est relancé sur un formulaire déjà (partiellement)
# traité. Une réponse REJETÉE par un humain ne compte PAS comme "déjà répondue" — si TOUTES les
# réponses d'une question sont rejetées (ou qu'il n'y en a aucune), elle doit être régénérée au
# prochain traitement. Une seule requête, rapide (index déjà en place), bien moins coûteuse
# qu'un seul appel à Gemini.
def lister_questions_deja_repondues(formulaire_id: int, modele_ia: str) -> set[str]:
    with SessionLocal() as session:
        resultat = session.execute(
            text("""
                SELECT q.identifiant_externe
                FROM reponses_proposees r
                JOIN questions q ON q.id = r.question_id
                WHERE q.formulaire_id = :formulaire_id
                AND r.modele_ia = :modele_ia
                AND r.statut != 'rejetée'
            """),
            {"formulaire_id": formulaire_id, "modele_ia": modele_ia},
        )
        return {ligne[0] for ligne in resultat.all()}


# Liste tous les formulaires importés — utilisé par la nouvelle page historique.html pour
# afficher chaque formulaire (titre, lien cliquable) avant de choisir lequel consulter.
def lister_formulaires() -> list[dict]:
    with SessionLocal() as session:
        resultat = session.execute(
            text("""
                SELECT
                    id,
                    titre,
                    url_source,
                    fournisseur,
                    date_extraction
                FROM formulaires
                ORDER BY date_extraction DESC
            """)
        )
        return resultat.mappings().all()
