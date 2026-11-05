# Rastreamento de campanhas — 7 Hábitos (rascunho)

**Estado: proposta isolada; sem merge nem deploy.** Não altera Hotmart, Meta, checkout, preço ou consentimento.

## Por que isso é necessário

A Hotmart não recebe automaticamente UTMs que chegaram a uma landing externa.
Os parâmetros precisam estar presentes no **link do botão de checkout**.
Fonte: Central de Ajuda Hotmart,
https://suportehotmart.zendesk.com/hc/pt-br/articles/360002403031

## Alteração nesta branch

- \`checkout-attribution.js\`: lê apenas cinco UTMs de campanha da URL atual,
  sem cookies nem localStorage; valida caracteres e comprimentos.
- Acrescenta essas tags aos dois botões de compra do produto
  \`https://pay.hotmart.com/D108002435X\`.
- Acrescenta \`sck=r7-<origem>-<meio>\` (até 30 caracteres, sem underline) como código
  resumido de origem da venda do produtor, quando não existir SCK.
- Preserva parâmetros existentes do checkout (por exemplo, \`split=1\`, \`off\`,
  \`sck\` ou UTMs preexistentes). Não substitui nem altera a oferta.
- Se a visita não tiver UTMs, usa somente \`sck=r7-landing\`, sem inventar
  uma origem como Facebook ou Instagram.
- Não propaga \`fbclid\`, e-mails, nomes, telefones ou parâmetros de formulário.

## Exemplos de links de destino nos anúncios e publicações

**Anúncio pago para 7 Hábitos (vídeo 01):**
\`https://7habitos.robertabitencourt.com.br/?utm_source=instagram&utm_medium=paid_social&utm_campaign=rb7-vendas&utm_content=video01\`

**Instagram orgânico para 7 Hábitos:**
\`https://7habitos.robertabitencourt.com.br/?utm_source=instagram&utm_medium=organic&utm_campaign=stories-7habitos\`

**Perfil e página de links:**
\`https://links.robertabitencourt.com.br/?utm_source=instagram&utm_medium=organic&utm_campaign=bio-roberta\`

## Como testar depois da publicação, sem comprar

1. Abrir em janela anônima o link de anúncio com UTM acima.
2. Na landing, clicar num botão de compra.
3. Confirmar que o checkout mantém o código \`D108002435X\`, preço e condições.
4. Confirmar que a URL possui \`utm_source=instagram\`,
   \`utm_medium=paid_social\`, \`utm_campaign=rb7-vendas\`,
   \`utm_content=video01\`, e \`sck=r7-instagram-paid-social\`.
5. Repetir com a página sem UTMs e conferir \`sck=r7-landing\`.
6. Repetir com o link da bio para validar links.roberta → landing → checkout.
7. Não concluir compra: o evento \`Purchase\` exige transação aprovada.
8. Após vendas reais, consultar Hotmart:
   **Vendas → Gestão de vendas → Dashboard de Origem de Vendas**,
   abas **UTM** e **SCK**.

**Os testes automatizados não comprovam relatório de vendas.**
O Pixel e a CAPI existentes não são alterados por este PR.
