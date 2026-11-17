"""RAG (Retrieval-Augmented Generation) do CitizenTech.

Indexa a base de conhecimento do projeto (documentos Markdown em
base_conhecimento/ e o relatório PDF do módulo IoT) em um índice vetorial
FAISS com embeddings multilíngues locais. O agente consulta esse índice pela
ferramenta buscar_base_conhecimento() e responde citando a fonte.

Pipeline: documentos -> divisão em trechos (chunks) -> embeddings -> FAISS
          pergunta -> embedding -> k trechos mais próximos -> contexto para o LLM
"""
from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_PROJETO = AQUI.parent.parent
sys.path.insert(0, str(AQUI.parent))

PASTA_DOCS = AQUI / "base_conhecimento"
PASTA_INDICE = AQUI / "indice_faiss"
PDF_IOT = RAIZ_PROJETO / "CitizenTech_Modulo_IoT.pdf"
MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHUNK = 700
SOBREPOSICAO = 120

_embeddings = None
_indice = None


def embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(model_name=MODELO_EMBEDDINGS)
    return _embeddings


def carregar_documentos() -> list:
    """Um Document por arquivo .md (com título) e um por página do PDF do módulo IoT."""
    from langchain_core.documents import Document

    docs = []
    for md in sorted(PASTA_DOCS.glob("*.md")):
        texto = md.read_text(encoding="utf-8")
        titulo = next((l.lstrip("# ").strip() for l in texto.splitlines() if l.startswith("# ")), md.stem)
        docs.append(Document(page_content=texto, metadata={"fonte": md.name, "titulo": titulo, "tipo": "md"}))
    if PDF_IOT.exists():
        from pypdf import PdfReader
        for i, pagina in enumerate(PdfReader(str(PDF_IOT)).pages, start=1):
            t = (pagina.extract_text() or "").strip()
            if len(t) > 80 and i <= 9:      # ignora o apêndice com o código-fonte
                docs.append(Document(page_content=t, metadata={"fonte": PDF_IOT.name, "titulo": f"Relatório IoT, página {i}",
                                                               "pagina": i, "tipo": "pdf"}))
    return docs


def dividir(docs: list) -> list:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK, chunk_overlap=SOBREPOSICAO,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " "],
    )
    pedacos = splitter.split_documents(docs)
    for i, p in enumerate(pedacos):
        p.metadata["chunk"] = i
    return pedacos


def construir_indice(forcar: bool = False):
    """Carrega o índice salvo ou (re)constrói a partir dos documentos."""
    global _indice
    from langchain_community.vectorstores import FAISS

    if _indice is not None and not forcar:
        return _indice
    if PASTA_INDICE.exists() and not forcar:
        _indice = FAISS.load_local(str(PASTA_INDICE), embeddings(), allow_dangerous_deserialization=True)
        return _indice
    pedacos = dividir(carregar_documentos())
    _indice = FAISS.from_documents(pedacos, embeddings())
    _indice.save_local(str(PASTA_INDICE))
    print(f"Índice FAISS criado com {len(pedacos)} trechos em {PASTA_INDICE}")
    return _indice


def buscar(pergunta: str, k: int = 4) -> list[tuple]:
    """Retorna [(Document, distância)] — distância menor = mais parecido (L2 no FAISS)."""
    return construir_indice().similarity_search_with_score(pergunta, k=k)


def formatar_contexto(resultados: list[tuple]) -> str:
    blocos = []
    for i, (doc, dist) in enumerate(resultados, start=1):
        blocos.append(f"[{i}] Fonte: {doc.metadata.get('fonte')} — {doc.metadata.get('titulo')} "
                      f"(distância {dist:.2f})\n{doc.page_content.strip()}")
    return "\n\n".join(blocos) if blocos else "Nenhum trecho relevante encontrado na base de conhecimento."


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--reconstruir", action="store_true")
    p.add_argument("--pergunta", default="Como o cidadão reporta um buraco em São Paulo?")
    a = p.parse_args()
    construir_indice(forcar=a.reconstruir)
    print(formatar_contexto(buscar(a.pergunta)))
