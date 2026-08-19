// Adresse de notre backend FastAPI.
// Vide (URL relative) : le backend sert maintenant le frontend depuis la même origine (voir
// app.mount("/", StaticFiles(...)) dans main.py), donc plus besoin d'adresse codée en dur —
// ça marche pareil en local (127.0.0.1:8000) et derrière un tunnel ngrok.
const API_URL = "";

// ngrok (gratuit) affiche une page d'avertissement HTML avant CHAQUE requête venant d'un
// navigateur, y compris les appels fetch() — cet en-tête la contourne. Inutile en local
// (127.0.0.1), mais on le laisse toujours présent pour ne pas avoir à y penser si API_URL
// repasse un jour par un tunnel ngrok.
const ENTETES_NGROK = { "ngrok-skip-browser-warning": "true" };

// Récupère la zone où on affiche les messages.
const zoneMessage = document.getElementById("message");

// Récupère la zone où on affichera les réponses.
const listeReponses = document.getElementById("liste-reponses");

// Seul modèle actuellement utilisé côté backend (voir ia_service.py) — plus de menu
// déroulant, le choix multi-modèles n'existe plus depuis la reconnexion backend.
const MODELE_IA = "gemini-3.1-flash-lite";

// Récupère le bouton qui lance le traitement IA.
const boutonTraitement = document.getElementById("bouton-traitement");

// Récupère le champ où l’utilisateur colle une URL de formulaire.
const champFormulaireUrl = document.getElementById("formulaire-url");

// Récupère le bouton qui importe le formulaire depuis une URL.
const boutonImporterUrl = document.getElementById("bouton-importer-url");

// Récupère le bouton flottant "remonter en haut".
const boutonHaut = document.getElementById("bouton-haut");

// Récupère le champ de fichier et le bouton pour ajouter un document à la base RAG.
const champDocumentRag = document.getElementById("document-rag-fichier");
const boutonUploaderDocument = document.getElementById("bouton-uploader-document");

// Garde l’id interne du formulaire importé actuellement.
// Au début, aucun formulaire n’est sélectionné.
let formulaireActuelId = null;

// Zone où sont affichées les cases à cocher "restreindre à ces documents" (voir
// documents_associes en base / retriever.py: retrieve(sources_autorisees=...)).
const listeDocumentsAssocies = document.getElementById("liste-documents-associes");
const champRechercheDocuments = document.getElementById("recherche-documents-associes");

// Liste complète venant du backend (même principe que tousLesFormulaires dans historique.js) —
// la recherche filtre CETTE liste en mémoire, sans redemander au backend à chaque frappe.
let tousLesDocuments = [];

// Sources cochées, conservées à part de l'affichage — sinon, filtrer la liste en tapant dans
// la recherche redessine les cases et perd les coches déjà faites sur des documents qui
// disparaissent temporairement du filtre.
let documentsAssociesCoches = new Set();

// Au-delà de ce nombre, la liste est repliée derrière un lien "... voir tout" — évite qu'elle
// devienne interminable à mesure que des documents s'accumulent (voir chargerListeDocuments()).
const NB_DOCUMENTS_VISIBLES = 4;

// Mémorise si la liste est actuellement dépliée (persiste tant que la page reste ouverte, pour
// ne pas la replier automatiquement après chaque rafraîchissement — voir attendreFinIndexation()).
let listeDocumentsDepliee = false;


// Recharge la liste des documents RAG disponibles depuis le backend — appelée au chargement de
// la page ET après chaque ajout de document, pour que la liste reste à jour sans recharger la
// page. Rien de coché = pas de restriction (comportement par défaut, inchangé).
async function chargerListeDocuments() {
    try {
        const reponseHttp = await fetch(`${API_URL}/documents-rag`, { headers: ENTETES_NGROK });
        const donnees = await reponseHttp.json();
        tousLesDocuments = donnees.documents;
        afficherListeDocuments(tousLesDocuments);
    } catch (erreur) {
        // Silencieux : la liste reste vide, l'import fonctionne quand même sans restriction.
    }
}


