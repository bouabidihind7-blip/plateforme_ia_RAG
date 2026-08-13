// Adresse de notre backend FastAPI.
const API_URL = "http://127.0.0.1:8000";

// Récupère la zone où on affiche les messages.
const zoneMessage = document.getElementById("message");

// Récupère la zone où on affichera les réponses.
const listeReponses = document.getElementById("liste-reponses");

// Récupère la liste de choix du modèle IA.
const choixModele = document.getElementById("modele-ia");

// Récupère le bouton qui lance le traitement IA.
const boutonTraitement = document.getElementById("bouton-traitement");

// Récupère le champ où l’utilisateur colle une URL de formulaire.
const champFormulaireUrl = document.getElementById("formulaire-url");

// Récupère le bouton qui importe le formulaire depuis une URL.
const boutonImporterUrl = document.getElementById("bouton-importer-url");

// Récupère le bouton flottant "remonter en haut".
const boutonHaut = document.getElementById("bouton-haut");

// Garde l’id interne du formulaire importé actuellement.
// Au début, aucun formulaire n’est sélectionné.
let formulaireActuelId = null;


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
        return "Non disponible";
    }

    // Convertit la date ISO en format français.
    return new Date(dateIso).toLocaleString("fr-FR");
}


// Charge les réponses depuis le backend — SEULEMENT celles du formulaire en cours. Tant
// qu'aucun formulaire n'a été importé dans cette session (juste après un rechargement de
// page, par exemple), on n'affiche rien plutôt que la liste globale de tous les formulaires
// mélangés — évite de mélanger les questions de plusieurs formulaires différents à l'écran.
async function chargerReponses() {
    if (formulaireActuelId === null) {
        listeReponses.innerHTML = "";
        afficherMessage("Importe un formulaire pour voir ses réponses.");
        return;
    }

    // Affiche un message pendant le chargement.
    afficherMessage("Chargement des réponses...");

    // Charge seulement les réponses de CE formulaire précis.
    const urlReponses = `${API_URL}/formulaires/${formulaireActuelId}/reponses`;

    // Appelle le backend pour récupérer les réponses.
    const reponseHttp = await fetch(urlReponses);

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
        afficherMessage("Colle d’abord une URL de formulaire.");
        return;
    }

    boutonImporterUrl.disabled = true;
    boutonImporterUrl.textContent = "Import en cours...";
    afficherMessage("Extraction et import du formulaire...");

    // try/catch : si le backend plante (ex. formulaire déjà importé, IntegrityError 500), sa
    // réponse est du texte brut, pas du JSON — reponseHttp.json() lève alors une exception. Sans
    // ce filet, le bouton restait bloqué sur "Import en cours..." pour toujours (le code qui le
    // réactive, plus bas, n'était jamais atteint).
    try {
        // url est un query param côté backend (def recevoir_formulaire_depuis_url(url: str)),
        // pas un Body — on la met donc directement dans l’URL de la requête, pas en JSON.
        const reponseHttp = await fetch(
            `${API_URL}/formulaires/depuis-url?url=${encodeURIComponent(url)}`,
            { method: "POST" }
        );

        if (!reponseHttp.ok) {
            afficherMessage("Import refusé : ce formulaire a peut-être déjà été importé, ou l’URL n’est pas un formulaire Google/Microsoft valide.");
            return;
        }

        const donnees = await reponseHttp.json();
        formulaireActuelId = donnees.id;

        // chargerReponses() modifie zoneMessage elle-même ("Chargement...", puis vide) — on
        // affiche donc le message de succès APRÈS, pour qu'il ne soit pas écrasé juste après.
        await chargerReponses();
        afficherMessage(`✓ Formulaire importé avec succès : ${donnees.nombre_questions} question(s). Tu peux maintenant lancer le traitement.`, true);
    } catch (erreur) {
        afficherMessage("Erreur inattendue pendant l’import — réessaie dans un instant.");
    } finally {
        boutonImporterUrl.disabled = false;
        boutonImporterUrl.textContent = "Importer depuis une URL";
    }
}


// Lance le traitement IA depuis le frontend.
async function lancerTraitementIA() {
    // Sans formulaire importé, formulaire_id (obligatoire côté backend) n'existe pas encore.
    if (formulaireActuelId === null) {
        afficherMessage("Importe d’abord un formulaire avant de lancer le traitement.");
        return;
    }

    // Récupère le modèle choisi par l’utilisateur.
    const modele = choixModele.value;

    // Désactive le bouton pendant l’appel backend.
    boutonTraitement.disabled = true;
    boutonTraitement.textContent = "Traitement en cours...";
    afficherMessage(`Traitement lancé avec ${modele}...`);

    // try/catch : même raison que dans importerFormulaireDepuisUrl() — une erreur backend non
    // gérée renvoie du texte brut, pas du JSON, et reponseHttp.json() planterait sans filet.
    try {
        // Appelle la route POST /traitements/questions-textuelles, avec le formulaire_id de
        // l’import en cours (voir formulaireActuelId, rempli par importerFormulaireDepuisUrl).
        const reponseHttp = await fetch(
            `${API_URL}/traitements/questions-textuelles?formulaire_id=${formulaireActuelId}&modele_ia=${modele}`,
            {
                method: "POST",
            }
        );

        if (!reponseHttp.ok) {
            afficherMessage("Échec du traitement — réessaie dans un instant.");
            return;
        }

        // Transforme la réponse du backend en objet JavaScript.
        const donnees = await reponseHttp.json();

        // Recharge les réponses pour afficher les nouvelles cartes, PUIS affiche le résultat —
        // chargerReponses() modifie zoneMessage elle-même, donc ce message doit venir après,
        // sinon il serait écrasé aussitôt.
        await chargerReponses();
        afficherMessage(`✓ ${donnees.nombre_reponses} nouvelle(s) réponse(s) générée(s) avec ${modele}.`, true);
    } catch (erreur) {
        afficherMessage("Erreur inattendue pendant le traitement — réessaie dans un instant.");
    } finally {
        // Réactive le bouton.
        boutonTraitement.disabled = false;
        boutonTraitement.textContent = "Lancer le traitement";
    }
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
            <p class="reponse">Réponse proposée : ${reponse.valeur}</p>
            <textarea class="edition-reponse" style="display:none;">${reponse.valeur}</textarea>
            <button class="ajuster">✎ Ajuster</button>

            <div class="historique">
                <p><span>Générée le</span>${formaterDate(reponse.date_generation)}</p>
                <p><span>Dernière modification</span>${formaterDate(reponse.date_modification)}</p>
            </div>

            <textarea class="commentaire" placeholder="Ajouter un commentaire...">${reponse.commentaire_validation || ""}</textarea>

            <span class="statut">Statut : ${reponse.statut}</span>
        </div>

        <div class="panneau-controle">
            <div class="boutons">
                <button class="valider">✓ Valider</button>
                <button class="rejeter">× Rejeter</button>
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
        boutonAjuster.textContent = enEdition ? "✎ Ajuster" : "Annuler l’ajustement";
    });

    // Quand on clique Valider, on envoie le statut "validée" (avec accent — même valeur que
    // StatutReponseModification/chk_reponse_statut, les 3 doivent rester synchronisés). Si le
    // champ d'édition est visible, sa valeur remplace la réponse générée par l'IA.
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
