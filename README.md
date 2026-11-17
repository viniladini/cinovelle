# cinovelle.

**Your next favorite story.** Projeto acadêmico de POO com banco de dados, em Python, Flask e SQLite3. Entrega registrada: **17/11/2026**.

Descubra filmes e séries a partir de uma seleção de até cinco referências. O Cinovelle mantém perfis locais, favoritos, watchlist e histórico; funciona offline com 18 obras fictícias ou com o catálogo real do TMDB. Interface PT/EN, responsiva, em grafite/vinho, com símbolo SVG próprio Cinovelle Match.

## Executar

Requisitos: Python **3.11+**. Ambiente validado: Python 3.13.7. Node não é necessário para usar a aplicação.

No PowerShell, na pasta extraída:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Apenas na primeira instalação; preserve um .env já configurado.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe run.py
```

Abra **http://127.0.0.1:5000**. O banco `instance/cinovelle.sqlite3` é criado automaticamente. `Ctrl+C` encerra o servidor. O menu web **Perfis → Entrar / Sair** controla o perfil, sem encerrar o Flask. Não há menu CLI de opções nem autenticação por senha: perfis locais não são contas protegidas.

`requirements-lock.txt` registra versões Python fixadas. Para reproduzi-las, instale esse arquivo em vez de `requirements.txt`. Flask/Jinja2, requests e python-dotenv são as dependências principais; pytest é usado nos testes. Não há ORM, modelo de IA pago ou framework frontend.

## Configurar APIs

Use `.env.example` como referência. Não distribua `.env` ou credenciais.

- `SECRET_KEY`: chave longa e estável. Gere com `py -c "import secrets; print(secrets.token_hex(32))"`. Sem ela, sessões expiram ao reiniciar; dados SQLite permanecem.
- `TMDB_API_KEY` **ou** `TMDB_READ_ACCESS_TOKEN`: catálogo real. O token Bearer tem precedência quando ambos existem.
- `OMDB_API_KEY`: opcional, para notas IMDb reais via OMDb.
- `DEMO_MODE=true`: força o catálogo fictício, mesmo com credenciais. Sem credenciais TMDB, o demo é automático.

Reinicie o servidor após configurar. Credenciais inválidas geram mensagens de erro; o sistema não troca silenciosamente títulos reais por fictícios. Cache, timeout e tratamento de respostas inválidas ficam nos clientes HTTP. Nunca são inventadas notas ou disponibilidades.

## Usar e demonstrar

1. Crie um perfil em **Perfis**. Em **Meu gosto**, edite nome e preferências opcionais de gênero.
2. Pesquise na navbar. As sugestões aparecem após 300 ms; use mouse/toque, Tab, ↑/↓, Enter e Esc. Selecione de um a cinco títulos e remova pelo `×`.
3. Clique em **Encontrar meus matches**. Filtros por tipo, gênero e preferências são explícitos. **Escolhidos para você** reúne todos os candidatos relevantes em ordem decrescente de score, inclusive abaixo de 70. **Por que este match?** explica as conexões observadas.
4. Coração salva **Favoritos**: histórias de que você gosta. **Quero assistir / Na minha lista** controla a watchlist: histórias que pretende assistir. São coleções independentes da seleção temporária de referências.
5. **Minha lista** permite remover títulos, abrir detalhes e encontrar similares. Favoritos, watchlist e histórico são isolados por perfil e persistem após reiniciar.
6. Em **Meu gosto**, consulte/exclua execuções do histórico. Em **Perfis**, entre ou exclua um perfil. Ao trocar de perfil ou sair, a seleção temporária é limpa.

Roteiro offline conferido: selecione **A casa de papel azul**, filtre **Séries** e gere matches. Adicione **A floresta dos relógios** para demonstrar seleção múltipla; **A ilha que sonhava** é um resultado do catálogo demo. Mostre favoritos, watchlist, atualização de perfil e exclusão de histórico para demonstrar CRUD. As obras, datas, durações e pôsteres do demo são fictícios; não há notas externas atribuídas a elas.

O banner da home alterna até seis títulos disponíveis a cada seis segundos, com controles, indicadores e pausa por interação, aba oculta e navegação. Redução de movimento desativa autoplay; a navegação manual continua funcionando. As imagens seguintes são carregadas progressivamente.

## Avaliações e Onde assistir

**TMDB** e **IMDb via OMDb** são avaliações distintas, nunca intercambiáveis. Detalhes usam o IMDb ID do TMDB, consultando IDs externos quando necessário. OMDb tem cache em memória de 24 horas. Cards só exibem IMDb se já houver nota válida em cache; não fazem uma requisição OMDb por card. Sem chave ou nota válida, somente TMDB é mostrado. O cache IMDb é perdido ao reiniciar, sem afetar suas coleções.

**Onde assistir** consulta a região **BR** dos endpoints oficiais `/movie/{id}/watch/providers` e `/tv/{id}/watch/providers`. Agrupa assinatura, gratuito, anúncios, aluguel e compra quando informados. Logotipos e nomes vêm da resposta. O botão de opções usa exclusivamente o link oficial retornado pelo TMDB. Não são gerados preços ou links diretos de serviços.

A seção possui loading, erro, nova tentativa e estado sem disponibilidade no Brasil. As respostas TMDB são armazenadas em cache por 30 minutos. **Dados de disponibilidade: JustWatch, fornecidos via TMDB.** A atribuição aparece na própria interface. Referências: [filmes](https://developer.themoviedb.org/reference/movie-watch-providers), [séries](https://developer.themoviedb.org/reference/tv-series-watch-providers), [OMDb](https://www.omdbapi.com/).

## Cinovelle Match — perfil combinado

O cálculo é local, determinístico e auditável. Uma nota de qualidade do filme não determina sua compatibilidade: TMDB/IMDb não entram no score ativo.

- Metadados fornecem gêneros, palavras-chave/IDs, sinopses e relações diretas/similares. Um vocabulário reutilizável PT/EN reconhece temas como família, tensão psicológica, identidade, investigação, sobrevivência, crítica social, sobrenatural e exploração espacial **somente quando sustentados pelo texto**.
- Termos de sinopses são separados por idioma; temas canônicos permitem conexão PT/EN. TF-IDF, cosseno, cobertura e normalização lexical são leves, sem serviços externos de IA.
- Perfis agrupam características recorrentes e complementares. Cada candidato é comparado com os grupos, com referências individuais e, quando conecta múltiplas referências, com o perfil consolidado. A combinação pondera evidência observada; não adiciona um bônus fixo por selecionar mais filmes.
- Interesses distintos podem produzir bons resultados para um subgrupo, sem exigir a interseção de todos os gêneros. Gêneros combinam o perfil consolidado e a melhor afinidade individual. Os desempates consideram cobertura de referências e grupos, mantendo os percentuais em ordem decrescente.
- Pesos de conteúdo de base: temas **35**, relações **35**, gêneros **20**, sinopse até **8**, normalizados conforme disponibilidade. Relação de recomendação direta tem sinal 1; similar amplo, 0,5. Suficiência temática e qualidade dos dados limitam confiança; ausência de metadados não é incompatibilidade comprovada. Não há mínimo obrigatório, escala que force o melhor a 80 ou percentuais aleatórios.
- Referências e duplicatas são excluídas. Apenas candidatos com evidência de relevância aparecem. Há estado vazio com ação para alterar a seleção; a grade não é completada com títulos populares aleatórios.

O catálogo reúne relações de cada referência e descoberta por gêneros/pares de palavras-chave. A prioridade inclui resumos temáticos e conexões com múltiplas referências. Limites: 400 resumos, até 22 consultas de recuperação, 32 candidatos enriquecidos inicialmente e até 64 na única expansão controlada, quando necessária. Cache de candidatos: cinco minutos; detalhes/respostas TMDB: 30 minutos. Consultas frias podem demorar e falhas parciais podem reduzir resultados.

`RecommendationEngine` orquestra o catálogo; `MatchScorer` calcula fatores e contribuições. Os modos anteriores são mantidos para compatibilidade de testes/cálculos históricos. **Score heurístico não é probabilidade de gostar.** Textos incompletos, rótulos genéricos e diferenças de idioma limitam a análise; não há compreensão semântica por um grande modelo.

Para avaliar os cenários **Corra! + Coraline + Parasita**, **Interestelar + A Chegada** e gostos distintos, com dados reais e banco temporário:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_match.py
```