// Redessine les cases à cocher à partir d'une liste donnée (complète ou filtrée) — restaure
// l'état coché depuis documentsAssociesCoches, pour ne rien perdre en filtrant. Replie la liste
// au-delà de NB_DOCUMENTS_VISIBLES tant que listeDocumentsDepliee est faux, avec un lien "..."
// pour tout afficher — sans jamais cacher un document déjà coché (sinon on perdrait de vue une
// restriction active sans prévenir l'utilisateur).
function afficherListeDocuments(documents, forcerAffichageComplet = false) {
    listeDocumentsAssocies.innerHTML = "";

    const coches = documents.filter((doc) => documentsAssociesCoches.has(doc.source));
    const nonCoches = documents.filter((doc) => !documentsAssociesCoches.has(doc.source));
    const repliee = !forcerAffichageComplet && !listeDocumentsDepliee && documents.length > NB_DOCUMENTS_VISIBLES;
    const aAfficher = repliee
        ? [...coches, ...nonCoches.slice(0, Math.max(0, NB_DOCUMENTS_VISIBLES - coches.length))]
        : documents;

    aAfficher.forEach((doc) => {
        const label = document.createElement("label");
        label.className = "case-document-associe";
        const coche = documentsAssociesCoches.has(doc.source) ? "checked" : "";
        label.innerHTML = `<input type="checkbox" value="${doc.source}" ${coche}> ${doc.nom_original}`;
        label.querySelector("input").addEventListener("change", (evenement) => {
            if (evenement.target.checked) {
                documentsAssociesCoches.add(doc.source);
            } else {
                documentsAssociesCoches.delete(doc.source);
            }
        });
        listeDocumentsAssocies.appendChild(label);
    });

    const peutReplier = !forcerAffichageComplet && documents.length > NB_DOCUMENTS_VISIBLES;
    if (repliee || (peutReplier && listeDocumentsDepliee)) {
        const lien = document.createElement("button");
        lien.type = "button";
        lien.className = "lien-voir-plus";
        if (repliee) {
            lien.textContent = "Voir plus";
            lien.addEventListener("click", () => {
                listeDocumentsDepliee = true;
                afficherListeDocuments(documents);
            });
        } else {
            lien.textContent = "Voir moins";
            lien.classList.add("deplie");
            lien.addEventListener("click", () => {
                listeDocumentsDepliee = false;
                afficherListeDocuments(documents);
            });
        }
        listeDocumentsAssocies.appendChild(lien);
    }
}


// Filtre tousLesDocuments par nom (insensible à la casse) — appelé à chaque frappe dans le
// champ de recherche, même principe que filtrerFormulaires() dans historique.js.
function filtrerDocuments() {
    const recherche = champRechercheDocuments.value.trim().toLowerCase();
    if (!recherche) {
        afficherListeDocuments(tousLesDocuments);
        return;
    }
    const resultats = tousLesDocuments.filter((doc) =>
        doc.nom_original.toLowerCase().includes(recherche)
    );
    afficherListeDocuments(resultats, true);
}

champRechercheDocuments.addEventListener("input", filtrerDocuments);


// Affiche un message dans zoneMessage — succes=true ajoute le style jaune du thème (.succes,
// voir style.css) plutôt qu'un emoji ✅ à la couleur verte fixe, non personnalisable. Toujours
// retirer la classe d'abord : sans ça, un message de succès resterait stylé même après un
// message d'erreur suivant qui n'a rien à voir.
function afficherMessage(texte, succes = false) {
    zoneMessage.classList.remove("succes");
    if (succes) {
        zoneMessage.classList.add("succes");
    }
    zoneMessage.textContent = texte;
}


// Transforme une date technique en date lisible.
function formaterDate(dateIso) {
    // Si la date n’existe pas, on affiche un texte simple.
    if (!dateIso) {
        return "Not available";
    }

    // Convertit la date ISO en format anglais (jour/mois conservé pour rester lisible
    // sans ambiguïté, contrairement au format mois/jour américain).
    return new Date(dateIso).toLocaleString("en-GB");
}


