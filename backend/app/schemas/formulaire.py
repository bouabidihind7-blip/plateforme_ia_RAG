# Literal limite une valeur à une liste précise de choix autorisés.
from typing import Literal

# BaseModel crée les modèles de validation.
# Field ajoute des règles supplémentaires à certains champs.
# model_validator permet de vérifier la cohérence entre plusieurs champs.
from pydantic import BaseModel, Field, model_validator


# Représente une option appartenant à une question à choix.
class OptionFormulaire(BaseModel):

    # Identifiant obligatoire de l’option.
    # Exemple : "q2_opt1".
    option_id: str =Field(min_length=1)


    texte: str =Field(min_length=1)


# Résultat de l'OCR pour une question avec image (voir scripts_extraction/ocr_utils.py).
# Rempli uniquement quand modalite est "image" ou "texte_image" — sinon question.ocr vaut None.
class Ocr(BaseModel):
    texte_extrait: str | None = None
    score_confiance: float | None = None
    nb_mots: int | None = None
    erreur: str | None = None
    image_utilisee: str | None = None


# Une ligne de grille = une sous-question à part entière (ex : "Kdrama").
class GrilleLigne(BaseModel):
    ordre: int = Field(ge=1)
    texte: str = Field(min_length=1)


# Une colonne de grille = un choix de réponse partagé par toutes les lignes.
class GrilleColonne(BaseModel):
    texte: str = Field(min_length=1)


# Contenu d'une question de type grille_choix_unique/grille_choix_multiple.
# Remplace le champ "options" pour ces deux types (qui restent une liste vide).
class Grille(BaseModel):
    lignes: list[GrilleLigne] = Field(min_length=1)
    colonnes: list[GrilleColonne] = Field(min_length=1)


# Représente une question extraite d’un formulaire.
class QuestionFormulaire(BaseModel):
    question_id: str = Field(min_length=1)

    # Position de la question dans le formulaire.
    # ge=1 signifie "greater than or equal", donc supérieur ou égal à 1.
    ordre: int = Field(ge=1)

    # "inconnue" existe réellement (determiner_modalite dans extraction_questions.py peut la
    # produire) — absente ici avant, une vraie question aurait pu être rejetée à tort.
    modalite: Literal["texte", "image", "texte_image", "inconnue"]

    # Texte facultatif, car une question peut être uniquement visuelle.
    texte: str | None = None

    # Chemin ou URL facultative vers une image.
    image: str | None = None

    # Les 12 types réellement produits par l'extraction (mêmes valeurs que chk_question_type
    # côté SQL) — avant, seuls les 3 types MVP du tout début étaient acceptés.
    type_question: Literal[
        "texte_libre",
        "choix_unique",
        "choix_multiple",
        "notation",
        "echelle_lineaire",
        "date",
        "heure",
        "grille_choix_unique",
        "grille_choix_multiple",
        "depot_fichier",
        "classement",
        "type_inconnu",
    ]

    # Déjà calculé par determiner_type_reponse() dans extraction_questions.py — on le valide
    # ici (même liste que chk_question_type_reponse), pas besoin de le recalculer.
    type_reponse_attendu: Literal[
        "texte",
        "option_unique",
        "options_multiples",
        "date",
        "heure",
        "grille_option_unique",
        "grille_options_multiples",
        "hors_perimetre",
        "inconnu",
    ]

    # Indique si la réponse est obligatoire.
    obligatoire: bool

    # La question contient une liste d’options validées
    # avec le modèle OptionFormulaire.
    # default_factory crée une nouvelle liste vide pour chaque question.
    options: list[OptionFormulaire] = Field(default_factory=list)

    # Règle de validation détectée sur la question source (ex : "The value must be a number").
    contrainte: str | None = None

    # Texte final prêt pour l'IA (texte + OCR + reconstruction éventuelle) — voir
    # construire_prompt() dans ia_service.py, qui part directement de ce champ.
    texte_pour_ia: str | None = None

    # Rempli seulement si modalite vaut "image" ou "texte_image".
    ocr: Ocr | None = None

    # Rempli seulement pour les deux types grille_* (options reste vide dans ce cas).
    grille: Grille | None = None

    # Fiabilité de CETTE question, calculée par determiner_statut_extraction() — même liste
    # que chk_question_statut_extraction côté SQL.
    statut_extraction: Literal[
        "prete",
        "contenu_manquant",
        "texte_manquant",
        "ocr_echec",
        "ocr_incertain",
        "type_inconnu",
        "options_manquantes",
        "grille_manquante",
        "grille_incomplete",
        "hors_perimetre",
    ]

    # Vérifie la cohérence entre le type de question et ses options.
    #  @ ici c a d juste apres ,mode="after" signifie que Pydantic exécute cette fonction
    # après avoir contrôlé chaque champ séparément.
    @model_validator(mode="after")
    def verifier_options(self):
        # self= représente l’instance de QuestionFormulaire en cours de validation.
        # Une question à réponse libre ne doit pas proposer d’options.
        if self.type_question == "texte_libre" and self.options:
            raise ValueError(
                "Une question texte_libre ne doit pas avoir d’options."
            )

        # Les types grille utilisent le champ "grille", pas "options" — exclus ici, sinon ce
        # validateur les rejetterait à tort (ils ont options == []).
        types_a_choix = ("choix_unique", "choix_multiple", "notation", "echelle_lineaire", "classement")

        # Une question à choix doit obligatoirement proposer des options.
        if self.type_question in types_a_choix and not self.options:
            raise ValueError(
                "Une question à choix doit contenir au moins une option."
            )

        # Retourne la question lorsque toutes les règles sont respectées.
        return self

    # ANCIEN verifier_modalite() retiré : il exigeait un texte non vide dès que
    # modalite == "texte", mais une vraie question peut légitimement avoir modalite="texte" et
    # texte vide/absent — c'est exactement ce que statut_extraction="texte_manquant" signale.
    # Ce validateur aurait rejeté ces questions avant même qu'elles atteignent la base, alors
    # que le pipeline d'extraction les a volontairement laissées passer avec ce statut.


class Source(BaseModel):
    type: str | None = None
    url: str | None = None


class FormulaireEntree(BaseModel):
    # Identifiant obligatoire du formulaire.
    formulaire_id: str =Field(min_length=1)

    # "test" retiré : la contrainte SQL chk_formulaire_fournisseur ne l'accepte plus.
    fournisseur: Literal[
        "google_forms",
        "microsoft_forms",
    ]

    # Titre visible du formulaire — facultatif : la colonne BD elle-même n'a pas de NOT NULL
    # (voir database_scripts), un vrai formulaire sans titre détecté existe (bug réel trouvé
    # en testant, pas supposé) — construire_prompt (ia_service.py) gère déjà un titre absent.
    titre: str | None = None

    # D'où vient le formulaire (produit par extraire_formulaire_depuis_url).
    source: Source | None = None

    description: str | None = None
    date_extraction: str | None = None

    # Fiabilité globale de l'extraction, calculée par determiner_statut_formulaire() — même
    # liste que chk_formulaire_statut_extraction côté SQL.
    statut_extraction: Literal["vide", "prete", "partiel", "erreur"] | None = None

    # Liste des questions validées avec le modèle QuestionFormulaire.
    #
    questions: list[QuestionFormulaire] = Field(min_length=1)

    # Documents RAG (valeurs "source" exactes, voir GET /documents-rag) choisis par
    # l'utilisateur pour restreindre la recherche RAG à ce périmètre précis. None/vide = pas
    # de restriction (voir retrieve() dans retriever.py).
    documents_associes: list[str] | None = None
