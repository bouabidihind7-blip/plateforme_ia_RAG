# 3D Smart Factory — Plateforme IA de traitement de formulaires

Plateforme développée dans le cadre d'un stage chez **3D Smart Factory**, qui automatise le
traitement des formulaires en ligne (Google Forms et Microsoft Forms) : extraction automatique
des questions, génération de propositions de réponses par IA en s'appuyant sur la documentation
interne de l'entreprise, puis validation humaine avant toute publication.

## Fonctionnement

1. **Extraction** — récupère automatiquement la structure d'un formulaire (questions, types,
   options, grilles...) directement depuis son URL (Google Forms ou Microsoft Forms).
2. **Génération IA** — un agent basé sur le modèle Gemini propose une réponse à chaque question,
   en s'appuyant sur un système de recherche documentaire (RAG) interrogeant la documentation de
   l'entreprise (politiques internes, données tabulaires...).
3. **Validation humaine** — chaque réponse proposée est relue, validée, corrigée ou rejetée via
   une interface web, avec un historique complet et traçable.

## Architecture

- `backend/` — API REST FastAPI, base de données PostgreSQL (SQLAlchemy)
- `rag/` — système de recherche documentaire (ingestion, recherche hybride embedding + BM25,
  reclassement par cross-encoder)
- `rag_documents/` — documents internes indexés par le RAG
- `scripts_extraction/` — extraction des formulaires Google/Microsoft Forms (scraping + OCR)
- `frontend/` — interface web (import, traitement, validation des réponses)
- `database_scripts/` — schéma SQL de la base de données
- `rapport/` — rapport de stage complet (LaTeX)
- `test_documents/` — exemples de formulaires extraits, utilisés pour les tests

## Stack technique

FastAPI · PostgreSQL · LangChain · Google Gemini · ChromaDB · Docling · sentence-transformers ·
BM25 · Playwright

## Lancer le projet

```bash
./demarrer.sh   # démarre le backend (sert aussi le frontend)
./arreter.sh    # arrête le backend
```

L'application est ensuite accessible sur `http://127.0.0.1:8000`.

## Rapport de stage

Le rapport complet décrivant la conception, les choix techniques et les résultats du projet se
trouve dans [`rapport/rapport_stage.tex`](rapport/rapport_stage.tex).
