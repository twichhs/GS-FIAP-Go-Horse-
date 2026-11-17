"""Agente generativo do CitizenTech (LangChain + Claude).

Arquitetura agêntica: um LLM (Claude) recebe a pergunta, decide quais
ferramentas chamar (banco compartilhado, RAG, detector de visão, MQTT),
observa os resultados e redige a resposta. O ciclo "pensar -> chamar
ferramenta -> observar" é executado pelo grafo criado por
langchain.agents.create_agent, com memória de conversa por thread_id.

Perfis:
  zeladoria - equipe da prefeitura: ranking, relatório de inspeção, rota, alertas
  cidadao   - linguagem simples; registra reportes; nunca fala em nome da prefeitura
  geral     - os dois públicos

Uso rápido:
    from agente import criar_agente, perguntar
    ag = criar_agente("zeladoria")
    resposta, passos = perguntar(ag, "Quais trechos precisam de vistoria esta semana?")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
try:  # .env na raiz do repositório (ANTHROPIC_API_KEY, CITIZENTECH_LLM, ...)
    from dotenv import load_dotenv
    load_dotenv(AQUI.parent.parent / ".env")
except ImportError:
    pass
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))

from langchain.agents import create_agent  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

import ferramentas  # noqa: E402

# Modelo padrão: Claude Opus 5.5. Troque pela variável de ambiente CITIZENTECH_LLM,
# ex.: "anthropic:claude-sonnet-5-5", "openai:gpt-5", "google_genai:gemini-2.5-pro",
# "ollama:llama3.1" (exige o pacote langchain-<provedor> correspondente instalado).
MODELO_PADRAO = "anthropic:claude-opus-5-5"

PROMPT_BASE = """Você é o assistente do CitizenTech · Monitor de Pavimento, um protótipo acadêmico (FIAP,
Global Solution 2026.2) que detecta e prioriza buracos em vias urbanas a partir de três fontes:
sensores IoT em veículos (ESP32: profundidade, umidade, botão de reporte), visão computacional
(detector YOLO em fotos e vídeos) e reportes de cidadãos. Tudo é gravado em um banco compartilhado e
resumido na view de prioridade por trecho. Responda sempre em português do Brasil.

REGRAS DE DADOS
- Nunca invente trechos, pontuações, contagens, datas ou estatísticas. Todo dado sobre trechos,
  eventos, detecções ou dispositivos deve vir de uma ferramenta de consulta chamada nesta conversa.
- Se uma ferramenta devolver erro ou lista vazia, diga isso claramente em vez de supor valores.
- Ao citar números, diga de onde vieram (ex.: "segundo o ranking do banco, ...").

REGRAS DE CONHECIMENTO (RAG)
- Para perguntas sobre procedimentos, direitos do cidadão, fórmula de prioridade, limitações,
  funcionamento dos módulos ou ODS, chame buscar_base_conhecimento antes de responder e cite a
  fonte (nome do documento) ao final da resposta.
- Se a base não cobrir a pergunta, diga que a informação não está na base do projeto e, se for o
  caso, indique um canal oficial (SP156) ou um profissional (advogado, Defensoria Pública).

RESPONSABILIDADE
- A pontuação é uma triagem. Nenhuma detecção automática confirma a gravidade de um buraco: a
  vistoria técnica presencial continua obrigatória. Deixe isso explícito quando recomendar ações.
- O CitizenTech não é a Prefeitura e não abre protocolos oficiais. Não dê parecer jurídico para um
  caso concreto; ofereça orientações gerais e indique onde buscar ajuda.
- Ações com efeito (registrar reporte, gravar detecções, enviar alerta ao ESP32) só depois de o
  usuário confirmar o trecho e a intenção. Informe o resultado da ação.
- Não peça nem registre dados pessoais (nome, CPF, telefone, endereço residencial).

ESTILO
- Seja direto e organizado. Use listas curtas e tabelas simples quando ajudarem.
- Quando pedirem um relatório de inspeção, use as seções: Resumo, Ranking de prioridade (com as
  evidências de cada trecho), Rota sugerida (agrupada por bairro, alta antes de média), Alertas e
  condições (umidade, reportes recentes), Limitações e validação humana necessária.
