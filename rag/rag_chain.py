"""
Construit la chaîne RAG complète :
  retriever fusionné → prompt → Gemini (gemini-3.1-flash-lite) → texte de la réponse
Même modèle et même clé API que backend/app/services/ia_service.py, pour rester
cohérente avec le reste de la plateforme.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI

from retriever import build_retriever

# Même chemin que ia_service.py/database.py : backend/.env, peu importe le dossier
# courant depuis lequel ce fichier est lancé.
env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
load_dotenv(env_path)

SYSTEM_PROMPT = """Tu es un assistant interne pour les employés et stagiaires de 3D Smart Factory.

Réponds à la question en te basant UNIQUEMENT sur le contexte ci-dessous.
Le contexte vient de plusieurs sources :
- des données structurées de l'entreprise (annuaire, départements, startups incubées)
- des exemples de questions/réponses déjà traitées
- la politique interne de l'entreprise

Si le contexte ne contient pas assez d'information pour répondre avec certitude,
dis-le clairement plutôt que d'inventer une réponse.

Contexte :
{context}
"""


# Colle tous les chunks récupérés en un seul bloc de texte, avec leur source entre
# crochets — même logique que la référence, adaptée à nos métadonnées à nous.
def _format_docs(docs: list[Document]) -> str:
    sections = []
    for doc in docs:
        source = doc.metadata.get("source", "inconnue")
        sections.append(f"[{source}]\n{doc.page_content}")
    return "\n\n---\n\n".join(sections)


def build_chain():
    retriever = build_retriever()

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ])

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0.1,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )

    chain = (
        {"context": retriever | _format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain
