# text permet d’écrire des requêtes SQL manuellement.
from sqlalchemy import text

# Va dans le fichier backend/app/database.py
 # et prends la variable SessionLocal pour ouvrir une session avec postgre sql.
from backend.app.database import SessionLocal

# Va dans le fichier backend/app/schemas/formulaire.py
# et prends la classe FormulaireEntree
from backend.app.schemas.formulaire import FormulaireEntree


# Détermine automatiquement le type de réponse attendu selon le type de question.
def determiner_type_reponse(type_question: str) -> str:
    #str) -> str: la focntion prend en entrée un type de question (str) et retourne le type de réponse attendu (str). 
    # Si la question est libre, la réponse attendue est du texte.
    if type_question == "texte_libre":
        return "texte"

    # Si la question a un seul choix, la réponse attendue est une seule option.
    if type_question == "choix_unique":
        return "option_unique"

    # Si la question accepte plusieurs choix, la réponse attendue est plusieurs options.
    if type_question == "choix_multiple":
        return "options_multiples"

    # Sécurité : normalement ce cas n’arrive pas grâce à Pydantic.
    raise ValueError("Type de question inconnu")


# Enregistre un formulaire validé dans PostgreSQL.
def enregistrer_formulaire(formulaire: FormulaireEntree) -> int:
    # Ouvre une session avec PostgreSQL.
    # La session sera automatiquement fermée à la fin du bloc.
    with SessionLocal() as session:

        # Insère les informations générales du formulaire.
        resultat_formulaire = session.execute(
            text("""
                INSERT INTO formulaires (
                    identifiant_externe,
                    fournisseur,
                    titre
                )
                VALUES (
                    :identifiant_externe,
                    :fournisseur,
                    :titre
                )
                RETURNING id
            """),
            {
                "identifiant_externe": formulaire.formulaire_id,
                "fournisseur": formulaire.fournisseur,
                "titre": formulaire.titre,
            },
        )

        # Récupère l’id interne généré par PostgreSQL pour ce formulaire.
        formulaire_db_id = resultat_formulaire.scalar_one()

        # Parcourt toutes les questions du formulaire.
        for question in formulaire.questions:

            # Calcule le type de réponse attendu à partir du type de question.
            type_reponse_attendu = determiner_type_reponse(question.type_question)

            # Insère une question dans la table questions.
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
                        obligatoire
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
                        :obligatoire
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
                    "type_reponse_attendu": type_reponse_attendu,
                    "obligatoire": question.obligatoire,
                },
            )

            # Récupère l’id interne généré pour cette question.
            question_db_id = resultat_question.scalar_one()

            # Parcourt les options de la question.
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

        # Valide définitivement toutes les insertions.
        session.commit()

        # Retourne l’id interne du formulaire enregistré.
        return formulaire_db_id
# Liste les questions textuelles que le modèle IA choisi peut traiter maintenant.
def lister_questions_textuelles_a_traiter(modele_ia: str) -> list[dict]:
    # Ouvre une session avec PostgreSQL.
    with SessionLocal() as session:

        # Cherche les questions textuelles qui n’ont pas encore de réponse
        # proposée par ce modèle précis.
        resultat = session.execute(
            text("""
                SELECT
                    q.id,
                    q.texte,
                    q.type_question,
                    q.type_reponse_attendu
                FROM questions q
                WHERE q.texte IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1
                    FROM reponses_proposees r
                    WHERE r.question_id = q.id
                    AND r.modele_ia = :modele_ia
                )
                ORDER BY q.id
            """),
            {
                "modele_ia": modele_ia,
            },
        )

        # Convertit les lignes SQL en dictionnaires Python.
        questions = resultat.mappings().all()

        # Retourne la liste des questions.
        return questions
