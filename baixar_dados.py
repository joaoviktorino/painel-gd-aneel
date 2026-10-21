"""Baixa a base de Micro e Minigeração Distribuída da ANEEL.

Salva o parquet em dados/brutos/ e grava dados/processados/metadados.json com a
data do download e a data da última atualização informada pelo portal (CKAN).

Uso:  python baixar_dados.py
"""

import json
import shutil
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

# Caminhos relativos à pasta onde este arquivo está, para funcionar em qualquer
# máquina (inclusive no GitHub Actions).
PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_BRUTOS = PASTA_PROJETO / "dados" / "brutos"
PASTA_PROCESSADOS = PASTA_PROJETO / "dados" / "processados"
ARQUIVO_PARQUET = PASTA_BRUTOS / "empreendimento-geracao-distribuida.parquet"
ARQUIVO_METADADOS = PASTA_PROCESSADOS / "metadados.json"

ID_RECURSO = "cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27"
URL_DOWNLOAD = (
    "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2"
    f"/resource/{ID_RECURSO}/download/empreendimento-geracao-distribuida.parquet"
)
URL_API_CKAN = (
    f"https://dadosabertos.aneel.gov.br/api/3/action/resource_show?id={ID_RECURSO}"
)

# Alguns servidores recusam pedidos sem identificação do programa.
CABECALHOS = {"User-Agent": "painel-gd-aneel (script de download)"}
TEMPO_LIMITE_SEGUNDOS = 300


def consultar_ckan():
    """Pergunta ao portal quando o arquivo foi atualizado pela última vez.

    Se a API falhar, devolve um dicionário vazio: o download continua mesmo assim.
    """
    try:
        pedido = urllib.request.Request(URL_API_CKAN, headers=CABECALHOS)
        with urllib.request.urlopen(pedido, timeout=60) as resposta:
            dados = json.load(resposta)
        return dados["result"]
    except Exception as erro:
        print(f"Aviso: não foi possível consultar a API CKAN ({erro}).")
        return {}


def baixar_arquivo():
    """Baixa o parquet em pedaços, sem carregar o arquivo inteiro na memória.

    Grava primeiro num arquivo temporário (.parcial) e só renomeia no fim, para
    nunca deixar um parquet pela metade se o download for interrompido.
    """
    PASTA_BRUTOS.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_PARQUET.with_suffix(".parquet.parcial")

    print(f"Baixando {URL_DOWNLOAD}")
    pedido = urllib.request.Request(URL_DOWNLOAD, headers=CABECALHOS)
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_SEGUNDOS) as resposta:
        with open(temporario, "wb") as destino:
            shutil.copyfileobj(resposta, destino, length=1024 * 1024)

    temporario.replace(ARQUIVO_PARQUET)
    tamanho_mb = ARQUIVO_PARQUET.stat().st_size / 1024 / 1024
    print(f"Arquivo salvo em {ARQUIVO_PARQUET.relative_to(PASTA_PROJETO)} ({tamanho_mb:.1f} MB)")


def salvar_metadados(info_ckan):
    """Grava um JSON pequeno com as datas e informações básicas da base."""
    PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    # Lê só o cabeçalho do parquet (rápido), não os dados.
    numero_linhas = pq.read_metadata(ARQUIVO_PARQUET).num_rows

    metadados = {
        "fonte": "ANEEL - Relação de empreendimentos de Mini e Micro Geração Distribuída",
        "licenca": "ODbL",
        "url_download": URL_DOWNLOAD,
        "data_download_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # O CKAN informa as datas em UTC, sem fuso no texto.
        "ultima_atualizacao_portal_utc": info_ckan.get("last_modified"),
        "tamanho_bytes": ARQUIVO_PARQUET.stat().st_size,
        "numero_linhas": numero_linhas,
    }
    with open(ARQUIVO_METADADOS, "w", encoding="utf-8") as arquivo:
        json.dump(metadados, arquivo, ensure_ascii=False, indent=2)
    print(f"Metadados salvos em {ARQUIVO_METADADOS.relative_to(PASTA_PROJETO)}")


def main():
    info_ckan = consultar_ckan()
    baixar_arquivo()
    salvar_metadados(info_ckan)


if __name__ == "__main__":
    try:
        main()
    except Exception as erro:
        # Código de saída 1 avisa o GitHub Actions que algo deu errado.
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)
