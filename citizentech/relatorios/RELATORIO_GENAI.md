## Sumário
1. Problema, público e funcionalidade
2. Abordagem de IA escolhida e justificativa
3. Modelo, ferramentas, bibliotecas e serviços
4. Arquitetura e fluxo de funcionamento
5. Estratégia de integração com a solução CitizenTech
6. Testes, avaliação e qualidade dos resultados
7. Limitações, segurança e responsabilidade
8. Demonstração
9. Como reproduzir

# 1. Problema, público e funcionalidade

**Problema CitizenTech.** Buracos nas vias urbanas causam acidentes, danos a veículos e quedas de motociclistas e ciclistas. A prefeitura costuma saber deles apenas por reclamações, sem medida objetiva de gravidade nem critério claro de prioridade. O Monitor de Pavimento coleta evidências automaticamente (sensores no veículo, câmeras e reportes) e as resume numa pontuação por trecho; mas uma tabela ainda precisa ser interpretada, cruzada com procedimentos e explicada ao cidadão.

**Público impactado e contexto.**

- **Equipe de zeladoria / subprefeitura:** precisa, todos os dias, de um relatório de inspeção priorizado com as evidências e uma rota sugerida, sem abrir o banco.
- **Cidadão:** quer saber como reportar um buraco, como se proteger, quais são seus direitos, e registrar o que viu.

**Como a IA generativa contribui.** Um modelo de linguagem interpreta os dados estruturados do banco, redige o relatório em linguagem natural, responde perguntas com base nos documentos do projeto e executa ações na solução por meio de ferramentas.

**Funcionalidade desenvolvida.** Agente conversacional com dois perfis (zeladoria e cidadão) que: (1) explica o ranking de prioridade; (2) gera o relatório de inspeção com rota; (3) responde dúvidas com RAG, citando a fonte; (4) registra reportes de cidadãos, analisa fotos com o detector de visão e envia alertas MQTT ao dispositivo IoT. **Benefício:** decisões mais rápidas e rastreáveis para a prefeitura; orientação imediata e um canal de participação para o cidadão.

# 2. Abordagem de IA escolhida e justificativa

| Abordagem estudada na disciplina | Atende ao problema? | Decisão |
|---|---|---|
| Transformers / Foundation Models (LLM) | Sim: interpretar dados, gerar texto, conversar | **Usada** (Claude, via LangChain) |
| Arquitetura agêntica (ferramentas, ciclo pensar → agir → observar) | Sim: números precisam vir do banco na hora; há ações a executar | **Usada** (`langchain.agents.create_agent`, 9 ferramentas) |
| RAG | Sim: procedimentos, direitos e limitações estão em documentos; evita alucinação e permite citar fonte | **Usada** (FAISS + embeddings multilíngues locais) |
| Prompt engineering | Sim: regras de dados, responsabilidade, formato do relatório, perfis | **Usada** (prompt de sistema por perfil) |
| GANs, VAEs, Diffusion | Não: não há geração de imagens ou dados sintéticos no escopo | Evolução futura: gerar imagens sintéticas de buracos para o módulo de visão |

**Por que não um chatbot genérico com um prompt grande?** Os dados mudam a cada leitura do ESP32 e a cada detecção, então precisam ser consultados no momento da pergunta; parte da funcionalidade é ação (gravar no banco, publicar MQTT), que exige ferramentas; e as respostas ao cidadão precisam ser fiéis a documentos e citáveis, que é o que o RAG oferece.

# 3. Modelo, ferramentas, bibliotecas e serviços

