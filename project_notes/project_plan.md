# Types internes du MVP

## Modalités
- texte
- image
- texte_image

## Types de questions
- texte_libre
- choix_unique
- choix_multiple

## Types de réponses
- texte
- option_unique
- options_multiples

## Hors périmètre initial
- questions personnelles
- questions subjectives
- dépôt de fichier
- remplissage automatique du formulaire



            ##   Résumé des services backend

database.py
- Prépare la connexion avec PostgreSQL.
- Crée SessionLocal, utilisé pour ouvrir une session avec la base de données.

formulaire_service.py
- Enregistre les formulaires validés dans PostgreSQL.
- Enregistre aussi leurs questions et leurs options.
- Liste les questions textuelles qui n’ont pas encore de réponse proposée.

ia_service.py
- Propose une réponse pour une question.
- Pour l’instant, c’est une IA de test.
- Plus tard, ce fichier contiendra l’appel à une vraie IA comme OpenAI, Gemini ou Claude.

reponse_service.py
- Enregistre les réponses proposées dans la table reponses_proposees.
- Transforme la valeur de réponse en JSON compatible avec PostgreSQL.

traitement_service.py
- Coordonne tout le traitement.
- Lit les questions à traiter.
- Demande une réponse au service IA.
- Enregistre chaque réponse proposée dans PostgreSQL.

main.py
- Contient les routes FastAPI.
- Reçoit les requêtes depuis Swagger, frontend ou autre client.
- Appelle les services nécessaires.


## Nouvelle orientation du projet : extraction avant backend

Après discussion avec l’encadrant, la priorité n’est pas de commencer directement par la base de données, le backend ou le frontend.

La priorité actuelle est de construire et tester les scripts capables d’extraire correctement les questions depuis les formulaires.

Objectif de cette phase :
- extraire les questions depuis un formulaire ;
- reconnaître le type de question ;
- reconnaître le type de réponse attendu ;
- gérer les questions texte, image et texte + image ;
- produire un JSON standard propre ;
- utiliser ce JSON plus tard pour concevoir la base de données, le backend et le frontend.


## Rôle des fichiers d’extraction

google_forms_public.py
- Lit un formulaire Google Forms public à partir de son lien.
- Récupère le titre du formulaire.
- Récupère la description.
- Récupère les questions.
- Récupère les options.
- Reconnaît certains types Google Forms : texte, choix unique, choix multiple, liste déroulante, date, heure, notation, échelle linéaire et grilles.
- Son rôle est spécifique à Google Forms.

extraction_questions.py
- Ne dépend pas seulement de Google Forms.
- Transforme une question brute en question standard.
- Détermine la modalité : texte, image ou texte_image.
- Détermine le type de question.
- Détermine le type de réponse attendu.
- Prépare le champ texte_pour_ia.
- Produit le format JSON final utilisé par le pipeline.

ocr_utils.py
- Traite les images.
- Utilise EasyOCR pour extraire le texte depuis une image.
- Applique plusieurs prétraitements pour améliorer la lecture OCR.
- Retourne le texte extrait, le score de confiance et l’image utilisée.

test_extraction_texte.py
- Sert à tester quelques questions simples simulées.
- Ce fichier est utilisé seulement pour vérifier la logique d’extraction.

test_extraction_formulaire.py
- Sert à tester un formulaire complet simulé.
- Il permet de vérifier si le JSON final est cohérent avant de travailler avec de vrais formulaires.

test_ocr.py
- Sert à tester OCR sur une image locale.
- Il permet de vérifier si EasyOCR lit correctement le contenu d’une image.


## Pipeline actuel d’extraction

Le pipeline actuel est :

```text
Lien Google Forms
    ↓
google_forms_public.py
    ↓
questions brutes extraites depuis Google Forms
    ↓
extraction_questions.py
    ↓
JSON standard
    ↓
si question avec image : ocr_utils.py extrait le texte de l’image
    ↓
texte_pour_ia
```


## OCR : objectif

OCR signifie Optical Character Recognition.

Son rôle dans notre projet est de lire le texte présent dans une image.

Exemple :

```text
image contenant : "Combien font 7 x 8 ?"
    ↓
OCR
    ↓
"Combien font 7 x 8 ?"
```

L’OCR est nécessaire parce que certaines questions peuvent être sous forme d’image ou contenir une image avec du texte.


## Limites observées avec OCR

Les tests ont montré que OCR fonctionne très bien avec :
- texte clair ;
- texte assez grand ;
- fond simple ;
- bon contraste ;
- image nette.

OCR fonctionne moins bien avec :
- texte stylisé ;
- image décorative ;
- texte doré ou avec ombres ;
- fond complexe ;
- petit texte ;
- image floue ;
- image inclinée ;
- logos ou objets proches des lettres.

Exemple observé :
- une image simple avec texte clair donne un score proche de 0.98 ;
- une image décorative comme une affiche peut donner un score faible et un texte mal extrait.

Conclusion :
- OCR doit être utilisé avec un score de confiance ;
- si le score est faible, il faut considérer le résultat comme incertain ;
- une validation humaine peut être nécessaire dans les cas difficiles.


## Prétraitements OCR utilisés

Le fichier ocr_utils.py crée plusieurs versions de la même image.

Chaque version est testée par EasyOCR, puis le système garde le meilleur résultat.

Prétraitements utilisés :

1. Image originale
- On garde toujours l’image originale.
- Parfois elle donne le meilleur résultat.

2. Niveaux de gris
- Convertit l’image couleur en image grise.
- Les couleurs sont souvent inutiles pour OCR.
- OCR travaille surtout sur la forme des lettres.

3. Débruitage
- Réduit les petits points parasites et le bruit visuel.
- Le débruitage est appliqué avant le seuillage.
- Cela évite de transformer le bruit en faux caractères.

4. Correction d’inclinaison
- Essaie de redresser une image si le texte est penché.
- Utile pour les photos ou scans légèrement inclinés.
- OCR lit mieux les lignes horizontales.

5. Agrandissement
- Agrandit l’image pour rendre les lettres plus lisibles.
- Utile quand le texte est petit.

6. CLAHE
- Améliore le contraste localement.
- Plus doux que equalizeHist.
- Évite de trop modifier les zones déjà lisibles.

7. Seuillage Otsu
- Transforme l’image en noir et blanc.
- Fonctionne bien quand l’éclairage est uniforme.

