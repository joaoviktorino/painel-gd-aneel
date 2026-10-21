"""Confere se os resumos de dados/processados/ batem com a base bruta.

Recalcula os totais direto do parquet, sem usar o processar_dados.py, e compara
com os CSVs. Se algo não bater, termina com erro (código 1): no GitHub Actions
isso impede que resumos errados sejam publicados.

Uso:  python checar_dados.py   (rode antes o processar_dados.py)
"""

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_BRUTOS = PASTA_PROJETO / "dados" / "brutos"
PASTA_PROCESSADOS = PASTA_PROJETO / "dados" / "processados"
ARQUIVO_PARQUET = PASTA_BRUTOS / "empreendimento-geracao-distribuida.parquet"

# Os CSVs guardam a potência com 2 casas decimais; aceitamos essa diferença.
TOLERANCIA_KW = 0.01


def abrir_bruta():
    """Abre o parquet no DuckDB com o nome 'bruta'."""
    if not ARQUIVO_PARQUET.exists():
        raise FileNotFoundError(
            f"{ARQUIVO_PARQUET.relative_to(PASTA_PROJETO)} não existe. Rode antes: python baixar_dados.py"
        )
    con = duckdb.connect()
    con.execute(f"CREATE VIEW bruta AS SELECT * FROM read_parquet('{ARQUIVO_PARQUET.as_posix()}')")
    return con


def calcular(con):
    """Recalcula, a partir do parquet, os totais e as checagens de qualidade."""
    r = {}
    r["linhas_lidas"] = con.execute("SELECT count(*) FROM bruta").fetchall()[0][0]

    # Mesmas regras do processamento, escritas de novo de forma independente.
    filtro_descarte = "MdaPotenciaInstaladaKW IS NULL OR MdaPotenciaInstaladaKW <= 0"
    r["descartes"] = con.sql(f"""
        SELECT SigUF AS uf, SigAgente AS distribuidora, CodEmpreendimento AS codigo,
               DscFonteGeracao AS fonte, MdaPotenciaInstaladaKW AS potencia_kw,
               DthAtualizaCadastralEmpreend AS data
        FROM bruta WHERE {filtro_descarte} ORDER BY uf, codigo
    """).df()
    r["data_coringa"] = con.execute(f"""
        SELECT count(*) FROM bruta
        WHERE NOT ({filtro_descarte}) AND DthAtualizaCadastralEmpreend < DATE '2000-01-01'
    """).fetchall()[0][0]
    r["fonte_vazia"] = con.execute(
        "SELECT count(*) FROM bruta WHERE DscFonteGeracao IS NULL"
    ).fetchall()[0][0]

    r["por_estado"] = con.sql(f"""
        SELECT SigUF AS uf, any_value(NomRegiao) AS regiao,
               count(*) AS lidas,
               count(*) FILTER (WHERE {filtro_descarte}) AS descartadas,
               sum(MdaPotenciaInstaladaKW) FILTER (WHERE NOT ({filtro_descarte})) AS potencia_kw
        FROM bruta GROUP BY uf ORDER BY uf
    """).df()
    r["por_fonte"] = con.sql(f"""
        SELECT coalesce(DscFonteGeracao, 'Não informada') AS fonte,
               count(*) AS lidas,
               count(*) FILTER (WHERE {filtro_descarte}) AS descartadas,
               coalesce(sum(MdaPotenciaInstaladaKW) FILTER (WHERE NOT ({filtro_descarte})), 0) AS potencia_kw
        FROM bruta GROUP BY fonte ORDER BY fonte
    """).df()

    # Códigos repetidos: exatamente iguais e também ignorando espaços e maiúsculas.
    r["repetidos"] = con.sql("""
        SELECT CodEmpreendimento AS codigo, count(*) AS ocorrencias
        FROM bruta WHERE CodEmpreendimento IS NOT NULL
        GROUP BY codigo HAVING count(*) > 1 ORDER BY ocorrencias DESC, codigo
    """).df()
    r["repetidos_normalizados"] = con.execute("""
        SELECT count(*) FROM (
            SELECT upper(trim(CodEmpreendimento)) FROM bruta
            WHERE CodEmpreendimento IS NOT NULL GROUP BY 1 HAVING count(*) > 1)
    """).fetchall()[0][0]
    r["codigo_vazio"] = con.execute(
        "SELECT count(*) FROM bruta WHERE CodEmpreendimento IS NULL"
    ).fetchall()[0][0]

    periodo, data_geracao = con.execute(
        "SELECT any_value(AnmPeriodoReferencia), max(DatGeracaoConjuntoDados) FROM bruta"
    ).fetchall()[0]
    r["periodo"], r["data_geracao"] = periodo, data_geracao
    return r