// Charge les réponses depuis le backend — SEULEMENT celles du formulaire en cours. Tant
// qu'aucun formulaire n'a été importé dans cette session (juste après un rechargement de
// page, par exemple), on n'affiche rien plutôt que la liste globale de tous les formulaires
// mélangés — évite de mélanger les questions de plusieurs formulaires différents à l'écran.
async function chargerReponses() {
    if (formulaireActuelId === null) {
        listeReponses.innerHTML = "";
        afficherMessage("Import a form to see its answers.");
        return;
    }

    // Affiche un message pendant le chargement.
    afficherMessage("Loading answers...");

    // Charge seulement les réponses de CE formulaire précis.
    const urlReponses = `${API_URL}/formulaires/${formulaireActuelId}/reponses`;

    // Appelle le backend pour récupérer les réponses.
    const reponseHttp = await fetch(urlReponses, { headers: ENTETES_NGROK });

    // Transforme la réponse HTTP en objet JavaScript.
    const donnees = await reponseHttp.json();

    // Vide l’ancienne liste avant de réafficher.
    listeReponses.innerHTML = "";

    // Efface le message de chargement pour garder l’interface légère.
    zoneMessage.textContent = "";

    // Crée une carte HTML pour chaque réponse.
    donnees.reponses.forEach((reponse) => {
        afficherReponse(reponse);
    });
}


// Importe un formulaire directement depuis son URL (Google/Microsoft Forms) — le backend
// scrape et enregistre en une seule requête, pas besoin de coller du JSON à la main.
async function importerFormulaireDepuisUrl() {
    const url = champFormulaireUrl.value.trim();

    if (!url) {
        afficherMessage("Paste a form URL first.");
        return;
    }

    boutonImporterUrl.disabled = true;
    boutonImporterUrl.textContent = "Importing...";
    afficherMessage("Extracting and importing the form...");

    // try/catch : si le backend plante (ex. formulaire déjà importé, IntegrityError 500), sa
    // réponse est du texte brut, pas du JSON — reponseHttp.json() lève alors une exception. Sans
    // ce filet, le bouton restait bloqué sur "Import en cours..." pour toujours (le code qui le
    // réactive, plus bas, n'était jamais atteint).
    try {
        // Documents cochés (documentsAssociesCoches, pas les cases visibles à l'écran — un
        // document coché puis masqué par la recherche doit rester pris en compte) : chacun
        // ajouté comme un paramètre "documents_associes" séparé — c'est la syntaxe attendue par
        // FastAPI pour une liste reçue en query params (list[str] = Query(...)), pas une chaîne
        // unique séparée par virgules.
        const parametres = new URLSearchParams({ url });
        documentsAssociesCoches.forEach((source) => {
            parametres.append("documents_associes", source);
        });

        const reponseHttp = await fetch(
            `${API_URL}/formulaires/depuis-url?${parametres.toString()}`,
            { method: "POST", headers: ENTETES_NGROK }
        );

        if (!reponseHttp.ok) {
            afficherMessage("Import rejected: this form may already have been imported, or the URL isn't a valid Google/Microsoft form.");
            return;
        }

        const donnees = await reponseHttp.json();
        formulaireActuelId = donnees.id;

        // Vide la sélection après un import réussi — sinon elle resterait cochée pour le
        // PROCHAIN formulaire importé, qui n'a probablement aucun rapport avec ces documents-ci.
        // Replie aussi la liste, pour repartir sur un affichage compact au prochain import.
        documentsAssociesCoches.clear();
        listeDocumentsDepliee = false;
        afficherListeDocuments(tousLesDocuments);

        // chargerReponses() modifie zoneMessage elle-même ("Chargement...", puis vide) — on
        // affiche donc le message de succès APRÈS, pour qu'il ne soit pas écrasé juste après.
        await chargerReponses();
        afficherMessage(`✓ Form imported successfully: ${donnees.nombre_questions} question(s). You can now start processing.`, true);
    } catch (erreur) {
        afficherMessage("Unexpected error during import — try again in a moment.");
    } finally {
        boutonImporterUrl.disabled = false;
        boutonImporterUrl.textContent = "Import from URL";
    }
}


