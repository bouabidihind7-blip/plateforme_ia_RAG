-- =========================================================
-- Ce script REMPLACE entièrement le schéma créé par
-- 01_create_forms_schema.sql (gardé comme trace historique,
-- pas modifié). Raison : le pipeline d'extraction produit
-- maintenant beaucoup plus de types de questions et de champs
-- que ce que prévoyait le MVP initial (voir project_plan.md,
-- section "Types internes du MVP" vs le JSON réellement produit
-- par scripts_extraction/extraction_questions.py).
--
-- Aucune donnée de production à préserver à ce stade : on
-- supprime les anciennes tables et on recrée tout, plutôt que
-- d'empiler des ALTER TABLE (pas d'outil de migration comme
-- Alembic dans ce projet).
-- =========================================================

BEGIN;

-- Supprime les anciennes tables si elles existent, dans l'ordre
-- inverse des dépendances (une table enfant avant sa table parente).
DROP TABLE IF EXISTS reponses_proposees;
DROP TABLE IF EXISTS grille_colonnes;
DROP TABLE IF EXISTS grille_lignes;
DROP TABLE IF EXISTS options;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS formulaires;


-- =========================================================
-- TABLE 1 : FORMULAIRES
-- Contient les informations générales de chaque formulaire.
-- =========================================================

CREATE TABLE formulaires (
    -- Identifiant interne généré automatiquement par PostgreSQL.
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Identifiant reçu de Google, Microsoft ou de notre fichier de test.
    identifiant_externe VARCHAR(255) NOT NULL,

    -- Origine du formulaire. Une seule méthode d'extraction existe par
    -- fournisseur (google_forms → scraping public, microsoft_forms →
    -- scraping DOM) : pas besoin d'une colonne séparée pour la méthode,
    -- ce serait redondant avec ce champ.
    fournisseur VARCHAR(30) NOT NULL,

    -- Nom visible du formulaire.
    titre VARCHAR(255),

    -- Description du formulaire (correspond à "description" du JSON).
    description TEXT,

    -- Lien original du formulaire.
    -- Peut être vide pour un formulaire fictif local.
    url_source TEXT,

    -- Date/heure à laquelle le SCRIPT D'EXTRACTION a lu le formulaire
    -- (correspond à "date_extraction" du JSON — différente de
    -- date_creation ci-dessous, qui est la date d'enregistrement dans
    -- NOTRE base, pas celle de la lecture du formulaire source).
    date_extraction TIMESTAMP WITH TIME ZONE,

    -- Fiabilité globale de l'extraction, telle que calculée par
    -- determiner_statut_formulaire dans extraction_questions.py.
    -- Différent de "statut" ci-dessous : celui-ci décrit la QUALITÉ
    -- de l'extraction source, "statut" décrit où en est CE formulaire
    -- dans notre propre pipeline de traitement.
    statut_extraction VARCHAR(30),

    -- État actuel du traitement du formulaire dans notre plateforme.
    statut VARCHAR(30) NOT NULL DEFAULT 'importe',

    -- Date de création dans notre plateforme.
    date_creation TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Date de dernière modification.
    date_modification TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Empêche d’importer deux fois le même formulaire
    -- pour un même fournisseur.
    CONSTRAINT uq_formulaire_fournisseur_identifiant
        UNIQUE (fournisseur, identifiant_externe),

    -- Limite les fournisseurs aux valeurs connues.
    CONSTRAINT chk_formulaire_fournisseur
        CHECK (
            fournisseur IN (
                'google_forms',
                'microsoft_forms'
            )
        ),

    -- Limite les statuts d'extraction aux valeurs produites par
    -- determiner_statut_formulaire.
    CONSTRAINT chk_formulaire_statut_extraction
        CHECK (
            statut_extraction IS NULL
            OR statut_extraction IN (
                'vide',
                'prete',
                'partiel',
                'erreur'
            )
        ),

    -- Limite les statuts aux valeurs autorisées.
    CONSTRAINT chk_formulaire_statut
        CHECK (
            statut IN (
                'importe',
                'en_traitement',
                'termine',
                'erreur'
            )
        )
);