def comparar(bruto, resumo, chave, nome):
    """Compara um resumo (CSV) com o recálculo. Devolve a lista de problemas."""
    bruto = bruto.assign(validas=bruto["lidas"] - bruto["descartadas"]).set_index(chave)
    resumo = resumo.set_index(chave)
    problemas = []
    for item in sorted(set(bruto.index) ^ set(resumo.index)):
        onde = "só na base bruta" if item in bruto.index else "só no resumo"
        problemas.append(f"{nome}: '{item}' aparece {onde}")
    for item in sorted(set(bruto.index) & set(resumo.index)):
        if bruto.loc[item, "validas"] != resumo.loc[item, "quantidade"]:
            problemas.append(
                f"{nome} '{item}': {bruto.loc[item, 'validas']} usinas na base, "
                f"{resumo.loc[item, 'quantidade']} no resumo"
            )
        diferenca_kw = abs(bruto.loc[item, "potencia_kw"] - resumo.loc[item, "potencia_kw"])
        if diferenca_kw > TOLERANCIA_KW:
            problemas.append(f"{nome} '{item}': potência difere em {diferenca_kw:.2f} kW")
    return problemas


def checar(r):
    """Roda todas as comparações. Devolve a lista de problemas (vazia = tudo certo)."""
    problemas = []
    problemas += comparar(r["por_estado"], pd.read_csv(PASTA_PROCESSADOS / "por_estado.csv"), "uf", "Estado")
    problemas += comparar(r["por_fonte"], pd.read_csv(PASTA_PROCESSADOS / "por_fonte.csv"), "fonte", "Fonte")

    with open(PASTA_PROCESSADOS / "processamento.json", encoding="utf-8") as arquivo:
        processamento = json.load(arquivo)
    if processamento["linhas_lidas"] != r["linhas_lidas"]:
        problemas.append(
            f"processamento.json diz {processamento['linhas_lidas']} linhas lidas; a base tem {r['linhas_lidas']}"
        )

    por_mes = pd.read_csv(PASTA_PROCESSADOS / "por_mes.csv")
    esperado_mes = r["por_estado"]["lidas"].sum() - len(r["descartes"]) - r["data_coringa"]
    if por_mes["quantidade"].sum() != esperado_mes:
        problemas.append(
            f"por_mes.csv soma {por_mes['quantidade'].sum()} usinas; o esperado era {esperado_mes}"
        )
    return problemas


def main():
    r = calcular(abrir_bruta())
    problemas = checar(r)

    print(f"Linhas lidas: {r['linhas_lidas']}")
    print(f"Descartadas (potência zero, negativa ou vazia): {len(r['descartes'])}")
    print(f"Fora só do gráfico mensal (data coringa): {r['data_coringa']}")
    # Códigos repetidos são um problema da base da ANEEL, não do nosso
    # processamento: avisamos, mas não bloqueamos a publicação.
    if len(r["repetidos"]) or r["repetidos_normalizados"]:
        print(f"Aviso: {len(r['repetidos'])} códigos de empreendimento repetidos "
              f"({r['repetidos_normalizados']} ignorando espaços e maiúsculas)")
    else:
        print("Códigos de empreendimento repetidos: nenhum")

    if problemas:
        print(f"\n{len(problemas)} problema(s) encontrados:", file=sys.stderr)
        for problema in problemas:
            print(f"  - {problema}", file=sys.stderr)
        sys.exit(1)
    print("Conferência OK: os resumos batem com a base bruta.")


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)
