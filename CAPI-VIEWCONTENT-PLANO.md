# Proposta isolada — ViewContent Pixel + Meta Conversions API (7 Hábitos)

**STATUS: SOMENTE PROPOSTA / SEM DEPLOY / SEM TOKEN / SEM CUSTO NOVO.**

Objetivo: melhorar a cobertura do evento **ViewContent** gerado pela landing do
**7 Hábitos para uma Vida com Mais Presença**, sem alterar o **Lead** da lista
de espera do Desafio 21 Dias, os eventos da Hotmart ou os anúncios existentes.

## Evidência anterior

No Gerenciador de Eventos, dataset \`1780688656320725\`:
- amostras de **Pixel da Meta** no domínio \`7habitos.robertabitencourt.com.br\`;
- amostras de **CAPI direta** com URL \`api-super-pixel.hotmart.com\`;
- alerta de cobertura para ViewContent: o número de eventos do navegador não
  acompanha o número enviado por API no período analisado.
Esses **podem ser eventos distintos**. Não se deduplicam por coincidência de
tipo de evento ou hora; os dois canais precisam representar a **mesma**
visualização e compartilhar \`event_id\`.

## Arquitetura preparada (ainda sem funcionamento externo)

\`index.html\`
: Mantém a aparência, o checkout, o Pixel existente e o consentimento. Após
  consentimento autorizado, chama \`meta-capi-bridge.js\` para **ViewContent**.
  Mantém PageView no navegador. Não toca em Purchase ou Lead.

\`meta-capi-bridge.js\`
: Gera um \`rbvc-<32 hex>\` por visualização, faz
  \`fbq('track','ViewContent',payload,{eventID:id})\` e, **somente quando o relay
  futuro estiver configurado**, solicita um comprovante temporário e replica
  o **mesmo** \`ViewContent\` ao servidor. Se o relay falhar ou não existir,
  o Pixel continua funcionando. Sem autorização do usuário, não registra
  evento nem faz chamadas. Não manda nome, telefone, e-mail ou dados de saúde.

\`capi-relay/app.py\`
: Serviço WSGI separado, sem serviços pagos criados nesta etapa.
  - \`GET /health\` somente status.
  - \`GET /v1/view-token?event_id=...\` cria assinatura HMAC com validade de 120s.
  - \`POST /v1/view-content\` verifica assinatura, consentimento, origem exata,
    formato de evento, limitação de requisições e repetição por ID.
  - Envia à Meta via HTTPS **somente** \`ViewContent\`, \`action_source=website\`,
    URL fixa da landing, \`event_id\` compartilhado e dados mínimos de
    correspondência (user-agent e \`_fbp\` opcional, após consentimento).
  - Token Meta e segredo HMAC permanecem apenas em variáveis do servidor.
  - IP do visitante não é encaminhado por padrão.
  - Não inclui dados de compra ou descrições de saúde/bem-estar.
  - Proteções de origem e limitação simples de taxa não substituem WAF ou
    autenticação completa; o endpoint público tem risco residual de abuso.

## Para testar localmente (sem Meta e sem credenciais reais)

\`\`\`sh
python -m py_compile capi-relay/app.py capi-relay/tests/test_app.py
python -m unittest discover -s capi-relay/tests -p 'test_*.py' -v
node --test tests/test-bridge.cjs
\`\`\`

Os testes cobrem:
- autorização de medição e revogação antes da requisição CAPI;
- igualdade exata de \`eventID\` do Pixel e \`event_id\` do servidor;
- preservação do ViewContent via Pixel quando o relay estiver indisponível;
- validação HMAC, expiração, origem, CORS e falhas de entrega;
- bloqueio de repetição local e ausência de encaminhamento de dados pessoais;
- ausência de envio real à Meta (backend mockado).

Existe uma workflow de GitHub Actions de testes offline no PR. Os testes
só provam comportamento simulado: **não validam recebimento real pela Meta**.

## Configuração FUTURA (não executar sem autorização)

O site atual é estático no Render. Ele não executa Python; portanto o relay
precisa de serviço web isolado, por exemplo um **novo Render Web Service**,
sujeito a preço e aprovação explícita. Não reutilizar ou alterar o PWA
\`meu-cuidado-roberta\`.

Sugestão de configuração do serviço separado:
- Fonte: este repositório, pasta raiz \`capi-relay\`.
- Ambiente: Python 3.13, instalação \`pip install -r requirements.txt\`.
- Inicialização: \`gunicorn app:application --bind 0.0.0.0:$PORT --workers 1 --threads 4\`.
- Auto deploy desativado na validação.
- Variáveis de ambiente no **Render**, nunca no GitHub ou HTML:

| Variável | Finalidade |
|---|---|
| \`META_CAPI_ACCESS_TOKEN\` | Token da CAPI fornecido pela Meta |
| \`META_GRAPH_VERSION\` | Versão atual e suportada da Graph API, no formato \`vX.Y\` |
| \`RB_CAPI_SIGNING_SECRET\` | Segredo aleatório exclusivo com 32+ caracteres |
| \`RB_CAPI_ALLOWED_ORIGIN\` | \`https://7habitos.robertabitencourt.com.br\` |
| \`META_CAPI_TEST_EVENT_CODE\` | Opcional, apenas para uma sessão de **Eventos de teste** |
| \`RB_CAPI_SEND_CLIENT_IP\` | Omitido por padrão (não enviar IP) |

Depois de um servidor implantado/testado, configurar na landing:
\`\`\`html
<script>window.RB_CAPI_RELAY_ORIGIN = "https://ENDERECO-DO-SERVIDOR-APROVADO";</script>
\`\`\`
Esse valor deve ser estabelecido **antes** de carregar
\`meta-capi-bridge.js\`. Nenhum endereço real de servidor foi configurado nesta
proposta, portanto a navegação atual ainda não chama CAPI de nossa landing.

## Critérios de liberação (pendentes)
- [ ] PR com testes offline passando e revisão do diff
- [ ] Revisão de categoria restrita de saúde/bem-estar e LGPD
- [ ] Aprovação explícita para qualquer serviço novo, custo e eventual token
- [ ] Inspecionar versão Graph API e política Meta em vigor na ocasião
- [ ] Teste isolado do relay, sem evento de produção (usar \`test_event_code\`)
- [ ] Comparar \`eventID\` e \`event_id\` nos dois canais para a mesma visualização
- [ ] Verificar taxa de deduplicação na Meta sem afetar eventos da Hotmart
- [ ] Somente então considerar merge e deploy de landing e backend
- [ ] Monitorar aviso de cobertura por até 7 dias; não há garantia de desaparecer
- [ ] Preservar campanha Meta existente e conta pré-paga sem alterações

## Pendências do Status Mestre não abrangidas
- Lead da lista de espera: validado e funcionando; **não tocar**.
- Purchase Hotmart: ainda precisa validação real.
- Vínculo do Pixel à conta de anúncios: continua pendente.
- Correspondência dos eventos: a classificação Meta pode remover campos;
  não tentar contornar restrições sensíveis.
