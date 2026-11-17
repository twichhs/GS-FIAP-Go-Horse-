## Sumário
1. Problema, nicho e papel na solução integrada
2. Dados: bases públicas, tratamento e divisão sem vazamento
3. Modelo: arquitetura, transfer learning e treinamento
4. Avaliação: métricas, matriz de confusão, limiar e análise de erros
5. Desempenho: latência, FPS e hardware
6. Integração ao protótipo CitizenTech (imagem e vídeo)
7. Justificativa técnica das escolhas
8. Limitações e evolução
9. Como reproduzir

# 1. Problema, nicho e papel na solução integrada

O CitizenTech · Monitor de Pavimento é um protótipo integrado (IoT, Visão Computacional e IA Generativa) para **detectar e priorizar buracos nas vias urbanas**. Este relatório cobre o módulo de Visão Computacional, no nicho **Infraestrutura e Pavimentação**: localizar buracos em fotos e vídeos por **caixas delimitadoras**, apresentando a **confiança** do modelo em cada detecção.

Na solução integrada, cada detecção com confiança ≥ 0,5 é gravada no banco compartilhado (`citizentech.db`, tabela `deteccoes_visao`) e passa a contar com peso 2 na pontuação de prioridade do trecho (`vw_prioridade_trechos`), ao lado das medições de profundidade do módulo IoT e dos reportes manuais. O agente GenAI lê essa view para montar o relatório de inspeção da zeladoria. O objetivo é apoiar a **triagem** e otimizar as rotas de inspeção; a detecção não substitui a vistoria técnica presencial.

# 2. Dados

## 2.1 Bases públicas
| Base | Uso | Licença | Conteúdo |
|---|---|---|---|
| `rupesh002/pothole-detection-dataset` (Hugging Face; exportação Roboflow "pothole.v1i") | treino, validação e teste | MIT | 715 imagens 640×640, 1 classe (`pothole`), 1.269 caixas em formato YOLO |
| `Ryukijano/Pothole-detection-Yolov8` (Hugging Face; amostra da base Roboflow "Potholes Detection") | teste externo (generalização) | CC BY 4.0 | split de teste com 100 imagens 640×640, deduplicado para 88 fotos de origem |

## 2.2 Tratamento e divisão
As exportações do Roboflow incluem variações aumentadas da mesma foto (espelhamento horizontal), identificadas pelo sufixo `.rf.<hash>`. Para não contaminar a avaliação, o script `preparar_dados.py` agrupa os arquivos pela **foto de origem** e divide os grupos em 70 % / 15 % / 15 % (semente 42). Validação e teste recebem uma única variante por foto; o teste externo também é deduplicado. O resultado é verificado automaticamente: **zero fotos de origem compartilhadas** entre conjuntos.

| Conjunto | Fotos de origem | Imagens | Caixas |
|---|---|---|---|
| treino | 429 | 502 | 807 |
| validação | 92 | 92 | 187 |
| teste | 93 | 93 | 206 |
| teste externo | 88 | 88 | 232 |

Pré-processamento: as imagens já vêm redimensionadas para 640×640; o Ultralytics aplica *letterbox* para 640 px e normaliza os pixels para 0–1. Aumento de dados somente no treino: mosaico de 4 imagens, variação HSV, translação, escala e espelhamento horizontal (mosaico desligado nas 5 últimas épocas).

![Amostras de treino](../visao/evidencias/amostras_treino.png)
Figura 1. Amostras de treino com os rótulos (verde).

![Distribuição das caixas](../visao/evidencias/distribuicao_caixas.png)
Figura 2. Tamanho relativo das caixas e número de buracos por imagem. Muitos buracos ocupam menos de 10 % do lado da imagem, o que justifica manter 640 px.

# 3. Modelo

**Arquitetura: YOLO11n** (Ultralytics 8.4), detector de um estágio, *anchor-free*, com {{PARAMS_M}} M de parâmetros e {{GFLOPS}} GFLOPs a 640 px. É a menor variante da família, escolhida porque o protótipo roda em **CPU comum** e deve caber em um computador de bordo ou numa câmera veicular.

**Transfer learning:** pesos pré-treinados no COCO e ajuste fino de todas as camadas na base de buracos. **Treinamento:** {{EPOCAS}} épocas (melhor época {{MELHOR_EPOCA}} pela mAP@0,5:0,95 de validação), lote 8, otimizador AdamW (lr 0,002) escolhido automaticamente, *early stopping* com paciência 10, semente 42, executado em CPU pelo script `treinar.py`.