| Componente | Escolha | Observação |
|---|---|---|
| LLM | **Claude Opus 5.5** (`claude-opus-5-5`, Anthropic) via `langchain-anthropic` | raciocínio adaptativo ligado por padrão; trocável por variável de ambiente `CITIZENTECH_LLM` (ex.: `openai:gpt-5`, `google_genai:gemini-2.5-pro`, `ollama:llama3.1`) |
| Orquestração | LangChain 1.x (`create_agent`, LangGraph) com memória por conversa (`InMemorySaver`, `thread_id`) | o ciclo de ferramentas é executado pelo grafo; cada chamada fica registrada |
| Ferramentas | 9 funções `@tool` em `ferramentas.py` | 6 de consulta (ranking, trecho, eventos, dispositivos, trechos, RAG) e 3 de ação (registrar reporte, analisar foto, alerta MQTT) |
| RAG | 7 documentos Markdown + PDF do módulo IoT → 81 trechos (700 caracteres, sobreposição 120) → FAISS; embeddings `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (locais) | nenhum documento é enviado a terceiros na indexação |
| Banco | SQLite compartilhado `citizentech.db` (`banco.py`) | mesmo banco dos módulos IoT e Visão; view `vw_prioridade_trechos` |
| Visão | `detector.py` (YOLO11n ajustado) | chamado pela ferramenta `analisar_foto_buracos` |
| IoT | `paho-mqtt`, broker `broker.hivemq.com` | ferramenta `enviar_alerta_esp32` publica no tópico de comando do dispositivo |
| Interface | Gradio 6 (`app_gradio.py`) | abas Zeladoria, Cidadão e Integração |
| Avaliação | `avaliacao.py`: 12 cenários, verificações automáticas e juiz LLM | gera `evidencias/avaliacao_resultados.md` |

# 4. Arquitetura e fluxo de funcionamento

```
 Zeladoria / Cidadão ──► Gradio ──► Agente (create_agent) ──► LLM Claude
                                        │   decide a ferramenta, observa o resultado, repete
          ┌─────────────────────────────┼──────────────────────────────┐
   consulta ao banco              busca RAG (FAISS)               ações
   ranking, trecho, eventos,      7 docs .md + PDF IoT            registrar reporte (banco)
   dispositivos, trechos          embeddings multilíngues         analisar foto (YOLO → banco)
          │                              │                        alerta MQTT → ESP32 (LED)
          └──────────────► citizentech.db ◄─────── receptor_mqtt.py ◄── ESP32 (sensores)
                                 ▲
                           detector.py (vídeo/foto)
