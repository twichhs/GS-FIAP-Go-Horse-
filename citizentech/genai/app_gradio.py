"""Interface Gradio do agente CitizenTech.

Abas:
  Zeladoria  - chat com o agente (perfil zeladoria), botão "Relatório de inspeção", ranking ao vivo
  Cidadão    - chat (perfil cidadão), envio de foto para o detector de buracos, registro de reporte
  Integração - tabelas do banco compartilhado (ranking, últimos eventos, dispositivos)

Execução (na raiz do projeto):
    export ANTHROPIC_API_KEY=...   # ou CITIZENTECH_LLM=openai:gpt-5 + OPENAI_API_KEY
    python citizentech/genai/app_gradio.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import gradio as gr
import pandas as pd

AQUI = Path(__file__).resolve().parent
try:  # .env na raiz do repositório (ANTHROPIC_API_KEY, CITIZENTECH_LLM, ...)
    from dotenv import load_dotenv
    load_dotenv(AQUI.parent.parent / ".env")
except ImportError:
    pass
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))

import banco  # noqa: E402
from agente import PROMPT_RELATORIO, criar_agente, perguntar  # noqa: E402

_agentes: dict[str, object] = {}


def agente(perfil: str):
    if perfil not in _agentes:
        _agentes[perfil] = criar_agente(perfil)
    return _agentes[perfil]


def conversar(mensagem: str, historico: list, perfil: str, thread: str):
    """Callback do chat: chama o agente e devolve o histórico atualizado + rastro das ferramentas."""
    mensagem = (mensagem or "").strip()
    if not mensagem:
        return historico, "", ""
    historico = (historico or []) + [{"role": "user", "content": mensagem}]
    try:
        resposta, passos = perguntar(agente(perfil), mensagem, thread_id=thread)
    except Exception as e:  # mostra o erro no chat em vez de derrubar a interface
        resposta, passos = f"Erro ao chamar o modelo: {e}", []
    historico.append({"role": "assistant", "content": resposta or "(sem resposta)"})
    rastro = "\n".join(
        f"→ {p['ferramenta']}({p['argumentos']})" if "ferramenta" in p else f"← {p['resultado_de']}: {p['resumo'][:120]}…"
        for p in passos
    ) or "(nenhuma ferramenta chamada)"
    return historico, "", rastro


def ranking_df() -> pd.DataFrame:
    c = banco.conectar(); banco.inicializar(c)
    linhas = banco.prioridades(c, apenas_com_registro=False)
    cols = ["uid", "nome", "bairro", "pontuacao", "nivel", "graves", "leves", "reportes", "deteccoes_visao",
            "prof_max_mm", "umidade_media"]
    return pd.DataFrame([{k: l.get(k) for k in cols} for l in linhas])


def eventos_df() -> pd.DataFrame:
    c = banco.conectar(); banco.inicializar(c)
    return pd.DataFrame(banco.ultimos_eventos(c, 20))


def dispositivos_df() -> pd.DataFrame:
    c = banco.conectar(); banco.inicializar(c)
    return pd.DataFrame(banco.status_dispositivos(c) or [{"device_id": "-", "status": "-", "atualizado_em": "-"}])


def opcoes_trechos() -> list[str]:
    c = banco.conectar(); banco.inicializar(c)
    return [f"{t['uid']} · {t['nome']}" for t in banco.listar_trechos(c)]


def analisar_foto(caminho: str | None, trecho_opcao: str | None):
    """Roda o detector diretamente (sem LLM) para mostrar a imagem anotada."""
    if not caminho:
        return None, "Envie uma foto primeiro."
    sys.path.insert(0, str(AQUI.parent / "visao"))
    from detector import DetectorBuracos
    try:
        det = DetectorBuracos()
    except FileNotFoundError as e:
        return None, str(e)
    r = det.detectar_imagem(caminho)
    import cv2
    anot = cv2.cvtColor(r.imagem_anotada, cv2.COLOR_BGR2RGB)
    resumo = (f"{len(r.confirmadas)} buraco(s) com confiança ≥ 0,5 e {len(r.deteccoes) - len(r.confirmadas)} "
              f"detecção(ões) incerta(s) | latência {r.latencia_ms:.0f} ms | "
              f"confianças: {[round(d.confianca, 2) for d in r.deteccoes]}")
    return anot, resumo


def mensagem_para_foto(caminho: str | None, trecho_opcao: str | None) -> str:
    uid = (trecho_opcao or "").split(" · ")[0].strip()
    if not caminho:
        return ""
    return (f"Enviei uma foto da via em {caminho}. Analise com o detector de buracos"
            + (f" e, se encontrar buracos, grave as detecções no trecho {uid}" if uid else "")
            + ". Explique o resultado de forma simples.")


with gr.Blocks(title="CitizenTech · Monitor de Pavimento") as app:
    gr.Markdown("# CitizenTech · Monitor de Pavimento\nAgente generativo integrado aos módulos IoT e Visão Computacional.")
    thread_zel = gr.State(lambda: f"zel-{uuid.uuid4().hex[:6]}")
    thread_cid = gr.State(lambda: f"cid-{uuid.uuid4().hex[:6]}")

    with gr.Tab("Zeladoria"):
        with gr.Row():
            with gr.Column(scale=3):
                chat_z = gr.Chatbot(label="Agente (perfil zeladoria)", height=460)
                with gr.Row():
                    txt_z = gr.Textbox(placeholder="Ex.: Quais trechos precisam de vistoria esta semana?", scale=5, show_label=False)
                    btn_z = gr.Button("Enviar", scale=1, variant="primary")
                with gr.Row():
                    btn_rel = gr.Button("Gerar relatório de inspeção")
                    btn_alerta = gr.Button("Alertar veículo no trecho crítico")
            with gr.Column(scale=2):
                rastro_z = gr.Textbox(label="Ferramentas usadas pelo agente", lines=12)
                btn_rank = gr.Button("Atualizar ranking")
                tab_rank = gr.Dataframe(value=ranking_df, label="Ranking de prioridade (vw_prioridade_trechos)")
        perfil_z = gr.State("zeladoria")
        btn_z.click(conversar, [txt_z, chat_z, perfil_z, thread_zel], [chat_z, txt_z, rastro_z])
        txt_z.submit(conversar, [txt_z, chat_z, perfil_z, thread_zel], [chat_z, txt_z, rastro_z])
        btn_rel.click(lambda h, p, t: conversar(PROMPT_RELATORIO, h, p, t), [chat_z, perfil_z, thread_zel], [chat_z, txt_z, rastro_z])
        btn_alerta.click(lambda h, p, t: conversar(
            "Identifique o trecho de maior prioridade e, se ele estiver em nível alta, envie o alerta ao ESP32 esp32-01 "
            "informando o motivo. Confirme o que foi feito.", h, p, t), [chat_z, perfil_z, thread_zel], [chat_z, txt_z, rastro_z])
        btn_rank.click(ranking_df, None, tab_rank)

    with gr.Tab("Cidadão"):
        with gr.Row():
            with gr.Column(scale=3):
                chat_c = gr.Chatbot(label="Agente (perfil cidadão)", height=460)
                with gr.Row():
                    txt_c = gr.Textbox(placeholder="Ex.: Como eu reporto um buraco na minha rua?", scale=5, show_label=False)
                    btn_c = gr.Button("Enviar", scale=1, variant="primary")
                rastro_c = gr.Textbox(label="Ferramentas usadas pelo agente", lines=5)
            with gr.Column(scale=2):
                foto = gr.Image(type="filepath", label="Foto da via (opcional)")
                trecho_sel = gr.Dropdown(choices=opcoes_trechos(), label="Trecho", value=None)
                btn_det = gr.Button("1) Detectar buracos na foto")
                foto_anot = gr.Image(label="Detecções (vermelho = confirmada, amarelo = incerta)")
                resumo_det = gr.Textbox(label="Resumo do detector", lines=3)
                btn_env = gr.Button("2) Enviar resultado ao agente", variant="primary")
        perfil_c = gr.State("cidadao")
        btn_c.click(conversar, [txt_c, chat_c, perfil_c, thread_cid], [chat_c, txt_c, rastro_c])
        txt_c.submit(conversar, [txt_c, chat_c, perfil_c, thread_cid], [chat_c, txt_c, rastro_c])
        btn_det.click(analisar_foto, [foto, trecho_sel], [foto_anot, resumo_det])
        btn_env.click(lambda f, t, h, p, th: conversar(mensagem_para_foto(f, t), h, p, th),
                      [foto, trecho_sel, chat_c, perfil_c, thread_cid], [chat_c, txt_c, rastro_c])

    with gr.Tab("Integração (banco compartilhado)"):
        gr.Markdown("Dados gravados pelos módulos IoT (ESP32 → MQTT → receptor) e Visão (YOLO), lidos pelo agente.")
        btn_atualiza = gr.Button("Atualizar")
        tab_rank2 = gr.Dataframe(value=ranking_df, label="Ranking de prioridade")
        tab_ev = gr.Dataframe(value=eventos_df, label="Últimos eventos IoT")
        tab_dev = gr.Dataframe(value=dispositivos_df, label="Dispositivos")
        btn_atualiza.click(lambda: (ranking_df(), eventos_df(), dispositivos_df()), None, [tab_rank2, tab_ev, tab_dev])

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, share=False)
