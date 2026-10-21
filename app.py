"""Painel de Micro e Minigeração Distribuída (ANEEL).

Lê apenas os resumos de dados/processados/ (gerados por processar_dados.py).

Uso:  python -m streamlit run app.py
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

PASTA_PROCESSADOS = Path(__file__).resolve().parent / "dados" / "processados"

# Período em que a ANEEL suspendeu a atualização da base (migração SISGD → MMGD).
INICIO_SUSPENSAO = date(2025, 9, 23)
FIM_SUSPENSAO = date(2025, 11, 13)

URL_DATASET = "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2"
URL_LICENCA = "https://opendatacommons.org/licenses/odbl/"


# ---------- Carregamento dos dados ----------

@st.cache_data(ttl="1h")
def carregar_resumos():
    """Lê os CSVs e JSONs uma vez e guarda em cache por 1 hora."""
    por_estado = pd.read_csv(PASTA_PROCESSADOS / "por_estado.csv")
    por_mes = pd.read_csv(PASTA_PROCESSADOS / "por_mes.csv", parse_dates=["mes"])
    with open(PASTA_PROCESSADOS / "processamento.json", encoding="utf-8") as arquivo:
        processamento = json.load(arquivo)
    with open(PASTA_PROCESSADOS / "metadados.json", encoding="utf-8") as arquivo:
        metadados = json.load(arquivo)
    return por_estado, por_mes, processamento, metadados


def numero_br(valor, casas=0):
    """Formata números no padrão brasileiro: 1.234.567,8"""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(texto_iso):
    """Converte '2026-10-10' (ou com hora) em '10/10/2026'."""
    return date.fromisoformat(texto_iso[:10]).strftime("%d/%m/%Y")


# ---------- Página ----------

st.set_page_config(page_title="Geração distribuída no Brasil", page_icon=":material/solar_power:", layout="wide")

st.title("Geração distribuída no Brasil")
st.caption("Micro e minigeração distribuída conectada às distribuidoras, segundo a ANEEL.")

por_estado, por_mes, processamento, metadados = carregar_resumos()

st.warning(
    f"A ANEEL suspendeu a atualização desta base entre {INICIO_SUSPENSAO:%d/%m/%Y} e "
    f"{FIM_SUSPENSAO:%d/%m/%Y}, durante a migração do sistema SISGD para o sistema MMGD. "
    "Os meses após a migração, e em especial os meses mais recentes, podem estar "
    "incompletos: conexões recentes ainda podem não ter sido registradas.",
    title="Dados recentes podem estar subestimados",
    icon=":material/warning:",
)

st.markdown(
    f"**Referência dos dados:** {processamento['periodo_referencia']} · "
    f"base gerada pela ANEEL em {data_br(processamento['data_geracao_conjunto'])} · "
    f"conexões registradas até {data_br(processamento['data_conexao_mais_recente'])}"
)

# ---------- Indicadores ----------

total_usinas = por_estado["quantidade"].sum()
potencia_total_gw = por_estado["potencia_kw"].sum() / 1_000_000

with st.container(horizontal=True):
    st.metric("Total de usinas", numero_br(total_usinas), border=True)
    st.metric("Potência instalada total", f"{numero_br(potencia_total_gw, 2)} GW", border=True)

# ---------- Potência por estado ----------

with st.container(border=True):
    st.subheader("Potência instalada por estado")
    grafico_estado = por_estado.assign(potencia_mw=por_estado["potencia_kw"] / 1000)
    figura = px.bar(
        grafico_estado.sort_values("potencia_mw"),
        x="potencia_mw",
        y="uf",
        orientation="h",
        color="regiao",
        labels={"potencia_mw": "Potência (MW)", "uf": "Estado", "regiao": "Região"},
        height=700,
    )
    figura.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(figura, alt="Barras horizontais com a potência instalada em MW de cada estado")

# ---------- Conexões por mês ----------

with st.container(border=True):
    st.subheader("Novas conexões por mês")
    st.caption(
        "A base não traz a data de conexão. Usamos a data da última atualização "
        "cadastral de cada usina como aproximação. A faixa laranja marca o período "
        "de suspensão da atualização. Antes de 2016 havia poucas conexões por mês, "
        "por isso o gráfico começa nesse ano."
    )
    figura = px.bar(
        por_mes[por_mes["mes"] >= "2016-01-01"],
        x="mes",
        y="quantidade",
        labels={"mes": "Mês", "quantidade": "Conexões"},
    )
    figura.add_vrect(
        x0=INICIO_SUSPENSAO.isoformat(),
        x1=FIM_SUSPENSAO.isoformat(),
        fillcolor="orange",
        opacity=0.3,
        line_width=0,
        annotation_text="Suspensão",
        annotation_position="top left",
    )
    st.plotly_chart(figura, alt="Barras com o número de novas conexões em cada mês")

# ---------- Rodapé ----------

st.divider()
st.caption(
    f"Fonte: [ANEEL – Relação de empreendimentos de Mini e Micro Geração Distribuída]({URL_DATASET}), "
    f"dados abertos sob a licença [ODbL]({URL_LICENCA}). "
    f"Download em {data_br(metadados['data_download_utc'])}."
)