// Envoie un document (PDF/Word/PowerPoint/Excel/CSV/TXT) au backend pour l'ajouter à la base RAG.
async function uploaderDocumentRag() {
    const fichiers = champDocumentRag.files;

    if (fichiers.length === 0) {
        afficherMessage("Choose one or more files to add first.");
        return;
    }

    boutonUploaderDocument.disabled = true;
    boutonUploaderDocument.textContent = "Adding...";
    afficherMessage(`Uploading and indexing ${fichiers.length} document(s)...`);

    // FormData (pas JSON.stringify) : nécessaire pour envoyer de vrais fichiers binaires. fetch
    // détecte tout seul le bon Content-Type (multipart/form-data) à partir d'un FormData —
    // ne jamais le préciser à la main, ça casserait la frontière ("boundary") entre les champs.
    // Plusieurs append() avec la MÊME clé "fichiers" : c'est ce qui permet au backend de les
    // recevoir tous ensemble comme une liste (list[UploadFile]), pas un seul fichier écrasé.
    const donneesFormulaire = new FormData();
    for (const fichier of fichiers) {
        donneesFormulaire.append("fichiers", fichier);
    }

    // try/catch/finally : même raison que importerFormulaireDepuisUrl() — sans ce filet, une
    // erreur backend laisserait le bouton bloqué sur "Ajout en cours..." pour toujours.
    try {
        let reponseHttp = await fetch(`${API_URL}/documents-rag`, {
            method: "POST",
            headers: ENTETES_NGROK,
            body: donneesFormulaire,
        });

        // 409 = des fichiers de même nom existent déjà (voir le backend). On redemande la
        // permission avant d'écraser quoi que ce soit, plutôt que refuser ou remplacer
        // silencieusement — l'utilisateur décide.
        if (reponseHttp.status === 409) {
            const erreurDonnees = await reponseHttp.json();
            const doublons = erreurDonnees.detail.doublons;
            const veutRemplacer = confirm(
                `These document(s) already exist: ${doublons.join(", ")}. Replace them?`
            );

            if (!veutRemplacer) {
                afficherMessage("Upload cancelled.");
                return;
            }

            // Renvoie exactement la même requête, juste avec remplacer=true en plus.
            reponseHttp = await fetch(`${API_URL}/documents-rag?remplacer=true`, {
                method: "POST",
                headers: ENTETES_NGROK,
                body: donneesFormulaire,
            });
        }

        if (!reponseHttp.ok) {
            afficherMessage("Upload rejected: unsupported file format (PDF, Word, PowerPoint, Excel, CSV, or TXT only) or indexing error.");
            return;
        }

        const donnees = await reponseHttp.json();
        champDocumentRag.value = "";
        afficherMessage(`✓ ${donnees.noms_fichiers.length} document(s) received: ${donnees.noms_fichiers.join(", ")}. Indexing in progress in the background (may take a few minutes).`, true);

        // Vérifie toutes les 3 secondes si l'indexation est terminée, pour remplacer le message
        // ci-dessus par une confirmation claire — sans ça, rien à l'écran ne dit jamais que
        // c'est fini, l'utilisateur doit deviner ou réessayer "Start processing" au hasard.
        attendreFinIndexation(donnees.noms_fichiers);
    } catch (erreur) {
        afficherMessage("Unexpected error while adding documents — try again in a moment.");
    } finally {
        boutonUploaderDocument.disabled = false;
        boutonUploaderDocument.textContent = "Add document";
    }
}


// Interroge GET /documents-rag/statut toutes les 3 secondes jusqu'à ce que l'indexation soit
// terminée, puis affiche une confirmation claire. N'écrase pas un message plus récent affiché
// entre-temps par une autre action (ex. l'utilisateur a lancé un import de formulaire) —
// vérifié via zoneMessage.textContent avant de mettre à jour.
async function attendreFinIndexation(nomsFichiers) {
    const messageAttendu = zoneMessage.textContent;

    const verifier = async () => {
        const reponseHttp = await fetch(`${API_URL}/documents-rag/statut`, { headers: ENTETES_NGROK });
        const statut = await reponseHttp.json();

        if (!statut.indexation_en_cours) {
            if (zoneMessage.textContent === messageAttendu) {
                afficherMessage(`✓ Indexing complete for ${nomsFichiers.join(", ")} — you can now import your form.`, true);
            }
            // Rafraîchit la liste des cases à cocher pour que le(s) nouveau(x) document(s)
            // apparaisse(nt) sans que l'utilisateur ait à recharger la page.
            chargerListeDocuments();
            return;
        }

        setTimeout(verifier, 3000);
    };

    setTimeout(verifier, 3000);
}


