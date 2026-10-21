# Painel de Geração Distribuída (ANEEL)

Painel em Streamlit com os dados de micro e minigeração distribuída do Brasil.

## Regras de trabalho

- O usuário está aprendendo Git e Python. Explique cada comando antes de rodá-lo.
- Faça commits pequenos, com mensagens claras em português.
- Nunca coloque no repositório dados brutos, senhas, tokens ou chaves de API.
- Ao criar ou alterar um arquivo de código, explique em linguagem simples o que
  cada parte principal faz.

## Fonte dos dados

- Conjunto: "Relação de empreendimentos de Mini e Micro Geração Distribuída",
  do portal de dados abertos da ANEEL (https://dadosabertos.aneel.gov.br).
- Licença: ODbL (Open Database License). Citar a fonte no painel.

### Aviso sobre a qualidade dos dados

A atualização da base foi suspensa entre 23/09/2025 e 13/11/2025, durante a
migração do sistema SISGD para o sistema MMGD. Os meses posteriores à migração
podem estar subestimados (registros ainda não carregados). O painel deve exibir
esse aviso.

### Observações sobre as colunas

- A base não tem coluna com a data de conexão. Usamos `DthAtualizaCadastralEmpreend`
  (data da última atualização cadastral) como aproximação do mês de conexão.
- Datas de 01/01/1900 são valores coringa e ficam fora do resumo mensal.
- Linhas com `MdaPotenciaInstaladaKW` <= 0 são descartadas de todos os resumos.
- `CodSubGrupoTarifario` e `SigModalidadeEmpreendimento` estão sempre vazias
  (deixaram de existir no sistema MMGD).
- `NumCPFCNPJ` e `NomTitularEmpreendimento` identificam titulares: nunca levar
  para `dados/processados/`.

## Arquitetura

```
dados brutos (dados/brutos/, fora do Git)
   → processamento com DuckDB
   → resumos pequenos (dados/processados/, versionados no Git)
   → app Streamlit
```

- `baixar_dados.py`: baixa o parquet da ANEEL para `dados/brutos/` e grava
  `dados/processados/metadados.json`.
- `processar_dados.py`: gera os resumos CSV em `dados/processados/`.
- `conferir_dados.py`: usa o recálculo do `checar_dados.py` para gerar uma
  planilha Excel de conferência em `dados/brutos/` (fora do Git). Só roda
  localmente. Usa o padrão visual
  Norven de `ferramentas_locais/`, que também fica fora do Git por conter o
  logo da empresa.
- `app.py`: painel Streamlit; lê só `dados/processados/` (principalmente o
  `cubo.csv`). Filtros na barra lateral e por clique nos gráficos.

### Regras do painel

- Nada de conclusões fixas no texto. Cada destaque é uma regra que olha o
  recorte filtrado e decide o que dizer (ex.: "domina" / "é maioria" /
  "lidera"), ou não aparece quando o dado não sustenta.
- Limiares de análise ficam como constantes nomeadas no topo do `app.py`,
  com comentário explicando o critério. Fatos externos (datas da suspensão,
  prazo da Lei 14.300) também ficam lá, separados.
- Meses incompletos são detectados pelos dados, não por número fixo de meses.
- `checar_dados.py`: recalcula os totais direto do bruto e termina com erro se
  os resumos não baterem. É a trava que impede publicar dados errados.
- O GitHub Actions (`.github/workflows/atualizar-dados.yml`) roda toda segunda:
  baixar → processar → checar → commit dos resumos, só se mudaram. Por isso os
  scripts do pipeline devem:
  - usar caminhos relativos à pasta do projeto (a partir de `__file__`), nunca
    caminhos absolutos da máquina;
  - rodar do início ao fim sem nenhuma interação (sem `input()`, sem perguntas);
  - terminar com erro (código de saída diferente de zero) quando algo falhar.

## Ambiente

- Dependências em `requirements.txt`, instaladas em um ambiente virtual `.venv`
  (que não vai para o Git).