O script grava somente a avaliação atual em `artifacts/product-evaluation.json` e `.md`, com cinco resultados e justificativas por cenário, além da verificação de disponibilidade BR. Esses arquivos são locais, ignorados pelo Git e excluídos do pacote. IDs dos cenários são fixtures de avaliação, não regras do motor. O script audita “Nós” sem forçar sua inclusão na recuperação.

## POO, SQLite3 e organização

| Módulo | Responsabilidade |
|---|---|
| `models/` | MediaItem, Movie/TVSeries com `duration()` polimórfico, Genre imutável, Profile com validação e preferências encapsuladas, Recommendation |
| `repositories/` | SQL parametrizado, persistência, transações, consultas e cascatas |
| `services/` | CatalogService, MatchScorer, vocabulário temático e RecommendationEngine |
| `integrations/` | TMDBClient e OMDbClient especializam JSONClient com cache e erros controlados |
| `routes/`, `templates/`, `static/` | Flask, formulários, Jinja2, CSS e JavaScript vanilla |
| `scripts/`, `tests/` | Execução de avaliações, empacotamento, verificação e regressões |

Movie/TVSeries demonstram herança e polimorfismo; Profile encapsula regras e retorna cópias das preferências. Serviços colaboram por composição; títulos contêm Genre. O CRUD completo de perfis tem criar, consultar, atualizar nome/preferências e excluir pela interface. Coleções e histórico têm as operações correspondentes de inclusão, leitura e remoção.

