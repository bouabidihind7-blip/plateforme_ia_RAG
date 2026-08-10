// Adresse de notre backend FastAPI.
const API_URL = "http://127.0.0.1:8000";

// Récupère la zone où on affiche les messages.
const zoneMessage = document.getElementById("message");

// Récupère la zone où on affichera la liste des formulaires.
const listeFormulaires = document.getElementById("liste-formulaires");

// Les deux vues qu'on bascule l'une contre l'autre (liste ↔ historique d'un formulaire).
const vueListe = document.getElementById("vue-liste");
const vueHistorique = document.getElementById("vue-historique");

// Éléments de la vue historique.
const boutonRetour = document.getElementById("bouton-retour");
const titreHistoriqueFormulaire = document.getElementById("titre-historique-formulaire");
const listeHistorique = document.getElementById("liste-historique");

// Récupère le bouton flottant "remonter en haut".
const boutonHaut = document.getElementById("bouton-haut");

// Récupère le champ de recherche par titre.
const champRecherche = document.getElementById("recherche-formulaire");

// Garde la liste complète venant du backend — la recherche filtre CETTE liste en mémoire,
// sans redemander au backend à chaque frappe (voir filtrerFormulaires()).
let tousLesFormulaires = [];


// Affiche un message dans zoneMessage — même logique que dans script.js (voir ce fichier
// pour le détail : succes=true ajoute le style jaune du thème, .succes dans style.css).
function afficherMessage(texte, succes = false) {
    zoneMessage.classList.remove("succes");
    if (succes) {
        zoneMessage.classList.add("succes");
    }
    zoneMessage.textContent = texte;
}


// Transforme une date technique en date lisible.
function formaterDate(dateIso) {
    if (!dateIso) {
        return "Non disponible";
    }

    return new Date(dateIso).toLocaleString("fr-FR");
}


// Charge la liste des formulaires importés depuis le backend.
async function chargerFormulaires() {
    afficherMessage("Chargement des formulaires...");

    try {
        const reponseHttp = await fetch(`${API_URL}/formulaires`);

        if (!reponseHttp.ok) {
            afficherMessage("Impossible de charger les formulaires — réessaie dans un instant.");
            return;
        }

        const donnees = await reponseHttp.json();

        // Garde la liste complète en mémoire pour la recherche (voir filtrerFormulaires()).
        tousLesFormulaires = donnees.formulaires;

        if (donnees.formulaires.length === 0) {
            afficherMessage("Aucun formulaire importé pour l’instant.");
            return;
        }

        afficherListeFormulaires(tousLesFormulaires);

        afficherMessage(`${donnees.nombre_formulaires} formulaire(s) importé(s).`, true);
    } catch (erreur) {
        afficherMessage("Erreur inattendue pendant le chargement — réessaie dans un instant.");
    }
}


// Vide la liste affichée et réaffiche seulement les formulaires donnés — utilisé au
// chargement initial (liste complète) et à chaque frappe dans la recherche (liste filtrée).
function afficherListeFormulaires(formulaires) {
    listeFormulaires.innerHTML = "";
    formulaires.forEach((formulaire) => {
        afficherFormulaire(formulaire);
    });
}


// Filtre tousLesFormulaires par titre (insensible à la casse) et réaffiche le résultat —
// appelé à chaque frappe dans le champ de recherche.
function filtrerFormulaires() {
    const recherche = champRecherche.value.trim().toLowerCase();

    if (!recherche) {
        afficherListeFormulaires(tousLesFormulaires);
        return;
    }

    const resultats = tousLesFormulaires.filter((formulaire) =>
        (formulaire.titre || "").toLowerCase().includes(recherche)
    );

    afficherListeFormulaires(resultats);
}


// Affiche un formulaire dans la liste — titre en grand, cliquable : le clic charge et
// affiche son historique complet (voir chargerHistorique()).
function afficherFormulaire(formulaire) {
    const carte = document.createElement("article");
    carte.className = `carte-formulaire ${formulaire.fournisseur}`;
    carte.dataset.formulaireId = formulaire.id;

    carte.innerHTML = `
        <h3>${formulaire.titre || "Formulaire sans titre"}</h3>
        <p class="carte-formulaire-meta">
            <span class="badge-fournisseur ${formulaire.fournisseur}">${formulaire.fournisseur.replace("_", " ")}</span>
            Importé le ${formaterDate(formulaire.date_extraction)}
        </p>
    `;

    carte.addEventListener("click", () => {
        chargerHistorique(formulaire.id, formulaire.titre);
    });

    listeFormulaires.appendChild(carte);
}


// Charge l'historique complet d'un formulaire et bascule vers la vue historique.
async function chargerHistorique(formulaireId, titre) {
    afficherMessage("Chargement de l’historique...");

    try {
        const reponseHttp = await fetch(`${API_URL}/formulaires/${formulaireId}/historique`);

        if (!reponseHttp.ok) {
            afficherMessage("Impossible de charger l’historique — réessaie dans un instant.");
            return;
        }

        const donnees = await reponseHttp.json();

        titreHistoriqueFormulaire.textContent = titre || "Formulaire sans titre";
        listeHistorique.innerHTML = "";

        if (donnees.historique.length === 0) {
            listeHistorique.innerHTML = "<p>Aucune réponse générée pour ce formulaire.</p>";
        } else {
            afficherHistoriqueParQuestion(donnees.historique);
        }

        // Bascule d'une vue à l'autre.
        vueListe.hidden = true;
        vueHistorique.hidden = false;

        afficherMessage(`Historique de « ${titre || "ce formulaire"} » chargé.`, true);
    } catch (erreur) {
        afficherMessage("Erreur inattendue pendant le chargement — réessaie dans un instant.");
    }
}


// Regroupe les tentatives par question et les affiche — le backend trie déjà par
// question_ordre puis date_generation DESC (voir lister_historique_formulaire), donc les
// lignes d'une même question arrivent toujours groupées, pas besoin de les retrier ici.
function afficherHistoriqueParQuestion(historique) {
    let questionActuelle = null;
    let carteActuelle = null;

    historique.forEach((tentative) => {
        if (tentative.question_id !== questionActuelle) {
            questionActuelle = tentative.question_id;

            carteActuelle = document.createElement("article");
            carteActuelle.className = "carte-historique-question";
            carteActuelle.innerHTML = `<h3>${tentative.question}</h3>`;

            listeHistorique.appendChild(carteActuelle);
        }

        const blocTentative = document.createElement("div");
        blocTentative.className = "tentative";
        blocTentative.innerHTML = `
            <p class="tentative-valeur">${JSON.stringify(tentative.valeur)}</p>
            <span class="statut-mini ${tentative.statut}">${tentative.statut}</span>
            ${tentative.commentaire_validation ? `<p class="tentative-commentaire">« ${tentative.commentaire_validation} »</p>` : ""}
            <p class="tentative-meta">${tentative.modele_ia} · Généré le ${formaterDate(tentative.date_generation)}</p>
        `;

        carteActuelle.appendChild(blocTentative);
    });
}


// Retour à la liste des formulaires depuis la vue historique.
boutonRetour.addEventListener("click", () => {
    vueHistorique.hidden = true;
    vueListe.hidden = false;
});


// Filtre la liste à chaque frappe dans le champ de recherche.
champRecherche.addEventListener("input", filtrerFormulaires);


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


// Charge les formulaires automatiquement au démarrage de la page.
chargerFormulaires();