-- =========================================================
-- TABLE 2 : QUESTIONS
-- Contient toutes les questions extraites des formulaires.
-- =========================================================

CREATE TABLE questions (
    -- Identifiant interne de la question.
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Identifiant fourni par Google/Microsoft,
    -- ou défini dans notre formulaire fictif.
    identifiant_externe VARCHAR(255) NOT NULL,

    -- Formulaire auquel appartient la question.
    formulaire_id BIGINT NOT NULL,

    -- Position de la question dans le formulaire.
    ordre INTEGER NOT NULL,

    -- Contenu analysé : texte, image, les deux, ou inconnue.
    modalite VARCHAR(30) NOT NULL,

    -- Texte de la question.
    -- Peut être vide si la question est uniquement visuelle,
    -- ou pour une grille sans titre (voir chk_question_contenu).
    texte TEXT,

    -- Chemin ou URL de l’image associée.
    image TEXT,

    -- Fonctionnement de la question.
    type_question VARCHAR(30) NOT NULL,

    -- Format que devra respecter la réponse générée.
    type_reponse_attendu VARCHAR(30) NOT NULL,

    -- Indique si la question exige une réponse.
    obligatoire BOOLEAN NOT NULL DEFAULT FALSE,

    -- Règle de validation de contenu détectée sur la question source
    -- (ex : "The value must be a number", "doit contenir : adi").
    -- Utile pour que l'IA sache qu'un format précis est attendu.
    contrainte TEXT,

    -- Texte reconstruit prêt à être envoyé à l'IA (texte de la question
    -- éventuellement enrichi du texte OCR, de la reconstruction d'une
    -- grille sans titre, et/ou de la contrainte de validation) —
    -- correspond à "texte_pour_ia" du JSON. Stocké tel quel plutôt que
    -- recalculé à la demande, pour garder une trace exacte de ce que
    -- l'IA a vraiment reçu (traçabilité/audit).
    texte_pour_ia TEXT,

    -- Fiabilité de CETTE question précise, telle que calculée par
    -- determiner_statut_extraction dans extraction_questions.py.
    statut_extraction VARCHAR(30) NOT NULL DEFAULT 'prete',

    -- --- Champs OCR (remplis seulement si modalite IN ('image','texte_image')) ---
    -- Texte brut extrait de l'image par EasyOCR.
    ocr_texte_extrait TEXT,

    -- Score de confiance moyen d'EasyOCR (entre 0 et 1).
    ocr_score_confiance REAL,

    -- Nombre de morceaux de texte détectés par EasyOCR.
    ocr_nb_mots INTEGER,

    -- Message d'erreur éventuel de l'étape OCR (ex : timeout de sécurité
    -- si l'image était trop complexe à analyser).
    ocr_erreur TEXT,

    -- Nom du fichier de la variante d'image prétraitée qui a donné
    -- le meilleur résultat (ex : "..._debruite.png", "..._adaptatif_x4.png").
    ocr_image_utilisee TEXT,

    -- Date d’importation de la question.
    date_creation TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Relie la question à un formulaire existant.
    -- ON DELETE CASCADE supprime aussi ses questions
    -- si le formulaire est volontairement supprimé.
    CONSTRAINT fk_question_formulaire
        FOREIGN KEY (formulaire_id)
        REFERENCES formulaires(id)
        ON DELETE CASCADE,

    -- Une question ne peut pas avoir un ordre inférieur à 1.
    CONSTRAINT chk_question_ordre
        CHECK (ordre >= 1),

    -- Limite les modalités aux valeurs reconnues par determiner_modalite.
    CONSTRAINT chk_question_modalite
        CHECK (
            modalite IN (
                'texte',
                'image',
                'texte_image',
                'inconnue'
            )
        ),

    -- Limite les types de questions à ceux réellement produits par
    -- determiner_type_question (MVP + tous les types réels rencontrés
    -- en testant des formulaires Google/Microsoft réels).
    CONSTRAINT chk_question_type
        CHECK (
            type_question IN (
                'texte_libre',
                'choix_unique',
                'choix_multiple',
                'notation',
                'echelle_lineaire',
                'date',
                'heure',
                'grille_choix_unique',
                'grille_choix_multiple',
                'depot_fichier',
                'classement',
                'type_inconnu'
            )
        ),

    -- Limite les formats de réponses à ceux produits par
    -- determiner_type_reponse.
    CONSTRAINT chk_question_type_reponse
        CHECK (
            type_reponse_attendu IN (
                'texte',
                'option_unique',
                'options_multiples',
                'date',
                'heure',
                'grille_option_unique',
                'grille_options_multiples',
                'hors_perimetre',
                'inconnu'
            )
        ),

    -- Vérifie que le type de question correspond au type de réponse
    -- attendu, selon exactement la même table de correspondance que
    -- determiner_type_reponse() dans extraction_questions.py.
    CONSTRAINT chk_question_correspondance_types
        CHECK (
            (type_question = 'texte_libre' AND type_reponse_attendu = 'texte')
            OR (type_question = 'choix_unique' AND type_reponse_attendu = 'option_unique')
            OR (type_question = 'choix_multiple' AND type_reponse_attendu = 'options_multiples')
            OR (type_question = 'notation' AND type_reponse_attendu = 'option_unique')
            OR (type_question = 'echelle_lineaire' AND type_reponse_attendu = 'option_unique')
            OR (type_question = 'date' AND type_reponse_attendu = 'date')
            OR (type_question = 'heure' AND type_reponse_attendu = 'heure')
            OR (type_question = 'grille_choix_unique' AND type_reponse_attendu = 'grille_option_unique')
            OR (type_question = 'grille_choix_multiple' AND type_reponse_attendu = 'grille_options_multiples')
            OR (type_question = 'depot_fichier' AND type_reponse_attendu = 'hors_perimetre')
            OR (type_question = 'classement' AND type_reponse_attendu = 'options_multiples')
            OR (type_question = 'type_inconnu' AND type_reponse_attendu = 'inconnu')
        ),

    -- Une question doit contenir du texte, une image, ou les deux —
    -- SAUF une grille, dont le contenu vit dans grille_lignes/
    -- grille_colonnes et dont le titre général peut être vide
    -- (ex : "Grille sans titre" chez Google, texte NULL en pratique).
    CONSTRAINT chk_question_contenu
        CHECK (
            NULLIF(BTRIM(texte), '') IS NOT NULL
            OR image IS NOT NULL
            OR type_question IN ('grille_choix_unique', 'grille_choix_multiple')
        ),

    -- Limite le statut d'extraction aux valeurs produites par
    -- determiner_statut_extraction.
    CONSTRAINT chk_question_statut_extraction
        CHECK (
            statut_extraction IN (
                'prete',
                'contenu_manquant',
                'texte_manquant',
                'ocr_echec',
                'ocr_incertain',
                'type_inconnu',
                'options_manquantes',
                'grille_manquante',
                'grille_incomplete',
                'hors_perimetre'
            )
        ),

    -- Le score de confiance OCR est une proportion entre 0 et 1.
    CONSTRAINT chk_question_ocr_score
        CHECK (
            ocr_score_confiance IS NULL
            OR (ocr_score_confiance >= 0 AND ocr_score_confiance <= 1)
        ),

    -- Évite deux questions ayant le même identifiant externe
    -- dans un même formulaire.
    CONSTRAINT uq_question_formulaire_identifiant
        UNIQUE (formulaire_id, identifiant_externe),

    -- Évite deux questions à la même position.
    CONSTRAINT uq_question_formulaire_ordre
        UNIQUE (formulaire_id, ordre)
);