// Lance le traitement IA depuis le frontend.
async function lancerTraitementIA() {
    // Sans formulaire importé, formulaire_id (obligatoire côté backend) n'existe pas encore.
    if (formulaireActuelId === null) {
        afficherMessage("Import a form first before starting processing.");
        return;
    }

    // Vérifie qu'aucun document n'est encore en train d'être indexé — sinon le RAG chercherait
    // dans une base pas encore à jour et pourrait manquer une réponse pourtant présente dans un
    // document tout juste ajouté (voir _executer_avec_suivi_indexation côté backend).
    const statutHttp = await fetch(`${API_URL}/documents-rag/statut`, { headers: ENTETES_NGROK });
    const statut = await statutHttp.json();
    if (statut.indexation_en_cours) {
        afficherMessage("A document is still being indexed in the background — please wait a moment and try again.");
        return;
    }

    // Désactive le bouton pendant l’appel backend.
    boutonTraitement.disabled = true;
    boutonTraitement.textContent = "Processing...";
    afficherMessage(`Processing started with ${MODELE_IA}...`);

    // try/catch : même raison que dans importerFormulaireDepuisUrl() — une erreur backend non
    // gérée renvoie du texte brut, pas du JSON, et reponseHttp.json() planterait sans filet.
    try {
        // Appelle la route POST /traitements/questions-textuelles, avec le formulaire_id de
        // l’import en cours (voir formulaireActuelId, rempli par importerFormulaireDepuisUrl).
        const reponseHttp = await fetch(
            `${API_URL}/traitements/questions-textuelles?formulaire_id=${formulaireActuelId}&modele_ia=${MODELE_IA}`,
            {
                method: "POST",
                headers: ENTETES_NGROK,
            }
        );

        if (!reponseHttp.ok) {
            afficherMessage("Processing failed — try again in a moment.");
            return;
        }

        // Transforme la réponse du backend en objet JavaScript.
        const donnees = await reponseHttp.json();

        // Recharge les réponses pour afficher les nouvelles cartes, PUIS affiche le résultat —
        // chargerReponses() modifie zoneMessage elle-même, donc ce message doit venir après,
        // sinon il serait écrasé aussitôt.
        await chargerReponses();
        afficherMessage(`✓ ${donnees.nombre_reponses} new answer(s) generated with ${MODELE_IA}.`, true);
    } catch (erreur) {
        afficherMessage("Unexpected error during processing — try again in a moment.");
    } finally {
        // Réactive le bouton.
        boutonTraitement.disabled = false;
        boutonTraitement.textContent = "Start processing";
    }
}


// Traduit un statut (valeur française, contrainte par chk_reponse_statut en base — voir
// modifierStatut()) en libellé anglais pour l'affichage, sans toucher à la valeur envoyée
// au backend ni aux classes CSS qui, elles, restent indexées sur le mot français.
const LIBELLES_STATUT = {
    "proposée": "Proposed",
    "validée": "Validated",
    "rejetée": "Rejected",
};

function libelleStatut(statut) {
    return LIBELLES_STATUT[statut] || statut;
}


