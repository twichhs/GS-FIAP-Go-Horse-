# CitizenTech · Monitor de Pavimento — visão geral da solução

## O que é
O Monitor de Pavimento é um protótipo da Global Solution 2026.2 (FIAP) dentro do tema
CitizenTech: tecnologia para melhorar a vida do cidadão nas cidades. O problema escolhido
é a **detecção e priorização de buracos nas vias urbanas**.

Hoje a prefeitura só fica sabendo de um buraco quando alguém reclama (por exemplo pelo
SP156). O processo é reativo, sem medida objetiva de gravidade e sem critério claro para
priorizar vistorias. O Monitor de Pavimento coleta dados de forma contínua e automática,
usando veículos que já circulam pela cidade (ônibus, viaturas da zeladoria, caminhões de
coleta) e imagens de câmeras, e transforma tudo isso em uma **lista priorizada de trechos
para inspeção**.

## Público beneficiado
- **Cidadãos que usam as vias**: motoristas, motociclistas, ciclistas, pedestres e
  passageiros de ônibus. Ganham vias mais seguras e reparos mais rápidos nos pontos críticos.
- **Equipes municipais de zeladoria e subprefeituras**: recebem uma lista priorizada de
  trechos, com base em medidas objetivas, e não apenas no volume de reclamações.

## Os três módulos
| Módulo | O que faz | Como se conecta aos outros |
|---|---|---|
| **IoT (sensores)** | Um ESP32 instalado no veículo mede a profundidade de irregularidades com um sensor de distância (VL53L0X), registra temperatura e umidade (DHT22) e recebe reportes manuais pelo botão. Publica tudo por MQTT. | O receptor grava leituras e eventos no banco compartilhado `citizentech.db`. Recebe comandos de volta (alerta de trecho crítico). |
| **Visão Computacional** | Um detector YOLO ajustado para buracos analisa fotos e vídeos e devolve caixas delimitadoras com a confiança do modelo. | Cada detecção com confiança suficiente é gravada no banco, associada a um trecho. |
| **IA Generativa (agente)** | Um agente com ferramentas e RAG lê o banco, explica o ranking em linguagem natural, gera o relatório de inspeção e responde dúvidas do cidadão. | Consulta a view de prioridade, as detecções e esta base de conhecimento; pode registrar reportes de cidadãos e enviar comandos MQTT ao ESP32. |

## Conceitos importantes
- **Trecho**: um segmento de via identificado por um código (ex.: `SIM0002`), com nome da
  rua, faixa de numeração, bairro e coordenadas. Todas as leituras, eventos e detecções
  são associadas a um trecho. No protótipo a localização é um **GPS simulado**: o trecho
  atual é informado ao ESP32 por comando MQTT.
- **Evento de buraco (IoT)**: gerado quando o sensor de distância mede uma profundidade
  acima do limiar. `leve` entre 15 mm e 39 mm; `grave` a partir de 40 mm (escala da maquete).
- **Reporte manual**: o motorista aperta o botão do dispositivo, ou o cidadão registra um
  reporte pelo assistente. Conta pontos na prioridade do trecho.
- **Detecção visual**: caixa delimitadora produzida pelo modelo YOLO em uma imagem ou em um
  quadro de vídeo, com uma confiança entre 0 e 1. Só detecções com confiança **≥ 0,5**
  entram na pontuação.
- **Pista úmida**: umidade relativa do ar ≥ 85% medida pelo DHT22. A infiltração de água é
  a principal causa de formação de buracos, então trechos com umidade média alta recebem
  peso maior.

## Fórmula de prioridade (view `vw_prioridade_trechos`)
```
pontuação = (3 × buracos graves + 1 × irregularidades leves
             + 2 × reportes manuais + 2 × detecções visuais com confiança ≥ 0,5)
            × 1,2 se a umidade média do trecho for ≥ 80%
```
Níveis: **alta** quando pontuação ≥ 8 · **média** quando ≥ 4 · **baixa** quando > 0 ·
**sem registro** quando 0.

A pontuação é uma **heurística de triagem** definida pelo grupo. Ela serve para ordenar
as vistorias, e **não substitui a vistoria técnica presencial**, que continua necessária
para atestar a gravidade real e decidir o reparo.

## Ações automáticas já implementadas
- Buraco grave ou reporte manual → alerta no console e no Telegram da zeladoria.
- Trecho atinge prioridade alta → alerta com o resumo das evidências.
- Veículo entra em trecho de prioridade alta → comando MQTT ao ESP32, que pisca o LED
  vermelho ("trecho crítico à frente").