-- =========================================================
-- TABLE 3 : OPTIONS
-- Contient les choix disponibles pour une question à choix
-- (choix_unique, choix_multiple, notation, echelle_lineaire,
-- classement). Ne concerne PAS les grilles, qui ont leurs
-- propres tables (grille_lignes / grille_colonnes ci-dessous).
-- =========================================================

CREATE TABLE options (
    -- Identifiant interne de l’option.
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Identifiant externe ou identifiant du fichier de test.
    identifiant_externe VARCHAR(255) NOT NULL,

    -- Question à laquelle appartient l’option.
    question_id BIGINT NOT NULL,

    -- Position de l’option dans la question.
    ordre INTEGER NOT NULL,

    -- Texte affiché pour l’option.
    texte TEXT,

    -- Image éventuelle associée à l’option.
    image TEXT,

    -- Relie l’option à une question existante.
    CONSTRAINT fk_option_question
        FOREIGN KEY (question_id)
        REFERENCES questions(id)
        ON DELETE CASCADE,

    -- Une option ne peut pas avoir un ordre inférieur à 1.
    CONSTRAINT chk_option_ordre
        CHECK (ordre >= 1),

    -- Une option doit avoir au moins un texte ou une image.
    CONSTRAINT chk_option_contenu
        CHECK (
            NULLIF(BTRIM(texte), '') IS NOT NULL
            OR image IS NOT NULL
        ),

    -- Évite les identifiants externes dupliqués
    -- dans une même question.
    CONSTRAINT uq_option_question_identifiant
        UNIQUE (question_id, identifiant_externe),

    -- Évite deux options à la même position.
    CONSTRAINT uq_option_question_ordre
        UNIQUE (question_id, ordre)
);


