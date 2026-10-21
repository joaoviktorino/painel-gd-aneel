"""Painel de Micro e Minigeração Distribuída (ANEEL).

Lê apenas os resumos de dados/processados/ (gerados por processar_dados.py).
As cores e fontes ficam em .streamlit/config.toml.

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
# Prazo da Lei 14.300/2022 para manter as regras antigas de compensação.
PRAZO_LEI_14300 = date(2023, 1, 7)
# Quantos meses finais da série tratamos como provavelmente incompletos.
MESES_RECENTES_INCOMPLETOS = 3
INICIO_GRAFICO_MENSAL = "2016-01-01"

URL_DATASET = "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2"
URL_LICENCA = "https://opendatacommons.org/licenses/odbl/"

# Cores fixas por região, para o mesmo estado ter a mesma cor em todos os gráficos.
CORES_REGIAO = {
    "Sudeste": "#F59E0B",
    "Sul": "#3B82F6",
    "Nordeste": "#14B8A6",
    "Centro Oeste": "#8B5CF6",
    "Norte": "#F43F5E",
}
COR_DESTAQUE = "#F59E0B"
NOMES_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ---------- Carregamento dos dados ----------

@st.cache_data(ttl="1h")
def carregar_resumos():
    """Lê os CSVs e JSONs uma vez e guarda em cache por 1 hora."""
    por_estado = pd.read_csv(PASTA_PROCESSADOS / "por_estado.csv")
    por_fonte = pd.read_csv(PASTA_PROCESSADOS / "por_fonte.csv")
    por_mes = pd.read_csv(PASTA_PROCESSADOS / "por_mes.csv", parse_dates=["mes"])
    with open(PASTA_PROCESSADOS / "processamento.json", encoding="utf-8") as arquivo:
        processamento = json.load(arquivo)
    with open(PASTA_PROCESSADOS / "metadados.json", encoding="utf-8") as arquivo:
        metadados = json.load(arquivo)
    return por_estado, por_fonte, por_mes, processamento, metadados


# ---------- Formatação em português ----------

def numero_br(valor, casas=0):
    """Formata números no padrão brasileiro: 1.234.567,8"""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(texto_iso):
    """Converte '2026-10-10' (ou com hora) em '10/10/2026'."""
    return date.fromisoformat(texto_iso[:10]).strftime("%d/%m/%Y")


def mes_br(data):
    """Converte uma data em 'jan/2023'."""
    return f"{NOMES_MESES[data.month - 1]}/{data.year}"


def estilizar(figura, altura=420):
    """Visual comum dos gráficos: fundo transparente, números em pt-BR, legenda no topo."""
    figura.update_layout(
        height=altura,
        separators=",.",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": None},
        hoverlabel={"font_family": "Inter"},
    )
    figura.update_xaxes(showgrid=False)
    figura.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return figura


# ---------- Cálculos para os destaques ----------

st.set_page_config(
    page_title="Geração distribuída no Brasil",
    page_icon=":material/solar_power:",
    layout="wide",
)

por_estado, por_fonte, por_mes, processamento, metadados = carregar_resumos()

total_usinas = por_estado["quantidade"].sum()
potencia_total_kw = por_estado["potencia_kw"].sum()
media_nacional_kw = potencia_total_kw / total_usinas

por_estado = por_estado.assign(
    potencia_mw=por_estado["potencia_kw"] / 1000,
    media_kw=por_estado["potencia_kw"] / por_estado["quantidade"],
)

# Série mensal com acumulado e marcação dos meses recentes incompletos.
por_mes = por_mes.assign(
    potencia_mw=por_mes["potencia_kw"] / 1000,
    acumulado_gw=por_mes["potencia_kw"].cumsum() / 1_000_000,
)
ultimo_mes = por_mes["mes"].max()
inicio_incompletos = ultimo_mes - pd.DateOffset(months=MESES_RECENTES_INCOMPLETOS - 1)

# Totais por ano; o ano atual fica fora das comparações por estar incompleto.
por_ano = (
    por_mes.assign(ano=por_mes["mes"].dt.year)
    .groupby("ano")[["quantidade", "potencia_kw"]]
    .sum()
)
ultimo_ano_completo = ultimo_mes.year - 1
anos_sparkline = por_ano.loc[2016:ultimo_ano_completo]
gw_ultimo_ano = por_ano.loc[ultimo_ano_completo, "potencia_kw"] / 1_000_000
gw_ano_anterior = por_ano.loc[ultimo_ano_completo - 1, "potencia_kw"] / 1_000_000
variacao_ano = (gw_ultimo_ano / gw_ano_anterior - 1) * 100

solar = por_fonte[por_fonte["fonte"] == "Radiação solar"].iloc[0]
solar_pct_usinas = solar["quantidade"] / por_fonte["quantidade"].sum() * 100
solar_pct_potencia = solar["potencia_kw"] / por_fonte["potencia_kw"].sum() * 100

top3 = por_estado.nlargest(3, "potencia_kw")
top3_pct = top3["potencia_kw"].sum() / potencia_total_kw * 100

maior_media = por_estado.loc[por_estado["media_kw"].idxmax()]
posicao_potencia = int(por_estado["potencia_kw"].rank(ascending=False)[maior_media.name])
posicao_quantidade = int(por_estado["quantidade"].rank(ascending=False)[maior_media.name])
lider_quantidade = por_estado.loc[por_estado["quantidade"].idxmax()]

pico = por_mes.loc[por_mes["quantidade"].idxmax()]
gw_ate_lei = por_mes.loc[por_mes["mes"] < pd.Timestamp(PRAZO_LEI_14300.replace(day=1)), "potencia_kw"].sum() / 1_000_000
pct_depois_lei = (1 - gw_ate_lei * 1_000_000 / potencia_total_kw) * 100


# ---------- Cabeçalho ----------

st.title("Geração distribuída no Brasil", icon=":material/solar_power:")
st.markdown(
    f":orange-badge[:material/calendar_month: Referência {processamento['periodo_referencia']}] "
    f":blue-badge[:material/database: Base ANEEL de {data_br(processamento['data_geracao_conjunto'])}] "
    f":gray-badge[:material/schedule: Conexões até {data_br(processamento['data_conexao_mais_recente'])}]"
)
st.caption(
    "Micro e minigeração distribuída: usinas de até 5 MW instaladas em residências, "
    "comércios, propriedades rurais e indústrias e conectadas à rede das distribuidoras."
)

st.warning(
    f"A ANEEL suspendeu a atualização desta base entre {INICIO_SUSPENSAO:%d/%m/%Y} e "
    f"{FIM_SUSPENSAO:%d/%m/%Y}, durante a migração do sistema SISGD para o sistema MMGD. "
    "Os meses após a migração, e em especial os mais recentes, podem estar incompletos: "
    "conexões recentes ainda podem não ter sido registradas.",
    title="Dados recentes podem estar subestimados",
    icon=":material/warning:",
)

# ---------- Indicadores ----------

colunas = st.columns(4)
with colunas[0]:
    st.metric(
        "Usinas conectadas",
        numero_br(total_usinas),
        border=True,
        height="stretch",
        chart_data=anos_sparkline["quantidade"].tolist(),
        chart_type="bar",
        help=f"Novas usinas por ano, de 2016 a {ultimo_ano_completo}.",
    )
with colunas[1]:
    st.metric(
        "Potência instalada",
        f"{numero_br(potencia_total_kw / 1_000_000, 1)} GW",
        border=True,
        height="stretch",
        chart_data=(anos_sparkline["potencia_kw"].cumsum() / 1_000_000).tolist(),
        chart_type="area",
        help="Potência acumulada ao fim de cada ano.",
    )
with colunas[2]:
    st.metric(
        f"Potência adicionada em {ultimo_ano_completo}",
        f"{numero_br(gw_ultimo_ano, 1)} GW",
        delta=f"{numero_br(variacao_ano, 1)}% vs {ultimo_ano_completo - 1}",
        delta_color="normal",
        border=True,
        height="stretch",
        help=f"Último ano completo. {ultimo_mes.year} ainda está em andamento.",
    )
with colunas[3]:
    st.metric(
        "Tamanho médio por usina",
        f"{numero_br(media_nacional_kw, 1)} kW",
        border=True,
        height="stretch",
        chart_data=(anos_sparkline["potencia_kw"] / anos_sparkline["quantidade"]).tolist(),
        chart_type="line",
        help="Potência média das usinas conectadas em cada ano.",
    )

# ---------- Destaques ----------

st.subheader("O que os números mostram", icon=":material/insights:")
destaques = [
    (
        ":material/wb_sunny:",
        "Quase tudo é solar",
        f"**{numero_br(solar_pct_usinas, 2)}%** das usinas e **{numero_br(solar_pct_potencia, 1)}%** "
        "da potência vêm de painéis fotovoltaicos. Biogás, hidráulica, vento e as demais fontes "
        f"somam só {numero_br(total_usinas - solar['quantidade'])} usinas.",
    ),
    (
        ":material/location_on:",
        f"Três estados, {numero_br(top3_pct, 1)}% da potência",
        f"**{', '.join(top3['uf'][:2])} e {top3['uf'].iloc[2]}** lideram em potência instalada, "
        f"de {por_estado['uf'].nunique()} unidades da federação. {lider_quantidade['uf']} também "
        f"lidera em número de usinas ({numero_br(lider_quantidade['quantidade'])}).",
    ),
    (
        ":material/bolt:",
        f"Usinas maiores: {maior_media['uf']}",
        f"A média em {maior_media['uf']} é de **{numero_br(maior_media['media_kw'], 1)} kW** por usina, "
        f"{numero_br(maior_media['media_kw'] / media_nacional_kw, 1)} vez a média nacional "
        f"({numero_br(media_nacional_kw, 1)} kW). É o **{posicao_potencia}º** estado em potência, "
        f"mas o {posicao_quantidade}º em número de usinas.",
    ),
    (
        ":material/gavel:",
        "A corrida da Lei 14.300",
        f"O recorde mensal foi em **{mes_br(pico['mes'])}** ({numero_br(pico['quantidade'])} conexões), "
        f"perto do prazo de {PRAZO_LEI_14300:%d/%m/%Y} para manter as regras antigas de compensação. "
        f"Mesmo assim, **{numero_br(pct_depois_lei, 0)}%** da potência atual entrou depois disso.",
    ),
]
for linha in (destaques[:2], destaques[2:]):
    for coluna, (icone, titulo, texto) in zip(st.columns(2), linha):
        with coluna.container(border=True, height="stretch"):
            st.subheader(titulo, icon=icone, anchor=False)
            st.markdown(texto)

# ---------- Crescimento e regiões ----------

coluna_acumulado, coluna_regiao = st.columns([3, 2])

with coluna_acumulado.container(border=True, height="stretch"):
    st.subheader("Potência acumulada", icon=":material/trending_up:")
    serie = por_mes[por_mes["mes"] >= INICIO_GRAFICO_MENSAL]
    figura = px.area(serie, x="mes", y="acumulado_gw", labels={"mes": "", "acumulado_gw": "GW"})
    figura.update_traces(
        line_color=COR_DESTAQUE,
        fillcolor="rgba(245,158,11,0.18)",
        hovertemplate="%{x|%m/%Y}<br><b>%{y:,.1f} GW</b><extra></extra>",
    )
    st.plotly_chart(estilizar(figura, 380), alt="Área com a potência acumulada em GW ao longo dos meses")

with coluna_regiao.container(border=True, height="stretch"):
    st.subheader("Potência por região", icon=":material/donut_large:")
    regioes = por_estado.groupby("regiao", as_index=False)["potencia_mw"].sum()
    figura = px.pie(
        regioes,
        names="regiao",
        values="potencia_mw",
        hole=0.62,
        color="regiao",
        color_discrete_map=CORES_REGIAO,
    )
    figura.update_traces(
        textinfo="percent",
        hovertemplate="%{label}<br><b>%{value:,.0f} MW</b> (%{percent})<extra></extra>",
        sort=True,
    )
    figura.add_annotation(
        text=f"<b>{numero_br(potencia_total_kw / 1_000_000, 1)}</b><br>GW",
        showarrow=False,
        font={"size": 22},
    )
    st.plotly_chart(estilizar(figura, 380), alt="Rosca com a participação de cada região na potência instalada")

# ---------- Ranking por estado ----------

with st.container(border=True):
    st.subheader("Ranking por estado", icon=":material/leaderboard:")
    indicadores = {
        "Potência total": ("potencia_mw", "Potência (MW)", "%{x:,.0f} MW"),
        "Número de usinas": ("quantidade", "Usinas", "%{x:,.0f} usinas"),
        "Tamanho médio": ("media_kw", "kW por usina", "%{x:,.1f} kW por usina"),
    }
    escolha = st.segmented_control(
        "Indicador", list(indicadores), default="Potência total", required=True, key="indicador_estado"
    )
    coluna, rotulo, formato = indicadores[escolha]
    figura = px.bar(
        por_estado.sort_values(coluna),
        x=coluna,
        y="uf",
        orientation="h",
        color="regiao",
        color_discrete_map=CORES_REGIAO,
        labels={coluna: rotulo, "uf": "", "regiao": "Região"},
    )
    figura.update_layout(yaxis={"categoryorder": "total ascending"}, bargap=0.25)
    figura.update_traces(hovertemplate=f"<b>%{{y}}</b><br>{formato}<extra></extra>")
    if coluna == "media_kw":
        figura.add_vline(x=media_nacional_kw, line_dash="dot", line_color="gray", line_width=2)
    st.plotly_chart(estilizar(figura, 720), alt=f"Barras horizontais com {rotulo.lower()} de cada estado")
    if coluna == "media_kw":
        st.caption(f"A linha pontilhada marca a média do Brasil: {numero_br(media_nacional_kw, 1)} kW por usina.")

# ---------- Conexões por mês ----------

with st.container(border=True):
    st.subheader("Novas conexões por mês", icon=":material/calendar_view_month:")
    medida = st.segmented_control(
        "Medida", ["Usinas", "Potência (MW)"], default="Usinas", required=True, key="medida_mensal"
    )
    coluna_y = "quantidade" if medida == "Usinas" else "potencia_mw"
    formato_y = "%{y:,.0f} usinas" if medida == "Usinas" else "%{y:,.0f} MW"
    serie = por_mes[por_mes["mes"] >= INICIO_GRAFICO_MENSAL].assign(
        situacao=lambda df: df["mes"].ge(inicio_incompletos).map(
            {True: "Provavelmente incompleto", False: "Registrado"}
        )
    )
    figura = px.bar(
        serie,
        x="mes",
        y=coluna_y,
        color="situacao",
        color_discrete_map={"Registrado": COR_DESTAQUE, "Provavelmente incompleto": "#94A3B8"},
        labels={"mes": "", coluna_y: medida, "situacao": ""},
    )
    figura.update_traces(hovertemplate=f"%{{x|%m/%Y}}<br><b>{formato_y}</b><extra></extra>")
    figura.add_vrect(
        x0=INICIO_SUSPENSAO.isoformat(),
        x1=FIM_SUSPENSAO.isoformat(),
        fillcolor="#F43F5E",
        opacity=0.18,
        line_width=0,
        annotation_text="Suspensão",
        annotation_position="top left",
    )
    figura.add_vline(
        x=PRAZO_LEI_14300.isoformat(),
        line_dash="dot",
        line_color="gray",
        annotation_text="Prazo Lei 14.300",
        annotation_position="top left",
    )
    st.plotly_chart(estilizar(figura, 440), alt="Barras com as novas conexões de cada mês desde 2016")
    st.caption(
        "A base não traz a data de conexão; usamos a data da última atualização cadastral como "
        f"aproximação. Os últimos {MESES_RECENTES_INCOMPLETOS} meses aparecem em cinza porque ainda "
        "estão sendo registrados. A faixa vermelha marca a suspensão da atualização da base."
    )

# ---------- Outras fontes ----------

with st.container(border=True):
    st.subheader("Além da energia solar", icon=":material/eco:")
    outras = por_fonte[por_fonte["fonte"] != "Radiação solar"].assign(
        potencia_mw=lambda df: df["potencia_kw"] / 1000
    )
    figura = px.bar(
        outras.sort_values("potencia_mw"),
        x="potencia_mw",
        y="fonte",
        orientation="h",
        labels={"potencia_mw": "Potência (MW)", "fonte": ""},
        custom_data=["quantidade"],
    )
    figura.update_traces(
        marker_color="#14B8A6",
        hovertemplate="<b>%{y}</b><br>%{x:,.1f} MW · %{customdata[0]:,.0f} usinas<extra></extra>",
    )
    st.plotly_chart(estilizar(figura, 480), alt="Barras com a potência das fontes que não são solares")
    st.caption(
        f"Juntas, as outras fontes somam {numero_br(outras['potencia_mw'].sum(), 0)} MW em "
        f"{numero_br(outras['quantidade'].sum())} usinas."
    )

# ---------- Rodapé ----------

st.caption(
    f":material/info: Fonte: [ANEEL – Relação de empreendimentos de Mini e Micro Geração Distribuída]({URL_DATASET}), "
    f"dados abertos sob a licença [ODbL]({URL_LICENCA}). "
    f"Download em {data_br(metadados['data_download_utc'])}."
)