8. Seuillage adaptatif
- Transforme aussi l’image en noir et blanc.
- Fonctionne mieux quand l’éclairage est inégal ou quand il y a des ombres.

9. Netteté
- Renforce les contours des lettres.
- Peut aider sur les images légèrement floues.

10. Inversion noir/blanc
- Inverse les couleurs.
- Utile si le texte est clair sur un fond foncé.


## Différence entre la première version OCR et la version améliorée

Première version :
- EasyOCR Reader était recréé à chaque appel.
- Cela rendait le test très lent.
- Le contraste était amélioré avec equalizeHist, parfois trop agressif.
- Le système utilisait surtout Otsu comme seuillage.
- Certains flous étaient appliqués après la binarisation, ce qui pouvait abîmer les lettres.
- Le meilleur résultat était choisi seulement selon le score moyen.
- Un petit texte mal extrait comme "106" pouvait gagner s’il avait un score plus élevé.

Version améliorée :
- EasyOCR Reader est créé une seule fois puis réutilisé.
- Le débruitage est fait avant le seuillage.
- CLAHE remplace equalizeHist pour un contraste plus stable.
- Le système teste Otsu et le seuillage adaptatif.
- Une correction d’inclinaison est ajoutée.
- Une version plus nette de l’image est testée.
- Le meilleur résultat est choisi avec un score pondéré.
- Le score pondéré prend en compte la confiance OCR et la quantité de texte détectée.


## Pourquoi le score pondéré est important

Choisir seulement le score moyen peut être trompeur.

Exemple :

```text
"106" avec 0.66 de confiance
```

peut être moins utile que :

```text
"100% LOGIQUE LA REPONSE EST SOUS VOS YEUX" avec 0.39 de confiance
```

Même si le premier résultat a une meilleure confiance, il est trop incomplet.

Donc la version améliorée utilise :
- le score de confiance ;
- la longueur du texte extrait.

Cela permet de choisir un résultat plus complet.


## Règle importante pour la suite

OCR ne garantit pas toujours une extraction parfaite.

La bonne stratégie du projet est :

```text
image claire
    ↓
OCR fiable
    ↓
utilisable par l’IA
```

Mais :

```text
image complexe ou score faible
    ↓
OCR incertain
    ↓
validation humaine ou traitement complémentaire
```

Cette logique respecte l’objectif du projet : automatiser, mais garder une injection contrôlée et traçable.


## Passage à l'API officielle Google Forms

Le scraping HTML (`google_forms_public.py`) fonctionnait, mais reposait sur une variable
JavaScript interne non documentée (`FB_PUBLIC_LOAD_DATA_`) et des codes numériques devinés.
Risque réel : si Google change la structure de la page, l'extraction casse sans prévenir.

Deux actions ont été faites :

1. **Rendre le scraping existant plus sûr** (`google_forms_public.py`) : ajout de vérifications
   explicites à chaque endroit où le code lit une structure supposée (titre, questions, grilles).
   En cas de structure inattendue, le script échoue maintenant avec un message clair au lieu
   d'un `IndexError` cryptique ou d'un JSON silencieusement faux. Ajout aussi d'un filtrage des
   éléments qui ne sont pas de vraies questions (titres de section, sauts de page).

