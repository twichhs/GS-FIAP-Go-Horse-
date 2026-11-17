# Procedimento operacional proposto — triagem e vistoria de pavimento

> Este documento descreve a **política proposta pelo grupo** para uso do Monitor de
> Pavimento pela equipe de zeladoria. Os prazos abaixo são metas internas sugeridas para o
> protótipo e não correspondem a normas oficiais do município.

## 1. Leitura diária do ranking
1. Consultar o ranking de prioridade por trecho (view `vw_prioridade_trechos`).
2. Separar os trechos por nível: **alta**, **média**, **baixa**.
3. Verificar, para cada trecho de prioridade alta, quais evidências sustentam a pontuação:
   número de buracos graves, irregularidades leves, reportes manuais e detecções visuais,
   além da profundidade máxima medida e da umidade média.

## 2. Metas de resposta sugeridas
| Nível | Pontuação | Ação recomendada | Meta de vistoria |
|---|---|---|---|
| Alta | ≥ 8 | Vistoria presencial prioritária; sinalização provisória se houver risco imediato (cones ou placa) | até 48 horas |
| Média | 4 a 7,9 | Incluir na rota de inspeção da semana | até 7 dias |
| Baixa | 0,1 a 3,9 | Monitorar; reavaliar se chover ou se surgirem novas evidências | até 30 dias |
| Sem registro | 0 | Nenhuma ação; o trecho continua sendo monitorado pelos veículos | — |

## 3. Critérios de desempate e agravantes
- **Profundidade máxima ≥ 40 mm** (escala da maquete) ou detecção visual com confiança
  ≥ 0,8: tratar como risco elevado para motociclistas e ciclistas.
- **Umidade média ≥ 80%**: a água acelera a degradação do pavimento; antecipar a vistoria.
- **Reporte manual + detecção visual no mesmo trecho**: duas fontes independentes
  confirmam o problema; aumentar a confiança na pontuação.
- **Trechos com transporte coletivo, escolas ou hospitais** nas proximidades devem ser
  vistoriados antes de outros com a mesma pontuação.

## 4. Montagem da rota de inspeção
1. Começar pelos trechos de prioridade alta, agrupando-os por bairro para reduzir o
   deslocamento.
2. Encaixar os trechos de prioridade média que estiverem no caminho.
3. Registrar, ao final, o resultado da vistoria (confirmado, reparado, falso positivo).

## 5. O que a vistoria presencial deve confirmar
- Dimensões reais do buraco (largura, comprimento e profundidade em centímetros).
- Se há risco estrutural (afundamento, erosão da base, vazamento de água).
- Se há risco imediato à circulação (faixa de rolamento, curva, área escolar).
- Necessidade de sinalização provisória antes do reparo.

## 6. Falsos positivos conhecidos
- Tampas de bueiro, manchas de óleo, remendos escuros e sombras fortes podem ser
  confundidos com buracos pelo modelo de visão.
- Lombadas e ressaltos não geram evento no sensor de distância (apenas profundidades
  positivas contam), mas vibração forte do veículo pode gerar leituras ruidosas.
- Por isso, nenhuma detecção automática isolada deve ser tratada como confirmação. O
  sistema faz **triagem**; a confirmação é da vistoria.

## 7. Registro e retroalimentação
Cada vistoria deve registrar se a detecção foi confirmada. Esses registros permitem, no
futuro, ajustar os pesos da fórmula de prioridade e o limiar de confiança do modelo de
visão com dados reais.