-- =========================================================
-- TABLE 4 : GRILLE_LIGNES
-- Les lignes d'une question grille (grille_choix_unique ou
-- grille_choix_multiple) — chaque ligne est en pratique une
-- sous-question à part entière (ex : "Kdrama", "cdrama").
-- L'ordre compte ici, comme pour une question (voir project_plan.md,
-- section sur la décision de garder "ordre" sur les lignes).
-- =========================================================

CREATE TABLE grille_lignes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Question grille à laquelle appartient cette ligne.
    question_id BIGINT NOT NULL,

    -- Position de la ligne dans la grille.
    ordre INTEGER NOT NULL,

    -- Texte de la ligne (ex : "Kdrama").
    texte TEXT NOT NULL,

    CONSTRAINT fk_grille_ligne_question
        FOREIGN KEY (question_id)
        REFERENCES questions(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_grille_ligne_ordre
        CHECK (ordre >= 1),

    CONSTRAINT chk_grille_ligne_texte
        CHECK (NULLIF(BTRIM(texte), '') IS NOT NULL),

    CONSTRAINT uq_grille_ligne_question_ordre
        UNIQUE (question_id, ordre)
);


-- =========================================================
-- TABLE 5 : GRILLE_COLONNES
-- Les colonnes d'une question grille — l'équivalent des options
-- de réponse, partagées par toutes les lignes. Pas de champ
-- "ordre" ici (décision volontaire, voir project_plan.md) :
-- l'ordre des colonnes compte généralement moins que celui des
-- lignes, ce sont juste les choix de réponse disponibles.
-- =========================================================

CREATE TABLE grille_colonnes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Question grille à laquelle appartient cette colonne.
    question_id BIGINT NOT NULL,

    -- Texte de la colonne (ex : "Woo Khan").
    texte TEXT NOT NULL,

    CONSTRAINT fk_grille_colonne_question
        FOREIGN KEY (question_id)
        REFERENCES questions(id)
        ON DELETE CASCADE,

    CONSTRAINT chk_grille_colonne_texte
        CHECK (NULLIF(BTRIM(texte), '') IS NOT NULL),

    -- Évite d'enregistrer deux fois la même colonne pour une
    -- même question.
    CONSTRAINT uq_grille_colonne_question_texte
        UNIQUE (question_id, texte)
);