"""

PROMPT_PERFIL = {
    "zeladoria": "\nPÚBLICO: equipe de zeladoria/subprefeitura. Foque em priorização, evidências, rota de inspeção e "
                 "ações operacionais (sinalização provisória, vistoria). Pode enviar alerta ao ESP32 quando solicitado.\n",
    "cidadao": "\nPÚBLICO: cidadão. Use linguagem simples e acolhedora. Explique como reportar pelo SP156, como se "
               "proteger e quais são seus direitos em termos gerais. Pode registrar um reporte no CitizenTech "
               "depois que o cidadão confirmar o trecho (use listar_trechos para mostrar as opções) e a descrição. "
               "Nunca envie alertas ao ESP32 nem prometa reparo.\n",
    "geral": "\nPÚBLICO: equipe de zeladoria e cidadãos. Adapte o tom a quem está falando.\n",
}

PROMPT_RELATORIO = (
    "Gere o relatório de inspeção de pavimento de hoje para a equipe de zeladoria. Consulte o ranking "
    "de prioridade, detalhe cada trecho com registro (eventos IoT e detecções de visão) e monte a rota "
    "sugerida. Siga as seções padrão do relatório."
)


def criar_modelo(nome: str | None = None):
    """Instancia o LLM. Anthropic usa ChatAnthropic; outros provedores passam por init_chat_model."""
    nome = nome or os.getenv("CITIZENTECH_LLM", MODELO_PADRAO)
    provedor, _, modelo = nome.partition(":")
    if provedor == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # Opus 5.5: thinking adaptativo sempre ligado; sem temperature (o modelo rejeita amostragem manual)
        return ChatAnthropic(model=modelo, max_tokens=4096)
    from langchain.chat_models import init_chat_model
    return init_chat_model(modelo, model_provider=provedor)


def ferramentas_do_perfil(perfil: str) -> list:
    if perfil == "cidadao":
        return ferramentas.FERRAMENTAS_CONSULTA + [ferramentas.registrar_reporte_cidadao, ferramentas.analisar_foto_buracos]
    return ferramentas.TODAS


def criar_agente(perfil: str = "geral", modelo=None, tools: list | None = None):
    """Cria o grafo do agente (modelo + ferramentas + prompt do perfil + memória por thread)."""
    if perfil not in PROMPT_PERFIL:
        raise ValueError(f"perfil inválido: {perfil} (use {list(PROMPT_PERFIL)})")
    llm = modelo if modelo is not None else criar_modelo()
    return create_agent(
        model=llm,
        tools=tools if tools is not None else ferramentas_do_perfil(perfil),
        system_prompt=PROMPT_BASE + PROMPT_PERFIL[perfil],
        checkpointer=InMemorySaver(),
        name=f"citizentech-{perfil}",
    )


def texto_da_mensagem(msg) -> str:
    """Conteúdo textual de uma mensagem (Claude devolve blocos; outros provedores devolvem string)."""
    c = msg.content
    if isinstance(c, str):
        return c
    partes = []
    for b in c:
        if isinstance(b, dict) and b.get("type") == "text":
            partes.append(b.get("text", ""))
        elif isinstance(b, str):
            partes.append(b)
    return "".join(partes)


def perguntar(agente, texto: str, thread_id: str = "demo", recursion_limit: int = 40):
    """Envia uma pergunta e devolve (resposta, passos), onde passos lista as ferramentas chamadas."""
    estado = agente.invoke(
        {"messages": [HumanMessage(content=texto)]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit},
    )
    msgs = estado["messages"]
    # mensagens geradas nesta rodada: tudo depois da última HumanMessage
    idx = max(i for i, m in enumerate(msgs) if isinstance(m, HumanMessage))
    novas = msgs[idx + 1:]
    passos = []
    for m in novas:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                passos.append({"ferramenta": tc["name"], "argumentos": tc["args"]})
        elif isinstance(m, ToolMessage):
            conteudo = m.content if isinstance(m.content, str) else str(m.content)
            passos.append({"resultado_de": m.name, "resumo": conteudo[:400]})
    resposta = next((texto_da_mensagem(m) for m in reversed(novas) if isinstance(m, AIMessage) and texto_da_mensagem(m)), "")
    return resposta, passos


def imprimir_passos(passos: list) -> None:
    for p in passos:
        if "ferramenta" in p:
            print(f"  -> {p['ferramenta']}({p['argumentos']})")
        else:
            print(f"  <- {p['resultado_de']}: {p['resumo'][:160].replace(chr(10), ' ')}...")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Conversa com o agente CitizenTech no terminal")
    ap.add_argument("--perfil", default="geral", choices=list(PROMPT_PERFIL))
    ap.add_argument("--pergunta", default=None, help="uma única pergunta (senão, modo interativo)")
    a = ap.parse_args()
    ag = criar_agente(a.perfil)
    if a.pergunta:
        r, p = perguntar(ag, a.pergunta)
        imprimir_passos(p)
        print("\n" + r)
    else:
        print("Agente CitizenTech (Ctrl+C para sair)")
        while True:
            try:
                q = input("\nvocê> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q:
                continue
            r, p = perguntar(ag, q)
            imprimir_passos(p)
            print("\nagente> " + r)