![Curvas de treino](../visao/evidencias/curvas_treino.png)
Figura 3. Perdas e métricas de validação por época.

# 4. Avaliação

## 4.1 Métricas de detecção
| Conjunto | Precisão | Recall | mAP@0,5 | mAP@0,5:0,95 | VP | FP | FN |
|---|---|---|---|---|---|---|---|
| teste (93 fotos da mesma base) | {{P_TESTE}} | {{R_TESTE}} | {{MAP50_TESTE}} | {{MAP5095_TESTE}} | {{VP_TESTE}} | {{FP_TESTE}} | {{FN_TESTE}} |
| teste externo (88 fotos de outra base) | {{P_EXT}} | {{R_EXT}} | {{MAP50_EXT}} | {{MAP5095_EXT}} | {{VP_EXT}} | {{FP_EXT}} | {{FN_EXT}} |

VP/FP/FN vêm da matriz de confusão do Ultralytics (confiança ≥ 0,25, IoU ≥ 0,45). A queda entre o teste interno e o externo mede o custo de mudar de câmera, cidade e estilo de anotação, e indica a necessidade de re-treino com fotos locais.

![Matriz de confusão](../visao/evidencias/matriz_confusao.png)
Figura 4. Matrizes de confusão nos dois conjuntos de teste.

## 4.2 Limiar de confiança
Precisão, recall e F1 foram calculados no teste para limiares de 0,05 a 0,95 (pareamento guloso por IoU ≥ 0,5). O melhor F1 ({{MELHOR_F1}}) ocorre no limiar {{MELHOR_F1_LIMIAR}}. Na integração usamos **dois limiares**: 0,25 para **exibir** a caixa (amarela, "incerta") e 0,50 para **registrar** no banco e pontuar o trecho (vermelha, "confirmada"). Em 0,5 o modelo obtém precisão {{P_05}}, recall {{R_05}} e F1 {{F1_05}}. A lógica: o módulo faz triagem e a vistoria confirma, então aceitamos recall alto na exibição e exigimos precisão maior no que altera a prioridade.

![Limiar de confiança](../visao/evidencias/limiar_confianca.png)
Figura 5. Precisão, recall e F1 por limiar de confiança.

## 4.3 Análise de acertos e erros
![Análise de erros](../visao/evidencias/analise_erros.png)
Figura 6. Linhas 1–2: imagens de teste com mais erros; linha 3: acertos limpos. Verde = rótulo, vermelho = acerto, laranja = falso positivo, "FN" = buraco perdido.

Padrões observados:

- **Falsos negativos** concentram-se em buracos pequenos ou distantes, em buracos parcialmente cobertos por água ou sombra e em grupos de buracos muito próximos, em que o modelo funde dois rótulos em uma caixa.
- **Falsos positivos** aparecem em remendos escuros, manchas de óleo, tampas de bueiro e sombras de borda bem definida, que compartilham a textura "mancha escura sobre asfalto". Em alguns casos o falso positivo é um buraco real não anotado, limitação do próprio rótulo.
- **Variação severa de iluminação** (contraluz, asfalto molhado refletindo o céu) reduz a confiança: várias detecções corretas ficam entre 0,25 e 0,5 e são exibidas como incertas sem entrar na pontuação.

# 5. Desempenho

Hardware de teste: **{{CPU}}** ({{NUCLEOS}} núcleos físicos, {{THREADS}} threads), {{RAM}} GB de RAM, **sem GPU**; {{SO}}; Python {{PYTHON}}, PyTorch {{TORCH}} (CPU), Ultralytics {{ULTRALYTICS}}, OpenCV {{OPENCV}}. Latência medida com lote 1, incluindo pré e pós-processamento, média de 30 imagens após aquecimento.

| Resolução de entrada | Latência média (ms) | p95 (ms) | FPS |
|---|---|---|---|
| 320 px | {{LAT_320}} | {{P95_320}} | {{FPS_320}} |
| 480 px | {{LAT_480}} | {{P95_480}} | {{FPS_480}} |
| 640 px | {{LAT_640}} | {{P95_640}} | {{FPS_640}} |

![Latência](../visao/evidencias/latencia.png)
Figura 7. Latência por imagem em CPU por resolução de entrada.

Processamento de vídeo (seção 6): {{VID_FRAMES}} quadros processados a {{VID_FPS}} FPS com rastreamento, latência média de {{VID_LAT}} ms por quadro ({{VID_RES}}, stride {{VID_STRIDE}}).