-- =========================================================
-- TABLE 6 : REPONSES PROPOSEES
-- Contient les réponses générées par l’IA.
--
-- PAS ENCORE ÉTENDUE aux nouveaux types de questions (date,
-- heure, grille, notation...) : ia_service.py ne sait pour
-- l'instant générer des réponses que pour les 3 types MVP.
-- Étendre cette table est une tâche séparée, à faire quand
-- la génération de réponses pour ces types sera construite —
-- pas de sens à deviner la forme des futures réponses sans
-- ce travail fait d'abord.
-- =========================================================

CREATE TABLE reponses_proposees (
    -- Identifiant interne de la proposition.
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Question à laquelle répond la proposition.
    question_id BIGINT NOT NULL,

    -- Forme de la valeur enregistrée.
    type_reponse VARCHAR(30) NOT NULL,

    -- Réponse au format JSONB.
    -- Elle peut être une chaîne, une liste ou rester vide en cas d’erreur.
    valeur JSONB,

    -- Nom du modèle ayant produit la réponse.
    modele_ia VARCHAR(100) NOT NULL,

    -- Méthode utilisée pour comprendre la question.
    methode_traitement VARCHAR(30) NOT NULL,

    -- État de la réponse proposée.
    statut VARCHAR(30) NOT NULL DEFAULT 'proposee',

    -- Message technique éventuel en cas d’échec.
    erreur TEXT,

    -- Commentaire laissé par la personne qui valide/rejette la réponse.
    commentaire_validation TEXT,

    -- Date de génération.
    date_generation TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Date de dernière modification ou validation.
    date_modification TIMESTAMP WITH TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Relie la proposition à une question existante.
    CONSTRAINT fk_reponse_question
        FOREIGN KEY (question_id)
        REFERENCES questions(id)
        ON DELETE CASCADE,

    -- Limite les types de réponses.
    CONSTRAINT chk_reponse_type
        CHECK (
            type_reponse IN (
                'texte',
                'option_unique',
                'options_multiples'
            )
        ),

    -- Limite les méthodes de traitement.
    CONSTRAINT chk_reponse_methode
        CHECK (
            methode_traitement IN (
                'texte',
                'ocr_texte'
            )
        ),

    -- Limite les statuts possibles.
    CONSTRAINT chk_reponse_statut
        CHECK (
            statut IN (
                'proposee',
                'validee',
                'rejetee',
                'erreur',
                'humaine_requise'
            )
        ),

    -- Vérifie la structure JSON selon le type de réponse.
    CONSTRAINT chk_reponse_format_valeur
        CHECK (
            valeur IS NULL
            OR (
                type_reponse IN ('texte', 'option_unique')
                AND jsonb_typeof(valeur) = 'string'
            )
            OR (
                type_reponse = 'options_multiples'
                AND jsonb_typeof(valeur) = 'array'
            )
        ),

    -- Une réponse normale doit avoir une valeur.
    -- Les statuts d’erreur ou d’intervention humaine peuvent rester vides.
    CONSTRAINT chk_reponse_valeur_statut
        CHECK (
            (
                statut IN ('erreur', 'humaine_requise')
                AND valeur IS NULL
            )
            OR
            (
                statut NOT IN ('erreur', 'humaine_requise')
                AND valeur IS NOT NULL
            )
        )
);


-- Accélère la recherche des questions d’un formulaire.
CREATE INDEX idx_questions_formulaire
    ON questions(formulaire_id);

-- Accélère la recherche des options d’une question.
CREATE INDEX idx_options_question
    ON options(question_id);

-- Accélère la recherche des lignes/colonnes d'une grille.
CREATE INDEX idx_grille_lignes_question
    ON grille_lignes(question_id);

CREATE INDEX idx_grille_colonnes_question
    ON grille_colonnes(question_id);

-- Accélère la recherche des réponses d’une question.
CREATE INDEX idx_reponses_question
    ON reponses_proposees(question_id);

-- Valide définitivement toutes les créations.
COMMIT;
