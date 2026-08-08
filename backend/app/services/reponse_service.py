# json permet de transformer une valeur Python en JSON pour PostgreSQL.
import json

# text permet d’écrire des requêtes SQL manuellement.
from sqlalchemy import text

# SessionLocal permet d’ouvrir une session avec PostgreSQL.
from backend.app.database import SessionLocal


# Enregistre une réponse proposée dans PostgreSQL.
def enregistrer_reponse_proposee(reponse: dict) -> int:
    # Ouvre une session avec la base de données.
    with SessionLocal() as session:

        # Insère la réponse proposée et récupère son id interne.
        resultat = session.execute(
            text("""
                INSERT INTO reponses_proposees (
                    question_id,
                    type_reponse,
                    valeur,
                    modele_ia,
                    methode_traitement
                )
                VALUES (
                    :question_id,
                    :type_reponse,
                    CAST(:valeur AS jsonb),
                    :modele_ia,
                    :methode_traitement
                )
                RETURNING id
            """),
            {
                "question_id": reponse["question_id"],
                "type_reponse": reponse["type_reponse"],
                "valeur": json.dumps(reponse["valeur"], ensure_ascii=False),
                "modele_ia": reponse["modele_ia"],
                "methode_traitement": reponse["methode_traitement"],
            },
        )

        # Récupère l’id généré par PostgreSQL.
        reponse_db_id = resultat.scalar_one()

        # Valide définitivement l’insertion.
        session.commit()

        # Retourne l’id interne de la réponse enregistrée.
        return reponse_db_id

# Liste les réponses proposées avec le texte de leur question.
def lister_reponses_proposees() -> list[dict]:
    # Ouvre une session avec PostgreSQL.
    with SessionLocal() as session:

        # Lit les réponses proposées et la question associée.
        resultat = session.execute(
            text("""
                SELECT
                    r.id,
                    r.question_id,
                    q.texte AS question,
                    r.type_reponse,
                    r.valeur,
                    r.modele_ia,
                    r.methode_traitement,
                    r.statut,
                    r.commentaire_validation,
                    r.date_generation,
                    r.date_modification
                FROM reponses_proposees r
                JOIN questions q ON q.id = r.question_id
                ORDER BY r.id
            """)
        )

        # Convertit les lignes SQL en dictionnaires Python.
        reponses = resultat.mappings().all()

        # Retourne les réponses.
        return reponses
    


# Modifie le statut d’une réponse proposée.
def modifier_statut_reponse(
    reponse_id: int,
    statut: str,
    commentaire: str | None = None,
) -> dict | None:
    # Ouvre une session avec PostgreSQL.
    with SessionLocal() as session:

        # Met à jour le statut et le commentaire de la réponse demandée.
        resultat = session.execute(
            text("""
                UPDATE reponses_proposees
                SET
                    statut = :statut,
                    commentaire_validation = :commentaire,
                    date_modification = CURRENT_TIMESTAMP
                WHERE id = :reponse_id
                RETURNING
                    id,
                    question_id,
                    type_reponse,
                    valeur,
                    modele_ia,
                    methode_traitement,
                    statut,
                    commentaire_validation,
                    date_modification
            """),
            {
                "reponse_id": reponse_id,
                "statut": statut,
                "commentaire": commentaire,
            },
        )

        # Récupère la réponse modifiée, ou None si l’id n’existe pas.
        reponse_modifiee = resultat.mappings().one_or_none()

        # Si aucune réponse n’a été trouvée, on ne valide rien.
        if reponse_modifiee is None:
            return None

        # Valide définitivement la modification.
        session.commit()

        # Retourne la réponse modifiée.
        return reponse_modifiee


# Liste les réponses proposées pour un formulaire précis.
def lister_reponses_par_formulaire(formulaire_id: int) -> list[dict]:
    # Ouvre une session avec PostgreSQL.
    with SessionLocal() as session:

        # Lit seulement les réponses liées aux questions de ce formulaire.
        resultat = session.execute(
            text("""
                SELECT
                    r.id,
                    r.question_id,
                    q.texte AS question,
                    r.type_reponse,
                    r.valeur,
                    r.modele_ia,
                    r.methode_traitement,
                    r.statut,
                    r.commentaire_validation,
                    r.date_generation,
                    r.date_modification
                FROM reponses_proposees r
                JOIN questions q ON q.id = r.question_id
                WHERE q.formulaire_id = :formulaire_id
                ORDER BY r.id
            """),
            {
                "formulaire_id": formulaire_id,
            },
        )

        # Convertit les lignes SQL en dictionnaires Python.
        reponses = resultat.mappings().all()

        # Retourne les réponses du formulaire demandé.
        return reponses
