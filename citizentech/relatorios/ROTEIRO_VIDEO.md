# Roteiro do vídeo de demonstração (GS + corte para o LinkedIn)

Duração alvo: **4–5 min** para a entrega (as três disciplinas pedem demonstração em vídeo) e um
**corte de 60–90 s** para o LinkedIn. Gravar a tela em 1080p com o terminal e o Gradio lado a lado;
a câmera do celular filma a maquete/ESP32 quando indicado.

| # | Tempo | O que aparece na tela | O que dizer (1 frase cada) |
|---|---|---|---|
| 1 | 0:00–0:20 | Capa + trecho do vídeo real da rua com buracos (sem anotação) | "Quase 52 mil pedidos de tapa-buraco em SP só no 1º semestre de 2026; a prefeitura só sabe quando alguém reclama." |
| 2 | 0:20–0:40 | Diagrama da arquitetura (README) | "Três módulos, um banco: sensores no veículo, câmera com YOLO e um agente de IA que prioriza e responde o cidadão." |
| 3 | 0:40–1:30 | **IoT:** ESP32 na maquete; Serial Monitor + `receptor_mqtt.py` no terminal; passar o carrinho pelo rebaixo de 5 cm → `[ALERTA] Buraco GRAVE…`; apertar o botão → reporte; mostrar Telegram se configurado | "Sensor de distância mede a profundidade, DHT22 marca a umidade, botão registra o reporte; tudo via MQTT para o banco." |
| 4 | 1:30–1:45 | `python citizentech/banco.py --resumo` | "A Av. Lins já está em prioridade alta com 9 pontos." |
| 5 | 1:45–2:45 | **Visão:** `processar_video.py --video midia/rua.mp4 --trecho SIM0005 --gravar-banco` rodando; depois o vídeo anotado (caixas vermelhas com confiança, contador, FPS) | "YOLO11n ajustado em 500 fotos públicas roda em CPU a X FPS; cada buraco rastreado vira um registro, com a confiança, no mesmo banco." |
| 6 | 2:45–3:00 | `banco.py --resumo` de novo: o trecho da rua filmada entrou no ranking | "A rua que acabei de filmar entrou no ranking só com visão." |
| 7 | 3:00–4:00 | **GenAI:** Gradio aba Zeladoria → "Gerar relatório de inspeção" (mostrar o rastro de ferramentas à direita) → "Alertar veículo" → LED vermelho piscando no ESP32 (câmera do celular) | "O agente consulta o banco, monta o relatório com rota e manda o comando de alerta para o carro, que pisca o LED." |
| 8 | 4:00–4:40 | Aba Cidadão: pergunta "como reporto um buraco?" (resposta cita SP156 e a fonte); envia uma foto → detecções → "registrar no trecho X" → ranking muda | "O cidadão recebe a orientação com fonte e o reporte dele alimenta a mesma prioridade." |
| 9 | 4:40–5:00 | Slide final: métricas (mAP, FPS), limitações, ODS 11/9/3, nomes e RMs | "Triagem automática, vistoria humana. Próximo passo: GPS real e re-treino com fotos de SP." |

## Corte para o LinkedIn (60–90 s)
Cenas 1 (10 s) → 5 (20 s, o vídeo anotado é o "gancho") → 7 (20 s, relatório + LED) → 8 (15 s, foto do
cidadão) → 9 (10 s). Legendas grandes, sem áudio obrigatório. Texto do post: problema (1 linha), o que
construímos (3 bullets: IoT, YOLO, agente), um número (FPS/mAP) e o aprendizado principal.

## Checklist antes de gravar
- [ ] `midia/rua.mp4` no repositório e `banco.py --cadastrar SIM0005 "Rua …" "Bairro"` feito.
- [ ] `processar_video.py` já rodado uma vez (o vídeo anotado fica em `citizentech/visao/saida/`).
- [ ] `ANTHROPIC_API_KEY` exportada e `app_gradio.py` aberto em http://localhost:7860.
- [ ] ESP32 ligado na mesma base MQTT do `config.py` (`TOPICO_BASE`) e `receptor_mqtt.py` rodando.
- [ ] Zoom do terminal e do navegador em 125 % para leitura no celular.