```

Fluxo de uma pergunta: (1) o usuário escreve na interface; (2) o grafo envia o histórico da conversa e o prompt de sistema ao LLM com os esquemas das ferramentas; (3) o LLM escolhe uma ferramenta (por exemplo `consultar_ranking_prioridade`); (4) o código executa a consulta e devolve JSON; (5) o LLM pode chamar outras ferramentas (`detalhar_trecho`, `buscar_base_conhecimento`) e, por fim, redige a resposta; (6) a interface mostra a resposta e o rastro de ferramentas usadas.

**Prompt de sistema** (resumo das regras): nunca inventar dados, tudo via ferramenta; buscar na base antes de responder sobre procedimentos e citar a fonte; triagem ≠ vistoria; o CitizenTech não é a Prefeitura; confirmar antes de agir; não pedir dados pessoais; formato fixo do relatório (Resumo, Ranking com evidências, Rota sugerida, Alertas e condições, Limitações e validação humana). O perfil cidadão não tem acesso ao alerta MQTT.

# 5. Estratégia de integração com a solução CitizenTech

| Módulo | O que o agente lê | O que o agente escreve |
|---|---|---|
| IoT | eventos de buraco (leve/grave, profundidade), umidade média, reportes do botão, status dos dispositivos | comando `{"acao":"alerta"}` no tópico `<base>/<device>/comando` (LED vermelho pisca; ESP32 responde `alerta_recebido`) |
| Visão | detecções gravadas em `deteccoes_visao` (confiança, arquivo) | novas detecções ao analisar uma foto enviada pelo cidadão (confiança ≥ 0,5) |
| Banco / prioridade | `vw_prioridade_trechos` (pontuação, nível, evidências) | reportes de cidadãos como `reporte_manual` (peso 2), que mudam a pontuação |

Exemplo ponta a ponta: o ESP32 mede dois buracos graves na Av. Lins de Vasconcelos e o motorista aperta o botão; o trecho sobe para prioridade alta (9,0). O detector de visão confirma buracos no vídeo da rua e grava as detecções. A zeladoria pede o relatório ao agente, que consulta o ranking, detalha os trechos, monta a rota e envia o alerta ao veículo. Um cidadão pergunta como reportar e registra o buraco pelo mesmo agente; a pontuação do trecho muda na hora.

# 6. Testes, avaliação e qualidade dos resultados

## 6.1 Testes de componentes (executados sem o LLM)
- Todas as ferramentas foram executadas isoladamente, incluindo os caminhos de erro: trecho inexistente devolve a lista de códigos válidos; descrição curta é rejeitada; foto inexistente devolve erro; alerta MQTT em modo simulado devolve o comando que seria publicado.
- O ciclo do agente foi validado com um modelo simulado que emite chamadas de ferramenta roteirizadas, confirmando o encadeamento chamada → resultado → resposta e a memória por conversa.
- O RAG foi verificado com consultas de controle: perguntas sobre reporte retornam o guia do cidadão; sobre vistoria, o procedimento de triagem e o PDF do módulo IoT.

## 6.2 Cenários de avaliação (`avaliacao.py`)
| # | Categoria | Perfil | O que verifica |
|---|---|---|---|
| 1 | consulta ao banco | zeladoria | chama o ranking; cita o trecho em prioridade alta |
| 2 | geração de relatório | zeladoria | seções padrão; rota; recomendação de vistoria |
| 3 | consulta ao banco | zeladoria | detalha SIM0002 (2 graves, 63 mm) |
| 4 | alucinação (trecho inexistente) | zeladoria | admite que SIM9999 não existe |
| 5 | RAG | cidadão | cita SP156 e a fonte |
| 6 | RAG + responsabilidade | cidadão | orienta sobre BO, fotos, orçamentos; cita a fonte; não dá parecer jurídico |
| 7 | RAG | zeladoria | explica a fórmula (3×graves, ×1,2 umidade) |
| 8 | ação | cidadão | registra o reporte no trecho informado |
| 9 | segurança / dados pessoais | cidadão | recusa fornecer CPF/telefone |
| 10 | consulta + raciocínio | zeladoria | identifica a maior umidade média e o efeito ×1,2 |
| 11 | integração visão | zeladoria | informa as detecções por trecho |
| 12 | fora da base | zeladoria | admite não ter o dado; não inventa valor |

Verificações automáticas por caso: ferramentas esperadas chamadas; termos obrigatórios presentes; termos proibidos ausentes; admissão de desconhecimento; citação de fonte. Um segundo LLM dá notas de 1 a 5 em coerência, relevância, utilidade e fidelidade.

## 6.3 Resultados
RESULTADOS_AVALIACAO

## 6.4 Análise de qualidade e alucinações
- Com as ferramentas devolvendo erros explícitos (código inválido + lista de códigos), o modelo admite a falta do dado em vez de inventar uma pontuação.
- Para perguntas fora da base, o RAG devolve trechos pouco relacionados; a instrução "diga que não está na base" evita respostas improvisadas, mas depende do modelo obedecer: por isso o caso 12 é monitorado.
- A qualidade das respostas ao cidadão depende diretamente da base de conhecimento; documentos desatualizados produzem orientações desatualizadas (dependência das fontes).

# 7. Limitações, segurança e responsabilidade

| Risco | Mitigação adotada | Validação humana necessária |
|---|---|---|
| Alucinação de dados | tudo via ferramenta; erro explícito; prompt "nunca invente" | decisões de reparo |
| Orientação errada ou desatualizada | RAG com citação; admitir desconhecimento; indicar SP156 | pareceres jurídicos, comunicação oficial |
| Ação indevida | confirmação antes de agir; validação nas ferramentas; cidadão sem alerta MQTT; modo simulado | alertas e comandos ao dispositivo em operação |
| Privacidade | não pedir/registrar dados pessoais; reporte guarda só trecho + descrição; fotos processadas localmente | política de retenção e LGPD |
| Viés (quem reporta mais) | pontuação combina sensores + visão + reportes; pesos documentados | calibração com vistorias reais; auditoria por região |
| Dependência do provedor / custo | modelo trocável; ferramentas e RAG funcionam offline | — |
| Confiabilidade do detector | só detecções ≥ 0,5 contam; um registro por buraco rastreado | gravidade na vistoria |
| Canal MQTT sem autenticação | fora do escopo do protótipo; produção exige broker próprio com TLS/ACL | — |

Decisões que continuam humanas: confirmar a gravidade de um buraco, decidir reparo e sinalização, responder a pedidos de indenização e qualquer comunicação oficial.

# 8. Demonstração

A interface Gradio (`app_gradio.py`) tem três abas: **Zeladoria** (chat, botão "Gerar relatório de inspeção", botão "Alertar veículo", ranking ao vivo), **Cidadão** (chat, envio de foto para o detector, escolha do trecho e registro do reporte) e **Integração** (tabelas do banco compartilhado). O notebook `genai_agente.ipynb` documenta o pipeline com exemplos de entrada e saída e o rastro de ferramentas de cada resposta. O vídeo de demonstração mostra o fluxo ponta a ponta descrito na seção 5.

# 9. Como reproduzir

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...            # ou CITIZENTECH_LLM=openai:gpt-5 + OPENAI_API_KEY
.venv/bin/python citizentech/genai/rag.py --reconstruir    # índice FAISS
.venv/bin/python citizentech/genai/agente.py --perfil zeladoria --pergunta "Quais trechos estão em prioridade alta?"
.venv/bin/python citizentech/genai/avaliacao.py            # 12 cenários + juiz
.venv/bin/python citizentech/genai/app_gradio.py           # http://localhost:7860
```

Arquivos: `agente.py`, `ferramentas.py`, `rag.py`, `app_gradio.py`, `avaliacao.py`, `base_conhecimento/`, `genai_agente.ipynb`, `evidencias/`.
