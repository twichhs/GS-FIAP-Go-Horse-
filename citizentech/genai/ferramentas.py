"""Ferramentas (tools) do agente CitizenTech.

Cada função abaixo é exposta ao LLM como uma ferramenta LangChain. O modelo
decide QUANDO chamar cada uma; o código decide O QUE ela faz. Todas devolvem
texto (JSON legível) para o modelo interpretar. Nenhum número sobre trechos
vem da "memória" do modelo: tudo passa por consulta ao banco compartilhado.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from langchain_core.tools import tool

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parent / "visao"))

import banco  # noqa: E402
import config  # noqa: E402

_conn = None


def conexao():
    global _conn
    if _conn is None:
        _conn = banco.conectar()
        banco.inicializar(_conn)
    return _conn


def _js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)


# ----------------------------------------------------------------- consulta
@tool
def listar_trechos() -> str:
    """Lista os trechos de via cadastrados no CitizenTech (código, nome da via, bairro, coordenadas).
    Use para descobrir códigos válidos antes de detalhar ou registrar algo em um trecho."""
    return _js(banco.listar_trechos(conexao()))


@tool
def consultar_ranking_prioridade(apenas_com_registro: bool = True) -> str:
    """Ranking de prioridade de inspeção por trecho (view vw_prioridade_trechos), do mais crítico ao menos.
    Traz pontuação, nível (alta/média/baixa/sem_registro), buracos graves e leves medidos pelo IoT,
    reportes manuais, detecções de visão computacional, profundidade máxima e umidade média.
    apenas_com_registro=False inclui trechos sem nenhuma ocorrência."""
    linhas = banco.prioridades(conexao(), apenas_com_registro=apenas_com_registro)
    campos = ["uid", "nome", "bairro", "pontuacao", "nivel", "graves", "leves", "reportes", "deteccoes_visao",
              "conf_media_visao", "prof_max_mm", "umidade_media", "ultimo_evento", "ultima_deteccao"]
    return _js([{c: l.get(c) for c in campos} for l in linhas]) if linhas else "Nenhum trecho com registro até agora."


@tool
def detalhar_trecho(codigo_trecho: str) -> str:
    """Detalha um trecho pelo código (ex.: SIM0002): prioridade atual, últimos eventos do sensor
    (buracos e reportes, com profundidade e umidade) e últimas detecções de visão computacional
    (confiança do modelo). Se o código não existir, informa isso e lista os códigos válidos."""
    c = conexao()
    uid = codigo_trecho.strip().upper()
    if not banco.trecho_existe(c, uid):
        return _js({"erro": f"Trecho {uid} não cadastrado.", "codigos_validos": [t["uid"] for t in banco.listar_trechos(c)]})
    return _js({
        "prioridade": banco.prioridade_do_trecho(c, uid),
        "ultimos_eventos_iot": banco.eventos_do_trecho(c, uid, 10),
        "ultimas_deteccoes_visao": banco.deteccoes_do_trecho(c, uid, 10),
    })


@tool
def ultimos_eventos_iot(quantidade: int = 10) -> str:
    """Últimos eventos recebidos dos dispositivos ESP32 por MQTT (buracos, reportes, trocas de trecho,
    alertas recebidos), com data/hora, dispositivo e trecho."""
    return _js(banco.ultimos_eventos(conexao(), max(1, min(int(quantidade), 50))))


@tool
def status_dispositivos() -> str:
    """Status online/offline de cada dispositivo ESP32 conhecido e quando foi atualizado."""
    s = banco.status_dispositivos(conexao())
    return _js(s) if s else "Nenhum dispositivo registrado ainda."


# ------------------------------------------------------------------- RAG
@tool
def buscar_base_conhecimento(pergunta: str) -> str:
    """Busca na base de conhecimento do projeto (procedimento de triagem e vistoria, guia do cidadão
    para reportar buracos e pedir ressarcimento em São Paulo, fórmula de prioridade, detalhes dos
    módulos IoT e de visão, ODS, FAQ). Retorna os trechos mais relevantes com a fonte. Use SEMPRE
    antes de responder perguntas sobre procedimentos, direitos, limitações ou funcionamento do sistema,
    e cite a fonte na resposta."""
    import rag
    return rag.formatar_contexto(rag.buscar(pergunta, k=4))


# ------------------------------------------------------------------- ação
@tool
def registrar_reporte_cidadao(codigo_trecho: str, descricao: str) -> str:
    """Registra um reporte de buraco feito pelo cidadão em um trecho cadastrado. O reporte entra no
    banco como 'reporte_manual' e soma pontos na prioridade do trecho. Só chame depois que o cidadão
    confirmar o trecho e a descrição. Retorna a nova pontuação e o nível do trecho."""
    c = conexao()
    uid = codigo_trecho.strip().upper()
    if not banco.trecho_existe(c, uid):
        return _js({"erro": f"Trecho {uid} não cadastrado; peça ao cidadão para escolher um dos trechos válidos.",
                    "codigos_validos": [t["uid"] for t in banco.listar_trechos(c)]})
    descricao = descricao.strip()[:300]
    if len(descricao) < 5:
        return _js({"erro": "Descrição muito curta. Peça ao cidadão uma descrição do problema."})
    banco.inserir_reporte_cidadao(c, uid, descricao)
    p = banco.prioridade_do_trecho(c, uid)
    return _js({"ok": True, "trecho": p["nome"], "pontuacao": p["pontuacao"], "nivel": p["nivel"],
                "mensagem": "Reporte registrado no CitizenTech. Para abrir o protocolo oficial, use o SP156."})


@tool
def analisar_foto_buracos(caminho_imagem: str, codigo_trecho: str = "") -> str:
    """Analisa uma foto da via com o detector de buracos (YOLO ajustado) e devolve as detecções com a
    confiança do modelo e o caminho da imagem anotada. Se codigo_trecho for informado e existir, as
    detecções com confiança >= 0,5 são gravadas no banco e passam a contar na prioridade do trecho."""
    import cv2
    from detector import CONF_REGISTRO, DetectorBuracos

    caminho = Path(caminho_imagem).expanduser()
    if not caminho.exists():
        return _js({"erro": f"Imagem não encontrada: {caminho}"})
    try:
        det = DetectorBuracos()
    except FileNotFoundError as e:
        return _js({"erro": str(e)})
    r = det.detectar_imagem(str(caminho))
    saida = AQUI / "evidencias" / "fotos_analisadas"
    saida.mkdir(parents=True, exist_ok=True)
    anotada = saida / f"{caminho.stem}_anotada.jpg"
    cv2.imwrite(str(anotada), r.imagem_anotada)

    gravadas = 0
    uid = codigo_trecho.strip().upper()
    if uid:
        c = conexao()
        if banco.trecho_existe(c, uid):
            gravadas = det.registrar_no_banco(c, uid, caminho.name, r.deteccoes)
        else:
            uid = f"{uid} (não cadastrado; nada foi gravado)"
    return _js({
        "imagem": str(caminho), "imagem_anotada": str(anotada), "latencia_ms": round(r.latencia_ms, 1),
        "limiar_registro": CONF_REGISTRO, "trecho": uid or None, "deteccoes_gravadas_no_banco": gravadas,
        "deteccoes": [{"classe": d.classe, "confianca": round(d.confianca, 3), "bbox": d.bbox} for d in r.deteccoes],
        "aviso": "A detecção automática é uma triagem; a gravidade real exige vistoria presencial.",
    })


@tool
def enviar_alerta_esp32(device_id: str = "esp32-01", motivo: str = "trecho crítico à frente") -> str:
    """Envia um comando de ALERTA por MQTT ao dispositivo ESP32 do veículo (o LED vermelho pisca por 5 s).
    Use apenas quando a equipe de zeladoria pedir para alertar o veículo, ou quando um trecho de
    prioridade ALTA justificar o aviso. Em modo de demonstração sem rede, apenas simula o envio."""
    cmd = {"acao": "alerta", "motivo": motivo[:120], "origem": "agente-genai"}
    topico = config.topico(device_id, "comando")
    if os.getenv("CITIZENTECH_MQTT_DRY_RUN") == "1":
        return _js({"simulado": True, "topico": topico, "comando": cmd})
    try:
        import uuid
        import paho.mqtt.client as mqtt
        try:
            cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"citizentech-agente-{uuid.uuid4().hex[:6]}")
        except AttributeError:
            cli = mqtt.Client(client_id=f"citizentech-agente-{uuid.uuid4().hex[:6]}")
        cli.connect(config.MQTT_HOST, config.MQTT_PORTA, 30)
        cli.loop_start()
        info = cli.publish(topico, json.dumps(cmd, ensure_ascii=False), qos=1)
        info.wait_for_publish(timeout=10)
        cli.loop_stop(); cli.disconnect()
        return _js({"enviado": info.is_published(), "broker": f"{config.MQTT_HOST}:{config.MQTT_PORTA}",
                    "topico": topico, "comando": cmd})
    except Exception as e:  # rede indisponível: não derruba o agente
        return _js({"enviado": False, "erro": str(e), "topico": topico, "comando": cmd})


FERRAMENTAS_CONSULTA = [listar_trechos, consultar_ranking_prioridade, detalhar_trecho, ultimos_eventos_iot,
                        status_dispositivos, buscar_base_conhecimento]
FERRAMENTAS_ACAO = [registrar_reporte_cidadao, analisar_foto_buracos, enviar_alerta_esp32]
TODAS = FERRAMENTAS_CONSULTA + FERRAMENTAS_ACAO
