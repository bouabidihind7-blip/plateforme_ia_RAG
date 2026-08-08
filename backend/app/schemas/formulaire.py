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

# Représente une question extraite d’un formulaire.
class QuestionFormulaire(BaseModel):
    question_id: str = Field(min_length=1)

    # Position de la question dans le formulaire.
    # ge=1 signifie "greater than or equal", donc supérieur ou égal à 1.
    ordre: int = Field(ge=1)

    # Seules ces trois modalités sont acceptées.
    # Toute autre valeur sera refusée par Pydantic.
    modalite: Literal["texte", "image", "texte_image"]

    # Texte facultatif, car une question peut être uniquement visuelle.
    texte: str | None = None

    # Chemin ou URL facultative vers une image.
    image: str | None = None

    # Limite les types de questions aux types du MVP.
    type_question: Literal[
        "texte_libre",
        "choix_unique",
        "choix_multiple",
    ]


    # Indique si la réponse est obligatoire.
    obligatoire: bool

    # La question contient une liste d’options validées
    # avec le modèle OptionFormulaire.
    # default_factory crée une nouvelle liste vide pour chaque question.
    options: list[OptionFormulaire] = Field(default_factory=list)
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

        # Une question à choix doit obligatoirement proposer des options.
        if self.type_question in ["choix_unique", "choix_multiple"] and not self.options:
            raise ValueError(
                "Une question à choix doit contenir au moins une option."
            )

        # Retourne la question lorsque toutes les règles sont respectées.
        return self
    #validateur pour image doit etre image ..
        # Vérifie que le contenu correspond à la modalité annoncée.
    @model_validator(mode="after")
    def verifier_modalite(self):

        # Si la modalité est image, une image doit être fournie.
        if self.modalite == "image" and not self.image:
            raise ValueError(
                "Le champ image doit être fourni pour la modalité image."
            )

        # Si la modalité est texte, un texte doit être fourni.
        if self.modalite == "texte" and not self.texte:
            raise ValueError(
                "Le champ texte doit être fourni pour la modalité texte."
            )

        # Si la modalité contient les deux, les deux champs sont obligatoires.
        if self.modalite == "texte_image" and (not self.texte or not self.image):
            raise ValueError(
                "Les champs texte et image doivent être fournis pour la modalité texte_image."
            )

        # Obligatoire : retourne la question après sa validation.
        return self
class FormulaireEntree(BaseModel):
    # Identifiant obligatoire du formulaire.
    formulaire_id: str =Field(min_length=1)
    # Origine du formulaire.
    fournisseur: Literal[
        "test",
        "google_forms",
        "microsoft_forms",
    ]
    # Titre visible du formulaire.
    titre: str =Field(min_length=1)
    # Liste des questions validées avec le modèle QuestionFormulaire.
    #
    questions: list[QuestionFormulaire] = Field(min_length=1)
