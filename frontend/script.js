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

// Récupère la zone où l’utilisateur colle le formulaire JSON.
const champFormulaireJson = document.getElementById("formulaire-json");

// Récupère le bouton qui importe le formulaire.
const boutonImporter = document.getElementById("bouton-importer");

// Garde l’id interne du formulaire importé actuellement.
// Au début, aucun formulaire n’est sélectionné.
let formulaireActuelId = null;


// Transforme une date technique en date lisible.
function formaterDate(dateIso) {
    // Si la date n’existe pas, on affiche un texte simple.
    if (!dateIso) {
        return "Non disponible";
    }

    // Convertit la date ISO en format français.
    return new Date(dateIso).toLocaleString("fr-FR");
}


// Charge les réponses depuis le backend.
async function chargerReponses() {
    // Affiche un message pendant le chargement.
    zoneMessage.textContent = "Chargement des réponses...";

    // Prépare l’URL utilisée pour charger les réponses.
    let urlReponses = `${API_URL}/reponses`;

    // Si un formulaire vient d’être importé, on charge seulement ses réponses.
    if (formulaireActuelId !== null) {
        urlReponses = `${API_URL}/formulaires/${formulaireActuelId}/reponses`;
    }

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


// Importe un formulaire JSON vers le backend.
async function importerFormulaire() {
    // Récupère le texte écrit par l’utilisateur.
    const texteJson = champFormulaireJson.value.trim();

    // Vérifie que le champ n’est pas vide.
    if (!texteJson) {
        zoneMessage.textContent = "Colle d’abord un formulaire JSON.";
        return;
    }

    let formulaire;

    // Transforme le texte JSON en objet JavaScript.
    try {
        formulaire = JSON.parse(texteJson);
    } catch (erreur) {
        zoneMessage.textContent = "JSON invalide : vérifie les accolades, virgules et guillemets.";
        return;
    }

    // Désactive le bouton pendant l’envoi.
    boutonImporter.disabled = true;
    boutonImporter.textContent = "Import en cours...";
    zoneMessage.textContent = "Import du formulaire...";

    // Envoie le formulaire au backend.
    const reponseHttp = await fetch(`${API_URL}/formulaires`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(formulaire),
    });

    // Lit la réponse du backend.
    const donnees = await reponseHttp.json();

    // Si le backend refuse le formulaire, on affiche une erreur simple.
    if (!reponseHttp.ok) {
        zoneMessage.textContent = "Import refusé : vérifie la structure du formulaire.";
        boutonImporter.disabled = false;
        boutonImporter.textContent = "Importer le formulaire";
        return;
    }

    // Affiche un message de succès.
    zoneMessage.textContent = `Formulaire importé : ${donnees.nombre_questions} question(s).`;

    // Garde l’id interne PostgreSQL du formulaire importé.
    formulaireActuelId = donnees.id;

    // Vide le champ après succès.
    champFormulaireJson.value = "";

    // Recharge les réponses existantes.
    await chargerReponses();

    // Réactive le bouton.
    boutonImporter.disabled = false;
    boutonImporter.textContent = "Importer le formulaire";
}


// Lance le traitement IA depuis le frontend.
async function lancerTraitementIA() {
    // Récupère le modèle choisi par l’utilisateur.
    const modele = choixModele.value;

    // Désactive le bouton pendant l’appel backend.
    boutonTraitement.disabled = true;
    boutonTraitement.textContent = "Traitement en cours...";
    zoneMessage.textContent = `Traitement lancé avec ${modele}...`;

    // Appelle la route POST /traitements/questions-textuelles.
    const reponseHttp = await fetch(
        `${API_URL}/traitements/questions-textuelles?modele_ia=${modele}`,
        {
            method: "POST",
        }
    );

    // Transforme la réponse du backend en objet JavaScript.
    const donnees = await reponseHttp.json();

    // Affiche le résultat du traitement.
    zoneMessage.textContent = `${donnees.nombre_reponses} nouvelle(s) réponse(s) générée(s) avec ${modele}.`;

    // Recharge les réponses pour afficher les nouvelles cartes.
    await chargerReponses();

    // Réactive le bouton.
    boutonTraitement.disabled = false;
    boutonTraitement.textContent = "Lancer le traitement";
}


// Affiche une réponse dans la page.
function afficherReponse(reponse) {
    // Crée une nouvelle carte.
    const carte = document.createElement("article");

    // Ajoute la classe CSS pour le design.
    carte.className = "carte-reponse";

    // Remplit la carte avec les informations de la réponse.
    carte.innerHTML = `
        <div class="contenu-reponse">
            <p class="question">${reponse.question}</p>
            <p class="reponse">Réponse proposée : ${JSON.stringify(reponse.valeur)}</p>

            <div class="historique">
                <p><span>Modèle</span>${reponse.modele_ia}</p>
                <p><span>Générée le</span>${formaterDate(reponse.date_generation)}</p>
                <p><span>Dernière modification</span>${formaterDate(reponse.date_modification)}</p>
            </div>

            <textarea placeholder="Ajouter un commentaire...">${reponse.commentaire_validation || ""}</textarea>

            <span class="statut">Statut : ${reponse.statut}</span>
        </div>

        <div class="panneau-controle">
            <div class="boutons">
                <button class="valider">✓ Valider</button>
                <button class="rejeter">× Rejeter</button>
            </div>
        </div>
    `;

    // Récupère le champ commentaire dans cette carte.
    const champCommentaire = carte.querySelector("textarea");

    // Récupère le bouton Valider dans cette carte.
    const boutonValider = carte.querySelector(".valider");

    // Récupère le bouton Rejeter dans cette carte.
    const boutonRejeter = carte.querySelector(".rejeter");

    // Quand on clique Valider, on envoie le statut "validee".
    boutonValider.addEventListener("click", () => {
        modifierStatut(reponse.id, "validee", champCommentaire.value);
    });

    // Quand on clique Rejeter, on envoie le statut "rejetee".
    boutonRejeter.addEventListener("click", () => {
        modifierStatut(reponse.id, "rejetee", champCommentaire.value);
    });

    // Ajoute la carte dans la liste affichée.
    listeReponses.appendChild(carte);
}


// Envoie au backend le nouveau statut d’une réponse.
async function modifierStatut(reponseId, statut, commentaire) {
    // Appelle la route PATCH /reponses/{id}/statut.
    await fetch(`${API_URL}/reponses/${reponseId}/statut`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({
            statut: statut,
            commentaire: commentaire,
        }),
    });

    // Recharge les réponses pour afficher le nouveau statut.
    await chargerReponses();
}


// Quand on clique sur le bouton, on lance le traitement IA.
boutonTraitement.addEventListener("click", lancerTraitementIA);

// Quand on clique sur le bouton, on importe le formulaire.
boutonImporter.addEventListener("click", importerFormulaire);


// Charge les réponses automatiquement au démarrage de la page.
chargerReponses();