2. **Créer un nouveau chemin d'extraction via l'API officielle** (`google_forms_api.py`) :
   authentification OAuth2 (identifiants dans `scripts_extraction/google_forms_credentials.json`,
   ignoré par git), appel à `forms.googleapis.com`, qui renvoie un JSON documenté et stable
   (`items[]` avec `questionItem`, `questionGroupItem` pour les grilles, `pageBreakItem`/`textItem`
   pour les éléments non-questions qui sont ignorés proprement).

   Contrainte acceptée : contrairement au scraping public, l'API ne peut lire que les
   formulaires auxquels le compte Google authentifié a accès (pas n'importe quel lien public).

   Avantages obtenus directement grâce à l'API, qui manquaient avant : le champ `obligatoire`
   (`required`) et un identifiant stable par question (`questionId`), tous les deux absents du
   JSON produit par le scraping HTML.

Testé avec un vrai formulaire construit pour couvrir tous les cas
(`test_documents/formulaire_google_extrait_reel.json`) : texte libre, choix unique, choix
multiple, échelle linéaire, date, heure, grille à choix unique, grille à choix multiple, et
dépôt de fichier. Résultat : `statut_extraction` global = `"prete"`.

Bugs trouvés et corrigés pendant ce test réel :
- **Échelle linéaire** : Google donne un intervalle (`low`/`high`), pas une liste d'options
  toute faite. `convertir_type_question_api` reconstruit maintenant les options depuis cet
  intervalle (sinon : `statut_extraction: "options_manquantes"` à tort).
- **Dépôt de fichier** : nouveau type `depot_fichier`, reconnu distinctement (nouveau statut
  `hors_perimetre`) plutôt que confondu avec du texte manquant. C'est un choix de périmètre
  assumé (voir "Hors périmètre initial" plus haut) : une IA ne peut pas générer un fichier à
  la place d'un humain, donc aucune génération de réponse n'est tentée pour ce type.
- **Grille sans titre** : Google affiche "Question" par défaut si le titre général d'une grille
  n'est pas rempli ; `texte_pour_ia` était alors `null`. Nouvelle fonction
  `construire_texte_pour_ia` qui reconstruit un texte exploitable à partir des lignes et
  colonnes de la grille quand le titre est vide.
- **Statut global du formulaire** : les questions `hors_perimetre` (dépôt de fichier) ne
  doivent pas faire passer le statut global à `"partiel"` — ce n'est pas un échec d'extraction,
  c'est une exclusion volontaire. `determiner_statut_formulaire` les exclut maintenant du calcul.


## Branchement de l'OCR dans le pipeline principal

Jusqu'ici, `extraction_questions.py` mettait toujours `"image": None, "ocr": None` en dur,
même si `ocr_utils.py` fonctionnait très bien en standalone. Le branchement complet a été fait :

- Quand la modalité est `image` ou `texte_image` et qu'un chemin d'image est fourni,
  `extraire_question_textuelle` appelle `extraire_texte_image` (import différé, pour ne pas
  charger OpenCV/EasyOCR sur les formulaires purement textuels).
- Nouveau statut `ocr_echec` (aucun texte détecté) et `ocr_incertain` (texte détecté mais
  confiance sous le seuil `SEUIL_CONFIANCE_OCR_FIABLE = 0.6`), en plus de `prete`.
- `construire_texte_pour_ia` combine le texte de la question et le texte OCR pour une
  question `texte_image`, ou utilise seulement l'OCR pour une question `image` pure.
- **Téléchargement des images réelles** (`google_forms_api.py`) : Google fournit une URL
  temporaire (`contentUri`, valable ~30 minutes) pour l'image d'une question. Une session
  authentifiée (`AuthorizedSession`) télécharge l'image dans
  `scripts_extraction/images_formulaires/` (ignoré par git) avant de la passer à l'OCR. Un
  échec de téléchargement (réseau, URL expirée) ne bloque pas le reste de l'extraction : la
  question concernée a juste `image: None`.

## Optimisation de la vitesse OCR

Le premier test (`ocr_utils.py` avant optimisation) prenait **5min41s pour une seule image**,
car 20 versions prétraitées de l'image étaient systématiquement toutes testées par EasyOCR,
en CPU (pas de GPU disponible sur la machine de développement).

Trois optimisations, testées sur plusieurs images réelles (`images_test/test1.png`,
`test2.png`, `test3.png`, en plus des images déjà présentes) :

1. **Sortie anticipée après la passe rapide** (8 variantes : originale, gris, débruitée,
   redressée, x2) : si la confiance dépasse `SEUIL_SCORE_SUFFISANT = 0.85`, on s'arrête sans
   calculer ni tester les 12 variantes coûteuses restantes (x4, netteté, inversion...).
   Important : la comparaison se fait sur la confiance brute d'EasyOCR, pas sur le score
   pondéré (qui pénalise les textes courts et aurait empêché la sortie anticipée sur de
   petites questions pourtant bien lues).
2. **Sortie anticipée aussi pendant la passe coûteuse** : dès qu'une variante de la passe
   coûteuse atteint le seuil, on arrête sans tester les variantes x4 restantes.
3. **Seuil de tentative (`SEUIL_TENTATIVE_VARIANTES_COUTEUSES = 0.55`)** : si la passe rapide
   donne déjà un score au-dessus de ce seuil, on n'essaie même pas les variantes coûteuses.
   Décision fondée sur des données réelles : sur 5 images testées, la variante gagnante venait
   de la passe rapide dans 4 cas sur 5 (confiances 0.64 à 0.94) ; les variantes coûteuses
   n'ont apporté un gain que sur l'image la plus difficile (une affiche décorative, passe
   rapide seule à 0.53, gain marginal à 0.59 avec `contraste_x4`). Comme un résultat sous
   0.85 est de toute façon signalé pour validation humaine, chercher un gain marginal ne
   valait pas le coût en temps.

Résultat mesuré : **test2.png : 255s → 39s** (~6,5x plus rapide), même résultat exact, aucune
perte de qualité. Les images faciles (`question_facile.png`) descendent à ~20s.


## Découverte stratégique : API officielle Google vs scraping public

Après validation avec l'encadrant du vrai objectif ("l'entreprise reçoit des formulaires
externes à remplir automatiquement, ex : nom, chiffre d'affaires..."), on a découvert une
limite fondamentale de `google_forms_api.py` : **l'API officielle Google Forms exige que le
compte authentifié soit éditeur/lecteur du formulaire dans Google Drive**. Un simple lien de
réponse public ne suffit pas. Confirmé par la documentation Google et des retours de
développeurs (`PERMISSION_DENIED` si le compte n'est pas explicitement ajouté par le
propriétaire).

Conséquence : pour le vrai cas d'usage (formulaire envoyé par un client/fournisseur externe,
qui n'ajoutera jamais l'entreprise comme éditeur), **`google_forms_api.py` ne peut pas
fonctionner**. C'est `google_forms_public.py` (scraping du lien public) qui est le module
réellement utilisable pour ce scénario. `google_forms_api.py` reste utile uniquement pour les
formulaires que l'entreprise possède elle-même (cas secondaire).

`google_forms_public.py` a donc été remis au niveau de qualité de la version API :
téléchargement des images des questions (les identifiants trouvés dans les données brutes ne
sont pas réutilisables comme URL — il faut lire les vraies URLs `lh7-rt.googleusercontent.com`
directement dans le HTML rendu, associées aux questions par ordre d'apparition).


## Limite définitive : formulaires avec dépôt de fichier (Google)

Découverte en testant plusieurs vrais formulaires : certains donnent une erreur **HTTP 401**
lors du simple téléchargement de la page, avant même de lire une question.

**Cause identifiée et confirmée par la documentation Google** : dès qu'un formulaire contient
une question de type "dépôt de fichier", Google **exige que tout visiteur soit connecté** à un
compte Google pour voir la page — y compris juste pour la consulter, pas seulement pour y
répondre. Ce réglage ne peut pas être désactivé par le créateur du formulaire. Confirmé en
supprimant la question d'un formulaire de test : l'accès redevient immédiatement possible.

**Tentative de contournement (navigateur automatisé connecté)** : `telecharger_html_connecte`
(Playwright) a été codée pour se connecter avec un vrai compte Google et réutiliser cette
session pour lire la page. Testée en conditions réelles : **Google détecte et bloque la
tentative de connexion** ("Couldn't sign you in - This browser or app may not be secure"),
une mesure de sécurité anti-bot volontaire. Décision : ne pas chercher à contourner cette
détection plus loin (fragile, zone grise vis-à-vis des conditions d'utilisation de Google,
risque de blocage de compte). La fonction est gardée dans le code, documentée comme non
fonctionnelle, pour garder une trace de la tentative.

**Conclusion, validée dans l'esprit du projet** : ce n'est pas un problème technique à
résoudre — c'est une frontière de sécurité posée délibérément par Google. Aucune app, aussi
bien identifiée soit-elle auprès de Google (voir le mécanisme OAuth déjà en place pour
`google_forms_api.py`), n'obtient de droits sur un formulaire sans l'accord explicite de son
propriétaire — l'identité de l'application n'y change rien, seule la permission accordée par
le propriétaire du formulaire compte.

**Solution retenue** : traiter ce cas comme une exception connue et prévisible, pas comme un
échec silencieux — cohérent avec le reste du pipeline (`ocr_incertain`, `hors_perimetre`) :
- `telecharger_html` détecte le 401 et lève une erreur claire et explicite plutôt que de
  planter avec une trace Python illisible.
- Un tel formulaire nécessite un traitement manuel (saisie humaine du contenu).
- Recommandation business à l'encadrant : pour les partenaires/fournisseurs réguliers (pas des
  formulaires publics anonymes), demander explicitement l'accès éditeur sur les formulaires
  envoyés — ça débloquerait `google_forms_api.py`, qui n'a pas cette limite (pas de scraping
  HTML, donc pas de blocage 401 lié au dépôt de fichier).


