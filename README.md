# CitizenTech · Monitor de Pavimento

**Global Solution 2026.2 · FIAP** — Protótipo integrado CitizenTech com IA para apoiar o cidadão.
Tema do grupo: **detecção e priorização de buracos nas vias urbanas**, em três disciplinas que
compartilham o mesmo problema, público e banco de dados.

| Disciplina | Módulo | Entregáveis |
|---|---|---|
| **IoT (Sensores)** | ESP32 com VL53L0X (profundidade), DHT22 (umidade/temperatura), botão e LEDs → MQTT → receptor → banco | `CitizenTech_Modulo_IoT.pdf` · `citizentech/iot/` |
| **Visão Computacional** | YOLO11n ajustado (transfer learning) para detectar buracos em fotos e vídeos, com confiança, latência/FPS e integração ao banco | `CitizenTech_Modulo_Visao.pdf` · `citizentech/visao/visao_computacional.ipynb` |
| **Generative AI and Advanced Nets** | Agente (LangChain + Claude) com 9 ferramentas e RAG: relatório de inspeção para a zeladoria, assistente do cidadão, ações no banco, no detector e no ESP32 | `CitizenTech_Modulo_GenAI.pdf` · `citizentech/genai/genai_agente.ipynb` · `citizentech/genai/app_gradio.py` |

```
 VL53L0X ─┐                                        ┌──> alertas (console / Telegram)
 DHT22   ─┼─> ESP32 ──MQTT──> receptor_mqtt.py ──> citizentech.db ──> agente GenAI ──> Gradio (zeladoria / cidadão)
 Botão   ─┘    ▲                                     ▲        ▲               │
 LEDs        ◄─┴───── comando "alerta" ◄─────────────┼────────┼───────────────┘
                                   detector.py (YOLO11n) ─────┘        foto do cidadão ──> detector ──> banco
                                   fotos e vídeo da via (midia/)
```

**Pontuação de prioridade por trecho** (`vw_prioridade_trechos`): `(3×graves + 1×leves + 2×reportes + 2×detecções visuais com confiança ≥ 0,5) × 1,2 se umidade média ≥ 80 %`. Alta ≥ 8 · média ≥ 4 · baixa > 0. É uma heurística de **triagem**: a vistoria presencial continua obrigatória.

## Estrutura

```
citizentech/
├── config.py, banco.py            # MQTT, SQLite compartilhado (tabelas + view de prioridade)
├── iot/                           # firmware ESP32, receptor MQTT, simulador, GPS simulado, evidências
├── visao/                         # preparar_dados.py, treinar.py, detector.py, processar_video.py, notebook, evidencias/, modelos/best.pt
├── genai/                         # agente.py, ferramentas.py, rag.py, app_gradio.py, avaliacao.py, base_conhecimento/, notebook, evidencias/
└── relatorios/                    # fontes Markdown dos PDFs + gerar_relatorios.py
midia/                             # vídeo/fotos reais da rua (entrada do módulo de visão)
ROTEIRO_VIDEO.md                   # roteiro da demonstração em vídeo
```

## Como rodar

```bash
python -m venv .venv && .venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
```

**IoT** (detalhes em `citizentech/README.md`)
```bash
.venv/bin/python citizentech/iot/receptor_mqtt.py            # terminal 1: assina o broker e grava no banco
.venv/bin/python citizentech/iot/simulador_esp32.py --cenario demo   # terminal 2 (ou o ESP32 físico)
.venv/bin/python citizentech/banco.py --resumo                # ranking de prioridade
```

**Visão computacional**
```bash
.venv/bin/python citizentech/visao/preparar_dados.py          # baixa 2 bases públicas, divide por foto de origem
.venv/bin/python citizentech/visao/treinar.py --epochs 30     # ~2-3 h em CPU → modelos/best.pt
.venv/bin/python citizentech/visao/processar_video.py --video midia/rua.mp4 --trecho SIM0005 --gravar-banco
.venv/bin/jupyter notebook citizentech/visao/visao_computacional.ipynb
```

**GenAI**
```bash
export ANTHROPIC_API_KEY=sk-ant-...     # ou CITIZENTECH_LLM=openai:gpt-5 + OPENAI_API_KEY
.venv/bin/python citizentech/genai/rag.py --reconstruir       # índice FAISS da base de conhecimento
.venv/bin/python citizentech/genai/app_gradio.py              # http://localhost:7860
.venv/bin/python citizentech/genai/avaliacao.py               # 12 cenários + juiz LLM → evidencias/
```

**Relatórios em PDF** (após executar os notebooks): `.venv/bin/python citizentech/relatorios/gerar_relatorios.py`

## Evidências
- IoT: `citizentech/iot/evidencias/` (logs do receptor e do simulador, ranking, últimos eventos) + fotos/prints do protótipo físico (seção 6.5 do PDF).
- Visão: `citizentech/visao/evidencias/` (figuras do notebook, `metricas_visao.json`) e `citizentech/visao/saida/` (vídeos anotados).
- GenAI: `citizentech/genai/evidencias/` (resultados da avaliação, fotos analisadas) e as saídas do notebook.

## ODS
ODS 11 (metas 11.2 e 11.7), ODS 9 (meta 9.1) e ODS 3 (meta 3.6).

## Integrantes
| Nome completo | RM |
|---|---|
| [preencher] | [preencher] |