// Affiche une réponse dans la page.
function afficherReponse(reponse) {
    // Crée une nouvelle carte.
    const carte = document.createElement("article");

    // Ajoute la classe CSS pour le design.
    carte.className = "carte-reponse";

    // reponse.valeur est déjà une chaîne simple (voir chk_reponse_format_valeur — l'IA ne
    // renvoie jamais que du texte) — pas besoin de JSON.stringify pour l'afficher/l'éditer,
    // contrairement à avant où ça ajoutait des guillemets superflus autour du texte.
    carte.innerHTML = `
        <div class="contenu-reponse">
            <p class="question">${reponse.question}</p>
            <p class="reponse">Proposed answer: ${reponse.valeur}</p>
            <textarea class="edition-reponse" style="display:none;">${reponse.valeur}</textarea>
            <button class="ajuster">✎ Edit</button>

            <div class="historique">
                <p><span>Generated on</span>${formaterDate(reponse.date_generation)}</p>
                <p><span>Last modified</span>${formaterDate(reponse.date_modification)}</p>
            </div>

            <textarea class="commentaire" placeholder="Add a comment...">${reponse.commentaire_validation || ""}</textarea>

            <span class="statut">Status: ${libelleStatut(reponse.statut)}</span>
        </div>

        <div class="panneau-controle">
            <div class="boutons">
                <button class="valider">✓ Approve</button>
                <button class="rejeter">× Reject</button>
            </div>
        </div>
    `;

    // Récupère les éléments propres à cette carte.
    const texteReponse = carte.querySelector(".reponse");
    const champEdition = carte.querySelector(".edition-reponse");
    const boutonAjuster = carte.querySelector(".ajuster");
    const champCommentaire = carte.querySelector(".commentaire");
    const boutonValider = carte.querySelector(".valider");
    const boutonRejeter = carte.querySelector(".rejeter");

    // Bascule entre le texte affiché et le champ d'édition — le bouton "Ajuster" permet de
    // corriger soi-même la réponse quand la régénération IA n'aiderait pas (ex. mauvaise
    // donnée extraite en amont, pas une mauvaise interprétation de l'IA).
    boutonAjuster.addEventListener("click", () => {
        const enEdition = champEdition.style.display !== "none";
        champEdition.style.display = enEdition ? "none" : "block";
        texteReponse.style.display = enEdition ? "block" : "none";
        boutonAjuster.textContent = enEdition ? "✎ Edit" : "Cancel edit";
    });

    // Quand on clique Valider, on envoie le statut "validée" (avec accent — même valeur que
    // StatutReponseModification/chk_reponse_statut, les 3 doivent rester synchronisés). Si le
    // champ d'édition est visible, sa valeur remplace la réponse générée par l'IA.
    // NOTE : la valeur envoyée au backend ("validée"/"rejetée") reste en français à dessein —
    // c'est une valeur de données contrainte par chk_reponse_statut en base, pas du texte
    // affiché à l'utilisateur ; la traduire casserait la contrainte CHECK côté PostgreSQL.
    boutonValider.addEventListener("click", () => {
        const valeurAjustee = champEdition.style.display !== "none" ? champEdition.value : null;
        modifierStatut(reponse.id, "validée", champCommentaire.value, valeurAjustee);
    });

    // Quand on clique Rejeter, on envoie le statut "rejetée".
    boutonRejeter.addEventListener("click", () => {
        modifierStatut(reponse.id, "rejetée", champCommentaire.value);
    });

    // Ajoute la carte dans la liste affichée.
    listeReponses.appendChild(carte);
}


// Envoie au backend le nouveau statut d’une réponse — valeur est optionnelle (null = pas de
// correction, on garde la valeur générée par l'IA telle quelle, voir schemas/reponse.py).
async function modifierStatut(reponseId, statut, commentaire, valeur = null) {
    // Appelle la route PATCH /reponses/{id}/statut.
    await fetch(`${API_URL}/reponses/${reponseId}/statut`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
            ...ENTETES_NGROK,
        },
        body: JSON.stringify({
            statut: statut,
            commentaire: commentaire,
            valeur: valeur,
        }),
    });

    // Recharge les réponses pour afficher le nouveau statut.
    await chargerReponses();
}


// Quand on clique sur le bouton, on lance le traitement IA.
boutonTraitement.addEventListener("click", lancerTraitementIA);

// Quand on clique sur le bouton, on importe le formulaire depuis une URL.
boutonImporterUrl.addEventListener("click", importerFormulaireDepuisUrl);

// Quand on clique sur le bouton, on envoie le document choisi vers la base RAG.
boutonUploaderDocument.addEventListener("click", uploaderDocumentRag);

// Affiche le bouton "remonter en haut" seulement après avoir un peu scrollé.
window.addEventListener("scroll", () => {
    if (window.scrollY > 300) {
        boutonHaut.classList.add("visible");
    } else {
        boutonHaut.classList.remove("visible");
    }
});

// Remonte en douceur en haut de la page au clic.
boutonHaut.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
});


// Charge les réponses automatiquement au démarrage de la page.
chargerReponses();

// Charge la liste des documents disponibles pour la case "restreindre à ces documents".
chargerListeDocuments();
