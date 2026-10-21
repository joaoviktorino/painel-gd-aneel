"""Gera resumos pequenos da base de GD da ANEEL usando DuckDB.

Lê o parquet bruto de dados/brutos/ e grava em dados/processados/:
  - por_estado.csv   quantidade e potência por estado (UF)
  - por_fonte.csv    quantidade e potência por fonte de geração
  - por_mes.csv      quantidade e potência por mês de conexão
  - processamento.json  data de referência e linhas descartadas

Uso:  python processar_dados.py   (rode antes o baixar_dados.py)
"""

import json
import sys
from pathlib import Path

import duckdb

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_PARQUET = (
    PASTA_PROJETO / "dados" / "brutos" / "empreendimento-geracao-distribuida.parquet"
)
PASTA_PROCESSADOS = PASTA_PROJETO / "dados" / "processados"

# Colunas que identificam o titular. Nunca podem aparecer nos resumos, que vão
# para o GitHub.
COLUNAS_PROIBIDAS = {"numcpfcnpj", "nomtitularempreendimento", "codcep"}

# Datas anteriores a esta são valores "coringa" (ex.: 01/01/1900), não datas reais.
DATA_MINIMA_VALIDA = "2000-01-01"

# A base não tem a data de conexão. A data da última atualização cadastral é a
# melhor aproximação disponível e segue a curva de crescimento das conexões.
SQL_BASE_VALIDA = """
    CREATE TABLE valida AS
    SELECT
        SigUF                                         AS uf,
        NomRegiao                                     AS regiao,
        coalesce(DscFonteGeracao, 'Não informada')    AS fonte,
        MdaPotenciaInstaladaKW                        AS potencia_kw,
        DthAtualizaCadastralEmpreend                  AS data_conexao
    FROM bruta
    WHERE MdaPotenciaInstaladaKW > 0
"""

SQL_POR_ESTADO = """
    SELECT
        uf,
        any_value(regiao)            AS regiao,
        count(*)                     AS quantidade,
        round(sum(potencia_kw), 2)   AS potencia_kw
    FROM valida
    GROUP BY uf
    ORDER BY potencia_kw DESC
"""

SQL_POR_FONTE = """
    SELECT
        fonte,
        count(*)                     AS quantidade,
        round(sum(potencia_kw), 2)   AS potencia_kw
    FROM valida
    GROUP BY fonte
    ORDER BY potencia_kw DESC
"""

SQL_POR_MES = f"""
    SELECT
        CAST(date_trunc('month', data_conexao) AS DATE)  AS mes,
        count(*)                                          AS quantidade,
        round(sum(potencia_kw), 2)                        AS potencia_kw
    FROM valida
    WHERE data_conexao >= DATE '{DATA_MINIMA_VALIDA}'
    GROUP BY mes
    ORDER BY mes
"""


def salvar_csv(con, sql, nome_arquivo):
    """Roda uma consulta e grava o resultado como CSV em dados/processados/."""
    colunas = {linha[0].lower() for linha in con.execute(f"DESCRIBE {sql}").fetchall()}
    if colunas & COLUNAS_PROIBIDAS:
        raise ValueError(
            f"{nome_arquivo} teria dados pessoais ({', '.join(colunas & COLUNAS_PROIBIDAS)}). "
            "Esses campos não podem ir para dados/processados/."
        )
    destino = (PASTA_PROCESSADOS / nome_arquivo).as_posix()
    con.execute(f"COPY ({sql}) TO '{destino}' (HEADER, DELIMITER ',')")
    linhas = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
    print(f"{nome_arquivo}: {linhas} linhas")


def contar(con, sql):
    return con.execute(sql).fetchone()[0]


def main():
    if not ARQUIVO_PARQUET.exists():
        raise FileNotFoundError(
            f"{ARQUIVO_PARQUET.relative_to(PASTA_PROJETO)} não existe. "
            "Rode antes: python baixar_dados.py"
        )
    PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)

    # Um banco DuckDB em memória: nada é gravado em disco além dos resumos.
    con = duckdb.connect()
    con.execute(
        f"CREATE VIEW bruta AS SELECT * FROM read_parquet('{ARQUIVO_PARQUET.as_posix()}')"
    )
    con.execute(SQL_BASE_VALIDA)

    salvar_csv(con, SQL_POR_ESTADO, "por_estado.csv")
    salvar_csv(con, SQL_POR_FONTE, "por_fonte.csv")
    salvar_csv(con, SQL_POR_MES, "por_mes.csv")

    # Informações para o app e para a conferência.
    periodo, data_geracao = con.execute(
        "SELECT any_value(AnmPeriodoReferencia), max(DatGeracaoConjuntoDados) FROM bruta"
    ).fetchone()
    processamento = {
        "periodo_referencia": periodo,
        "data_geracao_conjunto": data_geracao.isoformat(),
        "data_conexao_mais_recente": contar(
            con, "SELECT max(data_conexao) FROM valida"
        ).isoformat(),
        "linhas_lidas": contar(con, "SELECT count(*) FROM bruta"),
        "linhas_validas": contar(con, "SELECT count(*) FROM valida"),
        "descartes": [
            {
                "motivo": "Potência instalada nula, zero ou negativa",
                "afeta": "todos os resumos",
                "linhas": contar(
                    con,
                    "SELECT count(*) FROM bruta "
                    "WHERE MdaPotenciaInstaladaKW IS NULL OR MdaPotenciaInstaladaKW <= 0",
                ),
            },
            {
                "motivo": f"Data de conexão anterior a {DATA_MINIMA_VALIDA} (valor coringa)",
                "afeta": "somente por_mes.csv",
                "linhas": contar(
                    con,
                    "SELECT count(*) FROM valida "
                    f"WHERE data_conexao IS NULL OR data_conexao < DATE '{DATA_MINIMA_VALIDA}'",
                ),
            },
        ],
    }
    with open(PASTA_PROCESSADOS / "processamento.json", "w", encoding="utf-8") as arquivo:
        json.dump(processamento, arquivo, ensure_ascii=False, indent=2)
    print("processamento.json salvo")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)