## Recherche : accès officiel à Microsoft Forms

Contrairement à Google, Microsoft n'offre **aucun accès officiel documenté** pour lire la
structure d'un formulaire (ses questions, types, options). Recherche faite sur toutes les pistes
officielles disponibles (validé avec l'encadrant) :

- **Power Automate / Logic Apps — connecteur Microsoft Forms** (documenté sur Microsoft Learn) :
  `Get form details` ne retourne que `title`, `createdDate`, `modifiedDate`, `status`,
  `createdBy` — aucune question. `Get response details` et le déclencheur "When a new response
  is submitted" ne donnent accès qu'à des **réponses déjà soumises**, pas à la définition des
  questions avant qu'un humain y réponde. Incompatible avec l'objectif du projet (l'IA doit
  répondre avant qu'un humain le fasse).
- **Microsoft Graph API (beta)** : `formsSettings`/`adminForms` existent, mais ne concernent que
  des réglages d'organisation (ex. "les formulaires peuvent-ils être partagés en externe ?"),
  aucun rapport avec le contenu d'un formulaire. Pas d'endpoint Graph pour lire les questions.
- **Export Excel** : exporte les réponses, pas la structure. Bug documenté par Microsoft : pour
  les questions à choix, l'en-tête de colonne ne montre même pas le texte de la question. Aucune
  info sur le type de question ni sur `obligatoire`. Écarté.
- **Dynamics 365 Customer Voice** (ex-Forms Pro) : produit différent, payant, orienté enquêtes
  clients — hors sujet ici.

**Décision initiale (dépassée depuis, voir section suivante)** : la piste envisagée à ce
moment-là était l'endpoint interne non documenté
`forms.office.com/formapi/api/forms/{formId}/questions`, avec authentification OAuth2/MSAL
(inscription d'application Azure AD). Cette piste a été **abandonnée** — voir
"Microsoft Forms : abandon de l'API, passage au scraping DOM" ci-dessous.


## Microsoft Forms : abandon de l'API, passage au scraping DOM (Playwright)

L'inscription d'application Azure AD nécessaire à `microsoft_forms_api.py` (piste décrite
ci-dessus) s'est heurtée à un blocage systématique : **AADSTS50020** ("le compte n'existe pas
dans l'annuaire Microsoft Services") et des popups "Interaction requise", reproduits sur
plusieurs comptes Microsoft personnels différents (le compte de Hind, puis celui d'une amie).
Comptes personnels (MSA) sans tenant M365/Entra réel ne peuvent pas créer d'inscription
d'application. Cette piste a été abandonnée après plusieurs jours de blocage, sans solution
trouvée — ce n'est pas un problème résolu, juste une impasse constatée.

Sur indication directe de l'encadrant ("le web scraping fait tout ça"), pivot vers le
**scraping DOM via navigateur automatisé (Playwright)** de la page de réponse publique — même
principe que `google_forms_public.py`, mais en lisant le HTML **rendu par le JavaScript** (pas
de variable style `FB_PUBLIC_LOAD_DATA_` embarquée côté serveur pour Microsoft Forms : tout est
construit côté client). Nouveau module : `microsoft_forms_scraper.py`.

Fonctionnement général :
1. Ouvre la page publique dans un vrai Chromium (headless), sans authentification.
2. Clique sur "Start now" si une page de garde existe (voir plus bas).
3. Lit les questions visibles (`data-automation-id="questionItem"`), en s'appuyant sur un texte
   d'accessibilité caché ("Single line text.", "Date.", "Single choice.", "Ranking.", "Net
   Promoter Score.", "Likert.") pour déterminer le type de façon fiable plutôt que deviner
   depuis la structure brute.
4. Remplit des réponses factices pour satisfaire la validation "obligatoire" et avancer d'une
   section à l'autre (bouton "Next") — **jamais de clic sur "Submit"**, aucune vraie réponse
   n'est donc envoyée au propriétaire du formulaire.
5. Répète jusqu'à ce qu'il n'y ait plus de bouton "Next".

Testé avec succès sur plusieurs formulaires réels couvrant tous les types rencontrés : texte
libre, date, heure, choix unique, choix multiple, notation (étoiles/trophées/rubans),
classement (ranking), échelle NPS, grille Likert, question avec image, et menu déroulant.

### Bugs trouvés et corrigés en testant sur des formulaires réels

- **Pagination bloquée silencieusement** : sur un formulaire réel, le script restait coincé sur
  la première section indéfiniment. Cause trouvée par diagnostic direct (lecture du message
  d'alerte de validation Microsoft) : le remplissage factice échouait sur deux types de champs.
  - Champ texte : le sélecteur `input[type="text"]` ne matchait pas, car ce formulaire précis
    rend l'input **sans attribut `type` du tout** (valide en HTML, le navigateur le traite comme
    texte par défaut, mais un sélecteur CSS `[type="text"]` exige que l'attribut soit écrit
    explicitement). Corrigé en ciblant `[data-automation-id="textInput"]` à la place (plus
    robuste, indépendant de la présence de l'attribut `type`).
  - Choix unique : `dispatch_event("click")` sur le conteneur `choiceItem` ne mettait jamais
    `aria-checked` à vrai (donc jamais pris en compte par la validation), sans lever d'erreur.
    Corrigé en ciblant directement l'`<input type="radio">` à l'intérieur, avec un vrai `.click()`
    plutôt que `dispatch_event`.
- **Grilles Likert non reconnues** : une question de type "Likert." (tableau avec une ligne à
  évaluer par `<tr>`, une colonne par `<th>`, un `role="radiogroup"` par ligne) était traitée
  comme du texte libre vide. Ajout de `extraire_grille_microsoft` (même principe que la grille
  Google : lignes + colonnes), et du type `grille_choix_unique` dans la table de correspondance.
- **Page de garde ("Start now") ignorée** : certains formulaires affichent un écran d'accueil
  (titre, description, image/vidéo de fond, bouton "Start now") avant la première question.
  Sans gérer ce cas, l'extraction ne trouvait **aucune question du tout** (0 résultat, aucune
  erreur). Corrigé en cliquant sur ce bouton s'il existe, avant de commencer le parcours des
  sections. Testé et confirmé insensible au changement de style visuel, à l'ajout d'une musique
  de fond, ou à une image de couverture — seule la présence du bouton compte.
- **Images de question non supportées** : contrairement au texte de la question et aux options,
  aucune image n'était téléchargée pour les questions qui en contiennent une (ex : capture
  d'écran donnant du contexte à la question). Ajouté `telecharger_image_question` (même
  principe que pour Google : téléchargement direct, sans authentification nécessaire, vérifié
  en réel sur les domaines `hive.forms.usercontent.microsoft` et
  `cdn.hubblecontent.osi.office.net`) et branchement automatique de l'OCR déjà existant.
- **Menus déroulants ("Select your answer")** : une question à choix unique peut être rendue
  comme un menu déroulant personnalisé (`role="button"` + `aria-haspopup="listbox"`) plutôt que
  des boutons radio visibles. Ses options **n'existent pas du tout** dans le HTML tant qu'on n'a
  pas cliqué pour les révéler — impossible à lire après coup comme les autres types. Piège
  rencontré : une fois ouvertes, les options se mélangent avec celles d'une autre question
  déjà présente sur la page (ex : une question de classement plus bas), si on cherche
  simplement tous les éléments `role="option"` de la page. Solution : comparer les éléments
  `role="option"` juste avant et juste après le clic — seules les nouvelles apparues
  appartiennent au menu qu'on vient d'ouvrir. Le menu est refermé (touche Echap) avant de passer
  au suivant. Nouvelle fonction `extraire_options_menus_deroulants_page`, appelée avant chaque
  capture de page dans `telecharger_pages_rendues`.
- **Validation de contenu sur un champ texte** (ex : "le texte doit contenir tel mot") bloquant
  la pagination indéfiniment : un champ texte avec une règle personnalisée (Microsoft Forms
  permet d'exiger qu'une réponse contienne un mot précis) rejette systématiquement la valeur
  factice fixe ("test"), donc le clic "Next" échoue en boucle et une section entière (et ses
  questions) reste invisible. Le message d'erreur exact ("Please enter text that contains adi")
  s'affiche **à l'intérieur du bloc de la question concernée** (vérifié : jamais dans le bloc
  d'une autre question), ce qui permet de le détecter de façon fiable et de l'associer à la
  bonne question. Corrigé dans `remplir_reponse_factice` : si une telle alerte est présente
  dans le bloc, le mot requis est extrait par expression régulière et injecté dans la valeur
  factice (`"test {mot}"`) avant de retenter. Portée volontairement limitée à cette règle précise
  ("contains X") : d'autres règles possibles (longueur, format e-mail, expression régulière) ne
  sont pas gérées, faute d'exemple concret pour les tester.
- **Titres de section** ("personnal info", "Favorite things", sans image ni numéro) : à la
  différence de Google Forms (voir plus bas), ces blocs **n'ont jamais posé de problème** —
  ils ne correspondent à aucun `data-automation-id="questionItem"`, donc ils sont déjà
  naturellement ignorés par construction, sans besoin de filtre explicite.

Chaque correctif a été validé par re-test complet (formulaire concerné + un formulaire déjà
fonctionnel, pour vérifier l'absence de régression) et par les scripts `test_extraction_texte.py`
/ `test_extraction_formulaire.py`.

**Nouveau domaine `forms.cloud.microsoft`** (remplacement annoncé de `forms.office.com`) testé
avec succès : le scraper ne dépend d'aucun nom de domaine particulier, seulement de la structure
de la page rendue.


## Nouveau champ `contrainte` : transmettre les règles de validation à l'IA

Constat de Hind, pertinent : détecter une contrainte de validation (voir "contains adi"
ci-dessus) ne sert à rien pour l'IA si elle n'est utilisée qu'en interne pour débloquer la
pagination du scraper. L'IA qui génère une réponse plus tard doit **elle aussi** connaître cette
contrainte, sinon elle peut produire une réponse qui a l'air correcte mais qui ne respecte pas
le format exigé par le formulaire (ex : répondre par du texte à une question qui exige un
nombre).

Trouvaille importante en creusant ce point : Microsoft Forms affiche déjà cette consigne
**directement dans l'attribut `placeholder`** du champ texte (ex :
`placeholder="The value must be a number"`), à la place du texte générique "Enter your answer"
utilisé quand il n'y a aucune contrainte. Cette info est donc présente dès le chargement de la
page, sans avoir besoin de provoquer une erreur de validation pour la lire (contrairement à
l'approche initiale imaginée pour "contains adi").

Ajouts :
- Nouveau champ `contrainte` dans `convertir_question_html` (`microsoft_forms_scraper.py`) :
  lit le `placeholder` du champ texte, `None` si c'est la valeur générique par défaut.
- Propagé jusqu'au JSON standard (`extraction_questions.py`) : nouveau champ `contrainte` au
  niveau de la question, et ajouté à `texte_pour_ia` (ex :
  `"jvb (contrainte : The value must be a number)"`) pour que l'IA le voie directement dans le
  texte qu'elle traite, sans avoir à lire un champ séparé.

Testé avec succès sur un formulaire construit spécifiquement pour couvrir un maximum de règles
possibles (15 questions, 15 contraintes différentes) : nombre (supérieur/inférieur/égal/différent
à une valeur, entre deux valeurs, en dehors de deux valeurs, nombre entier), texte (contient/ne
contient pas un mot, longueur minimale/maximale), e-mail, URL. **Toutes** correctement capturées
sans code spécifique à chaque type de règle — la lecture du `placeholder` fonctionne de façon
générique, quelle que soit la contrainte configurée par le créateur du formulaire.

Limite connue : cette approche ne fonctionne que pour les questions de type texte (le
`placeholder` n'a de sens que là). Les contraintes éventuelles sur d'autres types de questions
(ex : une échelle avec des bornes personnalisées) ne sont pas couvertes, faute d'exemple concret
rencontré pour le moment.

### Même fonctionnalité côté Google Forms ("Validation des réponses")

Google Forms propose l'équivalent pour les questions à réponse courte : nombre (supérieur à,
inférieur à, égal à, entre, nombre entier...), texte (contient, ne contient pas, e-mail valide,
URL valide), longueur (min/max), expression régulière. Question naturelle une fois le champ
`contrainte` ajouté au schéma standard : `google_forms_public.py` le laissait-il vide alors que
l'info existe côté source ? Réponse : oui, corrigé.

Testé sur un formulaire construit spécifiquement pour couvrir ces règles (21 questions). Même
trouvaille que côté Microsoft, en mieux : Google stocke **directement le message d'erreur
affiché à l'utilisateur** (personnalisé par le créateur, ou généré par défaut) dans les données
brutes, à `question_google[4][0][4][0][3]` — le même emplacement que la règle "exactement 1"
trouvée précédemment pour les cases à cocher (`question_google[4][0][4]`), qui contient une
liste `[code_catégorie, code_sous_type, valeurs, message]`. Comme pour Microsoft : pas besoin de
déchiffrer les codes numériques (nombreux et non documentés — repérés en réel : catégorie `1`
pour les règles numériques avec les sous-types 1 à 10, catégorie `2` pour texte, `6` pour
longueur, `4` pour expression régulière, mais non confirmés officiellement), juste lire le
message directement.

Nouvelle fonction `extraire_contrainte_google`, appelée uniquement pour les questions de type
texte (`type_brut == "text"`) dans `convertir_question_google`. Aucun changement nécessaire côté
`extraction_questions.py` : le champ `contrainte` et son intégration dans `texte_pour_ia` étaient
déjà génériques (ajoutés pour Microsoft), donc réutilisables tels quels pour n'importe quelle
source qui fournit cette info.

Effet de bord positif détecté au passage : la fonction `question_checkbox_est_choix_unique`
(règle "exactement 1") faisait un dépaquetage strict à 3 éléments
(`code_type, code_sous_type, valeurs = regle_validation[0]`), qui aurait levé une erreur sur une
question ayant à la fois cette règle ET un message personnalisé (4 éléments au lieu de 3).
Corrigé avec `regle_validation[0][:3]` avant que le cas ne se présente réellement.

**Limite découverte et comblée** : quand le créateur du formulaire ne rédige pas de message
d'erreur personnalisé, Google **n'enregistre aucun message du tout** dans les données brutes
(vérifié : seulement `[catégorie, sous_type, valeurs]`, sans 4e élément) — le message par défaut
qu'un visiteur voit ("Please enter a number greater than 122") est généré par le JavaScript de
Google à l'affichage, jamais stocké côté serveur. Contrairement à Microsoft (`placeholder`
toujours présent, personnalisé ou par défaut), impossible ici de simplement "lire" le message
par défaut.

Remarque de Hind, juste : renvoyer `contrainte: null` dans ce cas prive l'IA d'une information
réelle et disponible (on connaît la règle, juste pas son libellé). Ajout de
`GENERATEURS_CONTRAINTE_GOOGLE` : reconstruit un texte à partir des codes (catégorie, sous-type),
mais **seulement pour les 16 combinaisons concrètement vérifiées** sur le formulaire de test à
20 règles (catégorie `1` = nombre, sous-types 1 à 10 ; catégorie `2` = texte, sous-types 100 à
103 ; catégorie `6` = longueur, sous-types 202-203). Pour toute combinaison non rencontrée
(ex : catégorie `4`, expression régulière, dont la signification précise des 4 sous-types
299-302 reste incertaine), la fonction renvoie délibérément `None` plutôt que de deviner —
mieux vaut aucune contrainte signalée qu'une contrainte inventée et fausse pour l'IA.


## Google Forms : nouveaux bugs trouvés en testant des formulaires externes réels

Après validation du pipeline sur des formulaires construits pour les tests, une série de
formulaires **réels, trouvés sur internet ou partagés par des tiers** (quiz de classe,
recrutement associatif, questionnaire de recherche universitaire...) a permis de découvrir des
cas non couverts par les formulaires de test construits à la main :

- **Titres de section traités comme de fausses questions** : Google Forms permet d'insérer des
  titres de section (avec ou sans image) entre les vraies questions. Deux variantes trouvées :
  - Type Google `11` : titre de section **avec image** (ex : "Week 8 — Due Date...").
  - Type Google `8` : titre de section **sans image** (ex : "Section sans titre",
    "INFORMATIONS GENERALES").

  Les deux ont un type non-`None` à l'index 3 des données brutes, donc passaient le filtre
  `est_une_vraie_question` existant (qui ne vérifiait que "type présent"), et se retrouvaient
  traités comme de vraies questions texte (parfois avec le statut `texte_manquant` à tort,
  parfois carrément acceptées avec le titre de section comme si c'était une vraie réponse).
  Corrigé en excluant explicitement ces deux types (`TYPES_GOOGLE_NON_QUESTIONS = {8, 11}`).
  Sur un questionnaire réel de 54 items, ce correctif a retiré 7 faux positifs (54 → 47 vraies
  questions).
- **Case à cocher fonctionnellement à choix unique** : une question à cases à cocher (type
  Google `4`, normalement `choix_multiple`) peut avoir une règle de validation
  "sélectionner exactement N options". Repéré en réel avec N=1 (ex : question "Filière" avec 8
  cases à cocher, mais contrainte "exactement 1"). Cette règle est encodée dans les données
  brutes sous la forme `[[7, 204, ["1"]]]` (codes internes Google non documentés, mais
  reproductibles). Sans cette information, l'IA pourrait croire qu'elle peut cocher plusieurs
  réponses. Corrigé en reclassant en `choix_unique` uniquement quand cette contrainte précise
  ("exactement 1") est détectée — pas de généralisation à "au moins N"/"au plus N" sans autre
  exemple concret vérifié.
- **Espaces parasites dans le texte des questions** : certains créateurs de formulaire laissent
  des espaces en début/fin de titre par erreur (ex : `"  Sélectionnez le(s) poste(s)...  "`).
  Corrigé avec un simple `.strip()`.
- **Champ `obligatoire` jamais rempli** : contrairement à `google_forms_api.py` (qui lit bien
  `required`), `google_forms_public.py` ne renseignait jamais ce champ — toutes les questions
  ressortaient `"obligatoire": false` par défaut, qu'elles le soient réellement ou non. Le flag
  est en réalité présent dans les données brutes, à l'index 2 de chaque sous-question
  (`question_google[4][0][2] == 1` ; pour une grille, obligatoire si au moins une ligne l'est).
  Corrigé et validé en comparant, formulaire par formulaire, les astérisques rouges réels contre
  le JSON produit (4/5 puis 1/14 champs obligatoires correctement détectés selon les cas).

Formulaires réels utilisés comme cas de test conservés dans `test_documents/` (ex :
`questionnaire_etudiants_ingenieurs.json`, 47 questions, toutes sections/types confondus).


## OCR : amélioration de la lecture de texte tourné + garde-fou contre les blocages

- **Texte tourné (90°/180°/270°) non lu** : sur une image de type "jauge" (cadran avec
  "LOW"/"HIGH" écrits à la verticale sur les côtés, "MEDIUM"/"CORTISOL" à l'horizontale),
  seul le texte horizontal était détecté. EasyOCR ne teste par défaut que l'orientation
  horizontale. Ajout du paramètre `rotation_info=[90, 180, 270]` dans
  `lire_image_avec_easyocr` : coût mesuré modeste (+44 % de temps sur le cas testé), gain réel
  (le texte tourné devient lisible — jusqu'à un score de confiance de 0.90 sur ce cas précis,
  tous les mots captés).
- **Blocage total de l'OCR sur une image pathologique** : une capture d'écran contenant une
  barre d'outils très dense (beaucoup de petites icônes/texte) a fait boucler l'OCR
  indéfiniment — même un `timeout` de 5 minutes appliqué au processus entier n'a pas suffi à
  l'arrêter proprement (a nécessité un arrêt forcé manuel). Ce n'est pas juste "lent" : c'est un
  vrai risque de blocage complet du pipeline sur une seule image malformée, sans limite. Ajouté
  un garde-fou dans `extraction_questions.py` : chaque image est traitée dans son propre thread
  avec un délai maximum (`DELAI_MAX_OCR_SECONDES = 180`) ; au-delà, la question concernée est
  marquée `ocr_echec` (via `concurrent.futures.TimeoutError`) plutôt que de bloquer tout le
  formulaire. Limite connue et acceptée : Python ne permet pas de tuer un thread de force, donc
  le thread bloqué continue en arrière-plan jusqu'à la fin naturelle du script — acceptable ici
  car ce script est un outil en ligne de commande à courte durée de vie, pas un serveur
  persistant.


## Dépôt de fichier : absent sur Microsoft Forms (compte personnel)

Contrairement à Google Forms (où le dépôt de fichier existe pour tout le monde, mais force une
connexion — voir plus haut), le type de question "dépôt de fichier" **n'apparaît pas du tout**
dans l'éditeur Microsoft Forms testé (compte Microsoft personnel) — vérifié : le panneau de
création de question ("Choice", "Text", "Rating", "Date", "Ranking", "Likert", "Net Promoter
Score", "Section") ne le propose pas, et il n'y a pas de menu caché avec plus d'options.

Hypothèse la plus probable (non confirmée officiellement, mais cohérente avec le fonctionnement
connu de Microsoft Forms) : cette fonctionnalité nécessite un compte professionnel/scolaire
(Microsoft 365 Entreprise/Éducation), car les fichiers déposés sont stockés dans le
OneDrive/SharePoint du compte — un compte personnel n'a pas cette infrastructure derrière lui.

Conséquence pratique pour le projet : `microsoft_forms_scraper.py` n'a aucune gestion de ce type
de question (ni dans la table de correspondance des types, ni dans le remplissage factice) —
resté non implémenté faute de pouvoir le tester avec les comptes disponibles. Si un vrai
formulaire d'un partenaire/fournisseur (compte professionnel) en contient un un jour, il faudra
le gérer à ce moment-là, avec un vrai cas concret à observer plutôt qu'en avance sans exemple.


## Ce qu'il reste à faire (mis à jour)

- Tests automatisés (pytest ou assertions) pour figer les cas validés et éviter les régressions
  futures. Reporté après validation du format JSON par l'encadrant.
- Dépôt de fichier sur Microsoft Forms : non géré, faute de pouvoir le tester (voir section
  ci-dessus). À traiter si un vrai formulaire professionnel en contient un.
- Cas de validation de contenu Microsoft Forms non couverts (voir section précédente) : seule la
  règle "le texte doit contenir X" est gérée pour l'instant. D'autres règles possibles (longueur
  minimale/maximale, format e-mail, expression régulière) bloqueraient probablement la
  pagination de la même façon si rencontrées — à corriger au cas par cas si un vrai formulaire
  les utilise, plutôt que d'anticiper sans exemple concret.
- **Avant la livraison finale de la plateforme** : remplacer l'authentification interactive
  actuelle de `google_forms_api.py` (`InstalledAppFlow`, popup navigateur, compte personnel de
  Hind) par une authentification d'entreprise — compte de service avec délégation côté Google
  (Workspace de l'entreprise). Le code d'extraction lui-même ne change pas, seule la façon
  d'obtenir les identifiants change. (`microsoft_forms_api.py` reste dans le dépôt pour
  documenter la piste OAuth/Azure abandonnée, mais n'est plus la voie utilisée.)


## Nettoyage du format JSON après relecture par l'encadrant

L'encadrant a validé le format JSON produit ("c'est bon"), avec une remarque : voir si on peut
l'optimiser. Discussion avec Hind, trois points concrets trouvés :

- **`date_extraction` était codé en dur à `None`**, jamais rempli depuis le début — pas un choix
  volontaire, un oubli. Corrigé : rempli avec l'horodatage réel au moment de l'extraction
  (`datetime.now().isoformat()`). Différent d'un futur horodatage d'insertion en base de
  données : `date_extraction` répond à "à quel moment a-t-on lu le formulaire", utile car le
  formulaire source peut changer après coup (constaté en réel plusieurs fois cette session).
- **Le champ `image` contenait un chemin de fichier absolu** (`/home/bouabidi_hind/...`),
  propre à cette machine de développement précise — inutilisable tel quel une fois le JSON
  consommé ailleurs (autre machine, serveur). Cause : `DOSSIER_IMAGES_TELECHARGEES` utilisait
  `Path(__file__).resolve().parent` dans `google_forms_public.py` et
  `microsoft_forms_scraper.py`, contrairement à `ocr_utils.py` qui utilisait déjà un chemin
  relatif simple pour `image_utilisee` — incohérence entre les modules. Corrigé : les deux
  utilisent maintenant `Path("scripts_extraction/images_formulaires")`, un chemin relatif,
  cohérent avec `ocr_utils.py` (suppose que les scripts sont lancés depuis la racine du projet,
  ce qui a toujours été le cas jusqu'ici).
- **Le champ `ordre`** (sur chaque question et chaque option) : d'abord retiré (redondant avec
  la position dans le tableau JSON), puis **remis** après réflexion avec Hind. Raison concrète :
  ces données finiront dans une base de données relationnelle (voir plan initial du projet,
  table "questions" + table "options"), et une table SQL ne garde aucun ordre par défaut sans
  colonne dédiée — contrairement à un tableau JSON. Sans ce champ explicite, l'écran de la
  personne qui valide les réponses risquerait d'afficher les questions dans le désordre par
  rapport au vrai formulaire, une régression silencieuse difficile à repérer avant qu'un humain
  s'en rende compte en conditions réelles. Gardé dans `formater_options` et
  `extraire_question_textuelle`.

Discussion ouverte, non tranchée (à confirmer avec l'encadrant si besoin) :
- `texte` vs `texte_pour_ia` : parfois identiques (question texte simple), parfois différents
  (`texte_pour_ia` enrichi avec le texte OCR, la reconstruction d'une grille sans titre, ou la
  contrainte de validation). Gardés séparés volontairement : `texte` reste fidèle à ce
  qu'affichait le formulaire (utile pour un affichage humain fidèle lors de la validation),
  `texte_pour_ia` est la version prête à l'emploi pour l'IA. Pas fusionnés pour l'instant.
- `type_reponse_attendu` est entièrement déductible de `type_question` (simple table de
  correspondance dans `determiner_type_reponse`) — champ "de confort" gardé pour éviter de
  dupliquer cette logique côté backend, mais techniquement redondant si le backend est prêt à
  la réimplémenter.
- `modalite` est entièrement déductible de `texte` + `image` (même logique : champ de confort,
  pas une vraie duplication de contenu).
- `statut_extraction` du formulaire (global) est déductible du statut de chaque question
  individuelle (`determiner_statut_formulaire` fait exactement cette agrégation).

### Suite du nettoyage : `options` dupliqué pour les grilles, `ordre` des colonnes

Analyse complète du schéma demandée par Hind (question de son encadrant : "on peut l'optimiser
plus ?"). Deux trouvailles concrètes, au-delà des trois premières :

- **Pour une question grille, le champ `options` contenait exactement le même texte que
  `grille.colonnes`** (vérifié en réel : `"options": ["Eres yeager", "L", "Light", "Conan"]`
  identique à `grille.colonnes`) — un vrai doublon de contenu, pas juste de structure. Vérifié
  dans `determiner_statut_extraction` que `options` n'est jamais utilisé pour valider une grille
  (seul `grille` l'est) : sans risque de le laisser vide. Corrigé dans
  `extraire_question_textuelle` : `options = []` pour `grille_choix_unique`/
  `grille_choix_multiple`, plus d'appel à `formater_options` dans ce cas.
- **`grille.lignes` garde `ordre`, `grille.colonnes` ne l'a plus** : même raisonnement que pour
  `options` sur une question à choix — les lignes d'une grille sont chacune une sous-question à
  part entière (l'ordre compte, comme pour les questions), les colonnes sont l'équivalent des
  options de réponse partagées (l'ordre compte moins). Corrigé dans `extraire_grille_google`
  (`google_forms_public.py`) et `extraire_grille_microsoft` (`microsoft_forms_scraper.py`).

Raisonnement qui a mené à garder `ordre` sur les questions (et sur les lignes de grille) malgré
la demande d'optimisation : un tableau JSON garde son ordre nativement, mais ces données finiront
en base de données relationnelle (table "questions", table "options"), où l'ordre n'est *pas*
garanti sans colonne dédiée — sans ce champ explicite, l'écran de la personne qui valide les
réponses risquerait d'afficher les questions dans le désordre par rapport au vrai formulaire.
Argument nettement moins fort pour les options/colonnes, dont l'ordre n'a généralement aucune
signification propre (juste la liste dans laquelle le créateur du formulaire les a tapées).

### `source.fichier` retiré

Deuxième passe d'analyse demandée par Hind : rien de nouveau trouvé comparable aux redondances
déjà corrigées, à une exception près. `source.fichier` était `null` dans absolument tous les
JSON produits depuis le début du projet — contrairement à `date_extraction` (un oubli), ce champ
n'a jamais eu de code pour le remplir : prévu pour un éventuel chemin d'extraction "depuis un
fichier importé" (Excel, PDF...) plutôt que "depuis un lien", jamais implémenté.

Décision de Hind : la plateforme finale ne recevra que des liens de formulaire (jamais de
fichier importé) — retiré de `source` dans les quatre modules qui le produisaient
(`extraction_questions.py`, `google_forms_public.py`, `microsoft_forms_scraper.py`,
`google_forms_api.py`) et du formulaire simulé de `test_extraction_formulaire.py`. Cohérent avec
le principe : ne pas garder de champ pour un cas d'usage hypothétique — à rajouter le jour où ce
besoin existe vraiment, avec un vrai cas concret pour guider la conception plutôt qu'en avance.

Tests de régression (`test_extraction_texte.py`, `test_extraction_formulaire.py`) repassés après
chaque correctif : aucune casse.

### Tests automatisés (pytest) et bug réel trouvé sur les grilles Google (2026-07-27)

Migration complète des anciens scripts manuels vers pytest : `test_automatise_extraction_texte.py`
et `test_automatise_extraction_formulaire.py` couvrent les 7 cas de
`test_extraction_texte.py`/`test_extraction_formulaire.py` (supprimés après migration),
`test_automatise_ocr.py` couvre `test_ocr.py` (supprimé) — attention, celui-ci appelle vraiment
EasyOCR (~2 min à lui seul, contre 0.03s pour les 8 autres tests).

En testant volontairement le cas jamais couvert (grille à choix unique), un vrai bug a été
trouvé : **le type général Google Forms (`question_google[3]`) vaut 7 pour une grille à choix
unique ET pour une grille à cases à cocher** — les deux ne sont pas distinguables à ce niveau,
contrairement à ce que supposait le commentaire du code ("généralement", jamais vérifié en
réel). Vérifié sur un vrai formulaire de test avec 4 grilles (3 à choix unique, 1 à cases à
cocher, toutes type 7) : le vrai signal est le dernier élément de la première ligne
(`question_google[4][0][-1]`) : `[0]` = choix unique, `[1]` = cases à cocher. Corrigé avec une
nouvelle fonction `grille_est_choix_unique` (même principe que
`question_checkbox_est_choix_unique`, déjà existante pour les questions à cases à cocher
simples), plus 4 tests de régression (`test_automatise_google_forms_grille.py`).