# 6. Integração ao protótipo CitizenTech

**Imagem estática.** `DetectorBuracos.detectar_imagem()` devolve caixas, confiança e a imagem anotada; `registrar_no_banco()` grava cada detecção confirmada em `deteccoes_visao`. No notebook, uma foto de teste gravada no trecho SIM0004 (sem registros) muda sua pontuação imediatamente na view de prioridade.

![Integração imagem](../visao/evidencias/integracao_imagem.png)
Figura 8. Resultado visual com a confiança de cada detecção (vermelho = confirmada, amarelo = incerta).

**Vídeo / monitoramento contínuo.** `DetectorBuracos.processar_video()` processa o vídeo quadro a quadro com rastreamento **ByteTrack**; cada buraco recebe um identificador e é gravado **uma única vez** no banco, com a maior confiança observada, evitando inflar a pontuação com uma detecção por quadro. O vídeo anotado mostra caixas, confiança, contador de buracos e FPS. O script `processar_video.py` faz o mesmo pela linha de comando para o vídeo real gravado na rua (pasta `midia/`).

![Integração vídeo](../visao/evidencias/integracao_video.png)
Figura 9. Quadros do vídeo anotado.

![Ranking após visão](../visao/evidencias/ranking_apos_visao.png)
Figura 10. Pontuação por trecho após a integração IoT + Visão: {{VID_PONTUACAO}}.

A interface Gradio do módulo GenAI usa o mesmo detector: o cidadão envia uma foto, vê as detecções com a confiança e o agente explica o resultado e registra o reporte.

# 7. Justificativa técnica das escolhas

| Decisão | Alternativas consideradas | Motivo |
|---|---|---|
| Detecção por caixas (YOLO) em vez de classificação | CNN classificadora "com/sem buraco" | a prefeitura precisa de onde e quantos; a caixa também permite rastrear no vídeo |
| YOLO11n | YOLO11s/m, SSD-MobileNet, Faster R-CNN | melhor relação qualidade × latência em CPU; 2,6 M de parâmetros cabem em dispositivo de borda |
| Transfer learning do COCO, ajuste completo | treinar do zero; congelar o backbone | base pequena (502 imagens) converge rápido a partir do COCO; ajuste completo adapta as texturas de asfalto |
| 640 px | 320/480 px | muitas caixas pequenas (figura 2); a latência a 640 ainda permite vídeo com stride |
| Dois limiares (0,25 exibir / 0,50 registrar) | um único limiar | triagem com recall alto na tela e precisão maior no que entra na pontuação |
| Divisão por foto de origem | divisão aleatória por arquivo | evita vazamento de variações aumentadas entre treino e teste |
| Teste externo | só teste interno | mede generalização para outra câmera/cidade |
| Rastreamento no vídeo | contar por quadro | um registro por buraco físico no banco |

# 8. Limitações e evolução

- Base de treino pequena e com pouca variedade de clima, noite e tipos de pavimento; a queda no teste externo mostra sensibilidade a domínio. Evolução: anotar fotos das vias de São Paulo captadas pela própria frota e re-treinar.
- Falsos positivos em remendos, tampas e sombras. Evolução: classe adicional "tampa/remendo" e mais exemplos negativos.
- O modelo não mede profundidade nem gravidade; isso vem do sensor IoT e da vistoria. Evolução: fusão temporal entre a detecção visual e a profundidade medida no mesmo instante.
- Rastreamento depende de câmera estável; curvas bruscas podem duplicar um buraco. Evolução: associar detecções por posição GPS.
- Latência em CPU limita a resolução/FPS. Evolução: exportar para ONNX/OpenVINO com quantização INT8.

# 9. Como reproduzir

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python citizentech/visao/preparar_dados.py      # baixa e divide as bases
.venv/bin/python citizentech/visao/treinar.py --epochs 30  # ~2-3 h em CPU; gera modelos/best.pt
jupyter nbconvert --execute --to notebook --inplace citizentech/visao/visao_computacional.ipynb
.venv/bin/python citizentech/visao/processar_video.py --video midia/rua.mp4 --trecho SIM0005 --gravar-banco
```

Arquivos: `preparar_dados.py`, `treinar.py`, `detector.py`, `processar_video.py`, `visao_computacional.ipynb`, `evidencias/` (figuras e `metricas_visao.json`), `modelos/best.pt`.