Bancos novos têm **oito tabelas**: `profiles`, `titles`, `genres`, `title_genres`, `favorites`, `watchlist`, `recommendation_runs`, `recommendation_results`. Há PKs, FKs, UNIQUE, relação N:N, `PRAGMA foreign_keys=ON`, commit e rollback. Watchlist tem ID, perfil, título e data, com UNIQUE(perfil,título). A inicialização é não destrutiva: adiciona sua tabela e índice aos bancos existentes. Tabelas legadas sem uso não são apagadas. Excluir perfil remove suas coleções e execuções em cascata.

Metadados variáveis usam JSON no título; relações principais mantêm FKs reais. Dados locais não são contas protegidas e a aplicação deve permanecer na máquina de demonstração. O servidor Flask embutido não é uma implantação pública de produção.

## Testes e pacote

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
# Somente para testes de interface (Node 26 recomendado):
npm ci --ignore-scripts
npm test
.\.venv\Scripts\python.exe scripts\package.py
.\.venv\Scripts\python.exe scripts\verify_delivery.py
```

Os testes isolam bancos temporários e simulam APIs; incluem CRUD, migração aditiva, perfis, favoritos, watchlist, histórico, Match combinado, providers BR, OMDb/cache, busca, filtros, banner e navegação. JavaScript usa node:test e jsdom de desenvolvimento (Node 22.22.2, 24.15 ou 26+ compatíveis). Não é necessário Node para executar o Flask. Testes HTTP/DOM não substituem inspeção visual em dispositivos físicos.

O ZIP `cinovelle-projeto-poo.zip` contém a pasta `cinovelle/`, fontes, templates/assets, testes, README e manifestos/locks Python e Node. Exclui `.env`, bancos pessoais, ambientes, node_modules, caches, auditorias, documentos redundantes e Git. O verificador confere integridade, fontes atuais, credenciais locais e fluxo demo/CRUD extraído, reutilizando as dependências instaladas. Regere o ZIP após qualquer alteração. Não há publicação automática no GitHub; acrescente nome/turma e entregue conforme o enunciado da professora.

## Créditos e limites

- [TMDB](https://www.themoviedb.org/): dados e imagens quando configurado. **This product uses the TMDB API but is not endorsed or certified by TMDB.** Logo oficial local preservado.
- [JustWatch](https://www.justwatch.com/): origem obrigatoriamente atribuída dos dados de disponibilidade fornecidos pelo TMDB.
- [OMDb](https://www.omdbapi.com/): nota IMDb opcional via API; sem scraping. Observe os termos e a licença [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
- Inter via Google Fonts é opcional; fontes do sistema são o fallback offline. Obras e ilustrações SVG do demo são autorais e fictícias.

APIs, imagens, traduções e disponibilidade podem mudar. O catálogo real não fica integralmente offline; detalhes já persistidos têm fallback SQLite em falha de rede. Mutações são serializadas dentro da aba, mas não há sincronização em tempo real entre abas. A ausência de chave OMDb impede validação IMDb real; o restante segue funcionando. Homologação visual desktop/mobile e uma instalação limpa em outra máquina são etapas manuais recomendadas antes da apresentação.