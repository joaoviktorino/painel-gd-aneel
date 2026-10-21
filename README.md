# Painel de geração distribuída no Brasil

Painel em Streamlit com os dados abertos da ANEEL sobre micro e minigeração
distribuída: usinas de até 5 MW instaladas em residências, comércios,
propriedades rurais e indústrias e conectadas à rede das distribuidoras.

O painel mostra:

- total de usinas, potência instalada e tamanho médio por usina;
- destaques calculados a partir dos números (participação da energia solar,
  concentração por estado, estados com usinas maiores, efeito da Lei 14.300);
- potência acumulada ao longo do tempo e participação por região;
- ranking por estado (potência, número de usinas ou tamanho médio);
- novas conexões por mês, com o período de suspensão da base destacado;
- fontes além da energia solar.

Os dados são atualizados automaticamente toda semana pelo GitHub Actions.

## Como funciona

```
ANEEL (parquet, ~100 MB)
  → baixar_dados.py      baixa para dados/brutos/ (fora do Git)
  → processar_dados.py   gera resumos pequenos com DuckDB em dados/processados/
  → checar_dados.py      recalcula tudo direto da base e bloqueia se não bater
  → app.py               painel Streamlit, lê só os resumos
```

| Arquivo | O que faz |
|---|---|
| `baixar_dados.py` | Baixa a base da ANEEL e grava `metadados.json` com a data do download e da última atualização do portal. |
| `processar_dados.py` | Gera `por_estado.csv`, `por_fonte.csv`, `por_mes.csv` e `processamento.json`. Recusa gravar CPF/CNPJ, nome do titular ou CEP. |
| `checar_dados.py` | Recalcula os totais de forma independente e termina com erro se os resumos não baterem. |
| `conferir_dados.py` | Gera uma planilha Excel de conferência (uso local, precisa de arquivos que não estão no repositório). |
| `app.py` | O painel. Cores e fontes em `.streamlit/config.toml`. |
| `.github/workflows/atualizar-dados.yml` | Roda baixar → processar → checar toda segunda e publica os resumos se a base mudou. |

## Como rodar no seu computador

Requer Python 3.13.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe baixar_dados.py
.venv\Scripts\python.exe processar_dados.py
.venv\Scripts\python.exe -m streamlit run app.py
```

Os comandos acima são para Windows. No Linux ou Mac, troque
`.venv\Scripts\python.exe` por `.venv/bin/python`. Os resumos já estão no
repositório, então para só abrir o painel bastam o primeiro, o segundo e o
último comando.

## Cuidados com os dados

- **Data de conexão:** a base não tem essa coluna. Usamos a data da última
  atualização cadastral de cada usina como aproximação.
- **Suspensão:** a ANEEL suspendeu a atualização da base entre 23/09/2025 e
  13/11/2025, durante a migração do sistema SISGD para o sistema MMGD. Os meses
  após a migração, e em especial os mais recentes, podem estar subestimados.
- **Descartes:** linhas com potência zero ou negativa ficam fora dos resumos;
  datas de 01/01/1900 (valor de preenchimento) ficam fora só do gráfico mensal.
  As quantidades estão em `dados/processados/processamento.json`.
- **Dados pessoais:** CPF/CNPJ, nome do titular e CEP nunca vão para o
  repositório. Os resumos só têm totais por estado, fonte e mês.

## Fonte e licença

Dados: [ANEEL – Relação de empreendimentos de Mini e Micro Geração Distribuída](https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2),
sob a licença [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/).

Código: licença MIT, ver [LICENSE](LICENSE).
