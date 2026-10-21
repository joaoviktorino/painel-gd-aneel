"""Painel de Micro e Minigeração Distribuída (ANEEL).

Lê apenas os resumos de dados/processados/ (gerados por processar_dados.py).
Os filtros da barra lateral e os cliques nos gráficos filtram a página inteira.
As cores e fontes ficam em .streamlit/config.toml.

Uso:  python -m streamlit run app.py
"""

import json
import math
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

PASTA_PROCESSADOS = Path(__file__).resolve().parent / "dados" / "processados"

# ---------- Fatos externos (não vêm da base) ----------

# Período em que a ANEEL suspendeu a atualização da base (migração SISGD → MMGD).
INICIO_SUSPENSAO = date(2025, 9, 23)
FIM_SUSPENSAO = date(2025, 11, 13)
# Prazo da Lei 14.300/2022 para manter as regras antigas de compensação.
PRAZO_LEI_14300 = date(2023, 1, 7)

URL_DATASET = "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2"
URL_LICENCA = "https://opendatacommons.org/licenses/odbl/"

# ---------- Parâmetros de análise ----------

# Um mês do fim da série é considerado incompleto quando tem menos que esta
# fração da mediana dos 12 meses anteriores a ele.
LIMIAR_MES_INCOMPLETO = 0.75
# Quantos destaques mostrar e quantos meses entram nas comparações de ritmo.
QUANTIDADE_DESTAQUES = 4
JANELA_MESES = 12
# Os gráficos de linha do tempo começam no mês em que o acumulado do recorte
# passa desta fração do total (antes disso as barras seriam invisíveis).
FRACAO_INICIO_GRAFICO = 0.001
# Destaques de ritmo e recorde só aparecem se houve conexões em pelo menos esta
# fração dos meses comparados (evita "recordes" de poucas usinas isoladas).
FRACAO_MINIMA_MESES_ATIVOS = 0.5
# Um grupo só entra na comparação de tamanho médio se tiver pelo menos esta
# fração das usinas do recorte (evita conclusões sobre grupos minúsculos).
FRACAO_MINIMA_GRUPO = 0.01

# ---------- Aparência ----------

COR_DESTAQUE = "#F59E0B"
COR_INCOMPLETO = "#94A3B8"
CORES_REGIAO = {
    "Sudeste": "#F59E0B",
    "Sul": "#3B82F6",
    "Nordeste": "#14B8A6",
    "Centro Oeste": "#8B5CF6",
    "Norte": "#F43F5E",
}
NOMES_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Dimensões filtráveis: coluna → (nome no singular, nome no plural).
DIMENSOES = {
    "regiao": ("Região", "regiões"),
    "uf": ("Estado", "estados"),
    "distribuidora": ("Distribuidora", "distribuidoras"),
    "fonte": ("Fonte", "fontes"),
    "classe": ("Classe de consumo", "classes de consumo"),
    "porte": ("Porte", "portes"),
    "modalidade": ("Modalidade", "modalidades"),
}

# Alguns valores da ANEEL vêm sem acento. Valores novos aparecem como vierem.
ROTULOS = {
    "Microgeracao": "Microgeração",
    "Minigeracao": "Minigeração",
    "Geracao na propria UC": "Geração na própria UC",
    "Auto consumo remoto": "Autoconsumo remoto",
}

st.set_page_config(
    page_title="Geração distribuída no Brasil",
    page_icon=":material/solar_power:",
    layout="wide",
)


# ---------- Carregamento dos dados ----------

@st.cache_data(ttl="1h")
def carregar():
    """Lê o cubo e os metadados uma vez e guarda em cache por 1 hora."""
    cubo = pd.read_csv(PASTA_PROCESSADOS / "cubo.csv", parse_dates=["mes"])
    regioes = pd.read_csv(PASTA_PROCESSADOS / "por_estado.csv")[["uf", "regiao"]]
    cubo = cubo.merge(regioes, on="uf", how="left")
    for coluna in DIMENSOES:
        cubo[coluna] = cubo[coluna].fillna("Não informado").replace(ROTULOS)
    distribuidoras = pd.read_csv(PASTA_PROCESSADOS / "distribuidoras.csv")
    nomes = dict(zip(distribuidoras["distribuidora"], distribuidoras["nome"]))
    with open(PASTA_PROCESSADOS / "processamento.json", encoding="utf-8") as arquivo:
        processamento = json.load(arquivo)
    with open(PASTA_PROCESSADOS / "metadados.json", encoding="utf-8") as arquivo:
        metadados = json.load(arquivo)
    return cubo, nomes, processamento, metadados


# ---------- Formatação em português ----------

def numero_br(valor, casas=0):
    """Formata números no padrão brasileiro: 1.234.567,8"""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def potencia_br(kw):
    """Escolhe a unidade pelo tamanho do número: kW, MW ou GW."""
    if abs(kw) >= 1_000_000:
        return f"{numero_br(kw / 1_000_000, 1)} GW"
    if abs(kw) >= 1_000:
        return f"{numero_br(kw / 1_000, 1)} MW"
    return f"{numero_br(kw, 1)} kW"


def pct_br(fracao, casas=1):
    """Percentual que nunca arredonda para 0% ou 100% quando o valor não é exato."""
    while casas < 3 and 0 < fracao < 1 and round(fracao * 100, casas) in (0, 100):
        casas += 1
    return f"{numero_br(fracao * 100, casas)}%"


def vezes_br(razao):
    return f"{numero_br(razao, 1)} {'vez' if razao < 2 else 'vezes'}"


def data_br(texto_iso):
    return date.fromisoformat(texto_iso[:10]).strftime("%d/%m/%Y")


def mes_br(mes):
    mes = pd.Timestamp(mes)
    return f"{NOMES_MESES[mes.month - 1]}/{mes.year}"


def estilizar(figura, altura=380):
    """Visual comum dos gráficos: fundo transparente, números em pt-BR."""
    figura.update_layout(
        height=altura,
        separators=",.",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": None},
        hoverlabel={"font_family": "Inter"},
        clickmode="event+select",
    )
    # Barras horizontais sempre ordenadas pelo total, mesmo com várias cores.
    if figura.data and getattr(figura.data[0], "orientation", None) == "h":
        figura.update_layout(yaxis={"categoryorder": "total ascending"})
    figura.update_xaxes(showgrid=False)
    figura.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return figura


# ---------- Estado dos filtros ----------

cubo, NOMES_DISTRIBUIDORAS, processamento, metadados = carregar()
MESES = sorted(cubo["mes"].dropna().dt.strftime("%Y-%m").unique())

PERIODO_COMPLETO = (MESES[0], MESES[-1])

st.session_state.setdefault("rodada", 0)
st.session_state.setdefault("filtro_periodo", PERIODO_COMPLETO)
for _dim in DIMENSOES:
    st.session_state.setdefault(f"filtro_{_dim}", [])


def periodo_selecionado():
    """Período escolhido como datas, ou None se for a série inteira."""
    inicio, fim = st.session_state["filtro_periodo"]
    if (inicio, fim) == PERIODO_COMPLETO:
        return None
    return pd.Timestamp(inicio), pd.Timestamp(fim)


def filtrar(exceto=None):
    """Aplica todos os filtros, menos o da dimensão `exceto`.

    Cada gráfico usa os filtros das outras dimensões, para que as opções da
    própria dimensão continuem visíveis (e clicáveis) depois de um clique.
    """
    mascara = pd.Series(True, index=cubo.index)
    for dim in DIMENSOES:
        selecionados = st.session_state[f"filtro_{dim}"]
        if dim != exceto and selecionados:
            mascara &= cubo[dim].isin(selecionados)
    periodo = periodo_selecionado()
    if exceto != "periodo" and periodo:
        mascara &= cubo["mes"].between(*periodo)
    return cubo[mascara]


def limpar_filtros():
    st.session_state["filtro_periodo"] = PERIODO_COMPLETO
    for dim in DIMENSOES:
        st.session_state[f"filtro_{dim}"] = []
    st.session_state["rodada"] += 1


def ao_clicar(dim, chave):
    """Cria o callback que transforma o clique num gráfico em filtro.

    Clicar de novo no mesmo item desfaz o filtro.
    """
    def callback():
        pontos = st.session_state[chave]["selection"]["points"]
        valores = []
        for ponto in pontos:
            valor = (ponto.get("customdata") or [None])[0]
            if valor is not None and valor not in valores:
                valores.append(valor)
        atual = st.session_state[f"filtro_{dim}"]
        st.session_state[f"filtro_{dim}"] = [] if sorted(valores) == sorted(atual) else valores
        st.session_state["rodada"] += 1  # chave nova = gráfico sem a seleção antiga

    return callback


def ao_selecionar_periodo(chave):
    def callback():
        meses = [pd.Timestamp(p["x"]) for p in st.session_state[chave]["selection"]["points"]]
        if meses:
            st.session_state["filtro_periodo"] = (min(meses).strftime("%Y-%m"), max(meses).strftime("%Y-%m"))
        else:
            st.session_state["filtro_periodo"] = PERIODO_COMPLETO
        st.session_state["rodada"] += 1

    return callback


def grafico_clicavel(figura, dim, nome, alt, altura=380):
    """Mostra um gráfico em que clicar numa barra filtra a página."""
    chave = f"grafico_{nome}_{st.session_state['rodada']}"
    st.plotly_chart(
        estilizar(figura, altura),
        key=chave,
        on_select=ao_clicar(dim, chave),
        selection_mode="points",
        alt=alt,
    )


def esmaecer_nao_selecionados(figura, dim):
    """Deixa em destaque só os itens filtrados; os outros ficam claros."""
    selecionados = st.session_state[f"filtro_{dim}"]
    if not selecionados:
        return
    for trace in figura.data:
        trace.marker.opacity = [1.0 if c[0] in selecionados else 0.25 for c in trace.customdata]


# ---------- Séries e meses incompletos ----------

def serie_mensal(df):
    """Quantidade e potência por mês, com todos os meses (inclusive os zerados)."""
    indice = pd.to_datetime(MESES)
    serie = df.dropna(subset=["mes"]).groupby("mes")[["quantidade", "potencia_kw"]].sum()
    return serie.reindex(indice, fill_value=0).rename_axis("mes")


def cortar_inicio(serie):
    """Remove os meses iniciais em que o recorte ainda era desprezível."""
    acumulado = serie["quantidade"].cumsum()
    return serie[acumulado >= FRACAO_INICIO_GRAFICO * acumulado.iloc[-1]] if acumulado.iloc[-1] else serie


def detectar_meses_incompletos(serie):
    """Percorre o fim da série e marca os meses muito abaixo do ritmo recente.

    Usa a série nacional, que é estável, e não a filtrada.
    """
    quantidades = serie["quantidade"].tolist()
    incompletos = []
    i = len(quantidades) - 1
    while i >= JANELA_MESES:
        mediana = pd.Series(quantidades[i - JANELA_MESES:i]).median()
        if mediana > 0 and quantidades[i] < LIMIAR_MES_INCOMPLETO * mediana:
            incompletos.append(serie.index[i])
            i -= 1
        else:
            break
    return set(incompletos)


SERIE_NACIONAL = serie_mensal(cubo)
MESES_INCOMPLETOS = detectar_meses_incompletos(SERIE_NACIONAL)


def serie_completa(df):
    """Série mensal sem os meses incompletos do fim."""
    serie = serie_mensal(df)
    return serie[~serie.index.isin(MESES_INCOMPLETOS)]


# ---------- Destaques calculados por regras ----------
# Cada regra olha o recorte filtrado e devolve um card com um "peso" entre 0 e
# 1 (quanto o dado chama atenção), ou None quando não há o que dizer. O painel
# mostra os de maior peso. Títulos e conclusões mudam conforme os números.

def agrupar(df, dim):
    grupos = df.groupby(dim)[["quantidade", "potencia_kw"]].sum()
    grupos = grupos[grupos["quantidade"] > 0].sort_values("potencia_kw", ascending=False)
    return grupos.assign(potencia_mw=grupos["potencia_kw"] / 1000)


def destaque_lider(df, dim, icone):
    grupos = agrupar(df, dim)
    if len(grupos) < 2:
        return None
    singular, plural = DIMENSOES[dim]
    lider, segundo = grupos.index[0], grupos.index[1]
    fatia_pot = grupos["potencia_kw"].iloc[0] / grupos["potencia_kw"].sum()
    fatia_usinas = grupos["quantidade"].iloc[0] / grupos["quantidade"].sum()
    if fatia_pot >= 0.9:
        titulo = f"{lider} domina"
        resto = grupos["quantidade"].iloc[1:].sum()
        fecho = f"As demais {plural} somam só {numero_br(resto)} usinas."
    elif fatia_pot >= 0.5:
        titulo = f"{lider} é maioria"
        fecho = f"Em segundo vem {segundo}, com {pct_br(grupos['potencia_kw'].iloc[1] / grupos['potencia_kw'].sum())}."
    else:
        titulo = f"{lider} lidera, sem maioria"
        fecho = f"{segundo} vem logo atrás, com {pct_br(grupos['potencia_kw'].iloc[1] / grupos['potencia_kw'].sum())}."
    texto = (
        f"Entre as {plural}, **{lider}** responde por **{pct_br(fatia_pot)}** da potência "
        f"e {pct_br(fatia_usinas)} das usinas. {fecho}"
    )
    # Quanto mais a líder se afasta de uma divisão igual, mais marcante.
    igual = 1 / len(grupos)
    peso = (fatia_pot - igual) / (1 - igual)
    return {"icone": icone, "titulo": titulo, "texto": texto, "peso": peso}


def destaque_concentracao(df):
    dim = "uf" if df["uf"].nunique() > 1 else "distribuidora"
    grupos = agrupar(df, dim)
    n = len(grupos)
    if n < 3:
        return None
    _, plural = DIMENSOES[dim]
    # Quantos grupos, dos maiores para os menores, são precisos para chegar à
    # metade da potência. Poucos grupos = potência concentrada.
    acumulado = grupos["potencia_kw"].cumsum() / grupos["potencia_kw"].sum()
    k = int((acumulado < 0.5).sum()) + 1
    fatia = acumulado.iloc[k - 1]
    nomes = grupos.index[:k].tolist()
    if k == 1:
        titulo = f"{nomes[0]} concentra {pct_br(fatia)}"
        texto = (
            f"Sozinha, **{nomes[0]}** tem **{pct_br(fatia)}** da potência entre {n} {plural}. "
            f"A segunda, {grupos.index[1]}, tem {pct_br(grupos['potencia_kw'].iloc[1] / grupos['potencia_kw'].sum())}."
        )
    else:
        lista = ", ".join(nomes[:-1]) + " e " + nomes[-1] if k <= 5 else f"os {k} maiores"
        titulo = (
            f"Metade da potência em {k} de {n} {plural}"
            if k / n <= 0.25 else f"Potência espalhada entre {n} {plural}"
        )
        texto = (
            f"São precisos **{k}** de {n} {plural} para somar metade da potência"
            f"{f' ({lista})' if k <= 5 else ''}: juntos, {pct_br(fatia)}."
        )
    # Se a potência fosse dividida por igual, seriam precisos n/2 grupos.
    peso = max(0.0, 1 - k / (n / 2))
    return {"icone": ":material/location_on:", "titulo": titulo, "texto": texto, "peso": peso}


def destaque_tamanho(df):
    """Procura a dimensão em que o tamanho médio das usinas mais varia."""
    media_geral = df["potencia_kw"].sum() / df["quantidade"].sum()
    melhor = None
    for dim in ("uf", "distribuidora", "classe", "modalidade"):
        grupos = agrupar(df, dim)
        grupos = grupos[grupos["quantidade"] >= FRACAO_MINIMA_GRUPO * df["quantidade"].sum()]
        if len(grupos) < 2:
            continue
        medias = grupos["potencia_kw"] / grupos["quantidade"]
        razao_maior, razao_menor = medias.max() / media_geral, medias.min() / media_geral
        variacao = max(razao_maior, 1 / razao_menor)
        if melhor is None or variacao > melhor[0]:
            melhor = (variacao, dim, medias, razao_maior, razao_menor)
    if melhor is None:
        return None
    variacao, dim, medias, razao_maior, razao_menor = melhor
    _, plural = DIMENSOES[dim]
    if variacao < 1.25:
        titulo = f"Tamanho parecido entre {plural}"
        texto = (
            f"A média é de **{numero_br(media_geral, 1)} kW** por usina e nenhum grupo "
            f"se afasta mais de {pct_br(variacao - 1, 0)} dela."
        )
    elif razao_maior >= 1 / razao_menor:
        maior = medias.idxmax()
        titulo = f"Usinas maiores: {maior}"
        texto = (
            f"{maior} tem média de **{numero_br(medias.max(), 1)} kW** por usina, "
            f"{vezes_br(razao_maior)} a média do recorte ({numero_br(media_geral, 1)} kW)."
        )
    else:
        menor = medias.idxmin()
        titulo = f"Usinas menores: {menor}"
        texto = (
            f"{menor} tem média de **{numero_br(medias.min(), 1)} kW** por usina, "
            f"{pct_br(1 - razao_menor, 0)} abaixo da média do recorte ({numero_br(media_geral, 1)} kW)."
        )
    peso = min(1.0, (variacao - 1) / 2)
    return {"icone": ":material/bolt:", "titulo": titulo, "texto": texto, "peso": peso}


def serie_tem_volume(serie, meses):
    """True se houve conexões em boa parte dos últimos `meses` meses."""
    janela = serie["quantidade"].iloc[-meses:]
    return len(janela) == meses and (janela > 0).mean() >= FRACAO_MINIMA_MESES_ATIVOS


def destaque_tendencia(serie):
    if not serie_tem_volume(serie, 2 * JANELA_MESES):
        return None
    recente = serie.iloc[-JANELA_MESES:]
    anterior = serie.iloc[-2 * JANELA_MESES:-JANELA_MESES]
    if anterior["potencia_kw"].sum() == 0:
        return None
    variacao = recente["potencia_kw"].sum() / anterior["potencia_kw"].sum() - 1
    if variacao >= 0.1:
        titulo, icone = "Conexões em alta", ":material/trending_up:"
    elif variacao <= -0.1:
        titulo, icone = "Conexões em queda", ":material/trending_down:"
    else:
        titulo, icone = "Ritmo de conexões estável", ":material/trending_flat:"
    texto = (
        f"Nos 12 meses até {mes_br(recente.index[-1])} entraram **{potencia_br(recente['potencia_kw'].sum())}** "
        f"({numero_br(recente['quantidade'].sum())} usinas), **{pct_br(abs(variacao))} "
        f"{'a mais' if variacao >= 0 else 'a menos'}** que nos 12 meses anteriores."
    )
    janela_inicio = anterior.index[0].date()
    if janela_inicio <= FIM_SUSPENSAO and recente.index[-1].date() >= INICIO_SUSPENSAO:
        texto += " O período inclui a suspensão da base, o que pode afetar a comparação."
    peso = min(1.0, abs(variacao) / 0.3)
    return {"icone": icone, "titulo": titulo, "texto": texto, "peso": peso}


def destaque_pico(serie):
    if not serie_tem_volume(serie, JANELA_MESES):
        return None
    mes_pico = serie["quantidade"].idxmax()
    valor_pico = serie["quantidade"].max()
    ritmo_atual = serie["quantidade"].iloc[-3:].mean()
    distancia = ritmo_atual / valor_pico - 1
    recente = mes_pico >= serie.index[-JANELA_MESES]
    titulo = "Recorde recente" if recente else f"Recorde em {mes_br(mes_pico)}"
    texto = (
        f"O mês com mais conexões foi **{mes_br(mes_pico)}** ({numero_br(valor_pico)} usinas). "
        f"Nos últimos 3 meses completos, a média foi de {numero_br(ritmo_atual)} por mês, "
        f"{pct_br(abs(distancia), 0)} {'abaixo' if distancia < 0 else 'acima'} do recorde."
    )
    meses_ate_prazo = abs((mes_pico.year - PRAZO_LEI_14300.year) * 12 + mes_pico.month - PRAZO_LEI_14300.month)
    if meses_ate_prazo <= 2:
        texto += (
            f" O recorde coincide com o prazo da Lei 14.300 ({PRAZO_LEI_14300:%d/%m/%Y}) "
            "para manter as regras antigas de compensação."
        )
    peso = 0.6 if recente else min(1.0, abs(distancia))
    return {"icone": ":material/emoji_events:", "titulo": titulo, "texto": texto, "peso": peso}


def destaque_porte(df):
    grupos = agrupar(df, "porte")
    if len(grupos) < 2:
        return None
    medias = grupos["potencia_kw"] / grupos["quantidade"]
    grande = medias.idxmax()
    fatia_usinas = grupos.loc[grande, "quantidade"] / grupos["quantidade"].sum()
    fatia_pot = grupos.loc[grande, "potencia_kw"] / grupos["potencia_kw"].sum()
    razao = fatia_pot / fatia_usinas
    if razao < 2:
        return None
    titulo = "Poucas usinas, muita potência"
    texto = (
        f"**{grande}** é só {pct_br(fatia_usinas)} das usinas, mas **{pct_br(fatia_pot)}** da potência: "
        f"cada usina tem em média {numero_br(medias[grande], 0)} kW."
    )
    peso = min(1.0, math.log(razao) / math.log(50))
    return {"icone": ":material/factory:", "titulo": titulo, "texto": texto, "peso": peso}


def escolher_destaques(df):
    serie = serie_completa(df)
    periodo = periodo_selecionado()
    if periodo:
        serie = serie[serie.index.to_series().between(*periodo)]
    candidatos = [
        destaque_lider(df, "fonte", ":material/wb_sunny:"),
        destaque_lider(df, "classe", ":material/home:"),
        destaque_concentracao(df),
        destaque_tamanho(df),
        destaque_tendencia(serie),
        destaque_pico(serie),
        destaque_porte(df),
    ]
    candidatos = [c for c in candidatos if c]
    return sorted(candidatos, key=lambda c: c["peso"], reverse=True)[:QUANTIDADE_DESTAQUES]


# ---------- Barra lateral: filtros ----------

def opcoes(dim):
    """Valores da dimensão, do maior para o menor em potência."""
    return cubo.groupby(dim)["potencia_kw"].sum().sort_values(ascending=False).index.tolist()


with st.sidebar:
    st.header("Filtros", icon=":material/filter_alt:")
    # O período fica guardado em "filtro_periodo"; o controle só o mostra e
    # atualiza. A chave muda a cada clique num gráfico, para o controle ser
    # recriado já com o período que o gráfico escolheu.
    chave_periodo = f"controle_periodo_{st.session_state['rodada']}"
    st.select_slider(
        "Período de conexão",
        options=MESES,
        value=st.session_state["filtro_periodo"],  # um par (início, fim) = controle de intervalo
        key=chave_periodo,
        format_func=lambda m: mes_br(m + "-01"),
        on_change=lambda: st.session_state.update(filtro_periodo=tuple(st.session_state[chave_periodo])),
    )
    for dim, (singular, _) in DIMENSOES.items():
        st.multiselect(
            singular,
            opcoes(dim),
            key=f"filtro_{dim}",
            placeholder="Todos",
            format_func=(lambda s: f"{s} – {NOMES_DISTRIBUIDORAS.get(s, '')}") if dim == "distribuidora" else str,
        )
    st.button("Limpar filtros", icon=":material/filter_alt_off:", on_click=limpar_filtros, width="stretch")
    st.caption(
        "Você também pode clicar nas barras dos gráficos para filtrar e arrastar no "
        "gráfico mensal para escolher o período. Clique de novo para desfazer."
    )

# ---------- Cabeçalho ----------

recorte = filtrar()

st.title("Geração distribuída no Brasil", icon=":material/solar_power:")
st.markdown(
    f":orange-badge[:material/calendar_month: Referência {processamento['periodo_referencia']}] "
    f":blue-badge[:material/database: Base ANEEL de {data_br(processamento['data_geracao_conjunto'])}] "
    f":gray-badge[:material/schedule: Conexões até {data_br(processamento['data_conexao_mais_recente'])}]"
)

filtros_ativos = [
    f"{DIMENSOES[d][0]}: {', '.join(map(str, st.session_state[f'filtro_{d}']))}"
    for d in DIMENSOES if st.session_state[f"filtro_{d}"]
]
if periodo_selecionado():
    inicio, fim = periodo_selecionado()
    filtros_ativos.insert(0, f"Período: {mes_br(inicio)} a {mes_br(fim)}")
if filtros_ativos:
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(" ".join(f":orange-badge[{f}]" for f in filtros_ativos))
        st.button("Limpar", icon=":material/close:", on_click=limpar_filtros, type="tertiary")
else:
    st.caption(
        "Micro e minigeração distribuída: usinas de até 5 MW em residências, comércios, "
        "propriedades rurais e indústrias, conectadas à rede das distribuidoras. "
        "Use os filtros ao lado ou clique nos gráficos."
    )

meses_incompletos_txt = (
    f" Pelos números, {'o mês' if len(MESES_INCOMPLETOS) == 1 else 'os meses'} de "
    f"{', '.join(mes_br(m) for m in sorted(MESES_INCOMPLETOS))} ainda "
    f"{'parece incompleto' if len(MESES_INCOMPLETOS) == 1 else 'parecem incompletos'}."
    if MESES_INCOMPLETOS else ""
)
st.warning(
    f"A ANEEL suspendeu a atualização desta base entre {INICIO_SUSPENSAO:%d/%m/%Y} e "
    f"{FIM_SUSPENSAO:%d/%m/%Y}, durante a migração do sistema SISGD para o sistema MMGD. "
    f"Os meses após a migração podem estar subestimados.{meses_incompletos_txt}",
    title="Dados recentes podem estar subestimados",
    icon=":material/warning:",
)

if recorte["quantidade"].sum() == 0:
    st.info("Nenhuma usina com esses filtros.", icon=":material/search_off:")
    st.stop()

# ---------- Indicadores ----------

total_usinas = recorte["quantidade"].sum()
total_kw = recorte["potencia_kw"].sum()
serie_recorte = serie_completa(recorte)
if periodo_selecionado():
    serie_recorte = serie_recorte[serie_recorte.index.to_series().between(*periodo_selecionado())]
ultimos = serie_recorte.iloc[-JANELA_MESES:]
anteriores = serie_recorte.iloc[-2 * JANELA_MESES:-JANELA_MESES]
sparkline = serie_recorte.iloc[-36:]

colunas = st.columns(4)
with colunas[0]:
    st.metric(
        "Usinas", numero_br(total_usinas), border=True, height="stretch",
        chart_data=sparkline["quantidade"].tolist(), chart_type="bar",
        help="Mini-gráfico: novas usinas por mês nos últimos 36 meses completos do recorte.",
    )
with colunas[1]:
    st.metric(
        "Potência instalada", potencia_br(total_kw), border=True, height="stretch",
        chart_data=sparkline["potencia_kw"].cumsum().tolist(), chart_type="area",
        help="Mini-gráfico: potência somada ao longo dos últimos 36 meses completos.",
    )
with colunas[2]:
    if len(anteriores) == JANELA_MESES and anteriores["potencia_kw"].sum() > 0:
        variacao = ultimos["potencia_kw"].sum() / anteriores["potencia_kw"].sum() - 1
        delta = f"{'+' if variacao >= 0 else '-'}{pct_br(abs(variacao))} vs 12 meses antes"
    else:
        delta = None
    st.metric(
        f"Últimos 12 meses (até {mes_br(ultimos.index[-1])})" if len(ultimos) else "Últimos 12 meses",
        potencia_br(ultimos["potencia_kw"].sum()), delta=delta, border=True, height="stretch",
        help="Potência conectada nos 12 meses completos mais recentes do recorte.",
    )
with colunas[3]:
    st.metric(
        "Tamanho médio por usina", f"{numero_br(total_kw / total_usinas, 1)} kW",
        border=True, height="stretch",
        chart_data=(sparkline["potencia_kw"] / sparkline["quantidade"].where(sparkline["quantidade"] > 0))
        .fillna(0).tolist(),
        chart_type="line",
        help="Mini-gráfico: tamanho médio das usinas conectadas em cada mês.",
    )

# ---------- Destaques ----------

destaques = escolher_destaques(recorte)
if destaques:
    st.subheader("O que os números mostram", icon=":material/insights:")
    st.caption(
        "Escolhidos automaticamente: o painel testa várias regras no recorte filtrado "
        "e mostra as que mais se destacam. Mude os filtros e os destaques mudam junto."
    )
    for par in (destaques[:2], destaques[2:4]):
        if not par:
            continue
        for coluna, d in zip(st.columns(2), par):
            with coluna.container(border=True, height="stretch"):
                st.subheader(d["titulo"], icon=d["icone"], anchor=False)
                st.markdown(d["texto"])

# ---------- Conexões por mês ----------

with st.container(border=True):
    st.subheader("Novas conexões por mês", icon=":material/calendar_view_month:")
    medida = st.segmented_control(
        "Medida", ["Usinas", "Potência"], default="Usinas", required=True, key="medida_mensal",
        label_visibility="collapsed",
    )
    coluna_y = "quantidade" if medida == "Usinas" else "potencia_mw"
    serie = cortar_inicio(serie_mensal(filtrar(exceto="periodo"))).reset_index()
    serie["potencia_mw"] = serie["potencia_kw"] / 1000
    serie["situacao"] = serie["mes"].isin(MESES_INCOMPLETOS).map(
        {True: "Provavelmente incompleto", False: "Registrado"}
    )
    figura = px.bar(
        serie, x="mes", y=coluna_y, color="situacao",
        color_discrete_map={"Registrado": COR_DESTAQUE, "Provavelmente incompleto": COR_INCOMPLETO},
        labels={"mes": "", coluna_y: "Usinas" if medida == "Usinas" else "MW", "situacao": ""},
    )
    formato_y = "%{y:,.0f} usinas" if medida == "Usinas" else "%{y:,.1f} MW"
    figura.update_traces(hovertemplate=f"%{{x|%m/%Y}}<br><b>{formato_y}</b><extra></extra>")
    figura.add_vrect(
        x0=INICIO_SUSPENSAO.isoformat(), x1=FIM_SUSPENSAO.isoformat(),
        fillcolor="#F43F5E", opacity=0.18, line_width=0,
        annotation_text="Suspensão", annotation_position="top left",
    )
    if serie["mes"].min() <= pd.Timestamp(PRAZO_LEI_14300) <= serie["mes"].max():
        figura.add_vline(
            x=PRAZO_LEI_14300.isoformat(), line_dash="dot", line_color="gray",
            annotation_text="Prazo Lei 14.300", annotation_position="top left",
        )
    if periodo_selecionado():
        inicio, fim = periodo_selecionado()
        figura.add_vrect(
            x0=inicio - pd.Timedelta(days=15), x1=fim + pd.Timedelta(days=15),
            fillcolor=COR_DESTAQUE, opacity=0.12, line_width=1, line_color=COR_DESTAQUE,
        )
    figura.update_layout(dragmode="select", bargap=0.1)
    chave = f"grafico_mensal_{st.session_state['rodada']}"
    st.plotly_chart(
        estilizar(figura, 420), key=chave, on_select=ao_selecionar_periodo(chave),
        selection_mode=("box", "points"), alt="Barras com as novas conexões de cada mês",
    )
    st.caption(
        "Arraste sobre as barras para filtrar o período. O eixo começa quando o recorte "
        f"passa de {pct_br(FRACAO_INICIO_GRAFICO)} das usinas. A base não traz a data de conexão; "
        "usamos a data da última atualização cadastral como aproximação. Em cinza, os meses "
        f"que ficaram abaixo de {pct_br(LIMIAR_MES_INCOMPLETO, 0)} da mediana dos 12 meses anteriores."
    )

# ---------- Potência acumulada e regiões ----------

coluna_esq, coluna_dir = st.columns([3, 2])

with coluna_esq.container(border=True, height="stretch"):
    st.subheader("Potência acumulada", icon=":material/trending_up:")
    completa = serie_mensal(filtrar(exceto="periodo"))
    acumulado = completa.assign(gw=completa["potencia_kw"].cumsum() / 1_000_000)
    acumulado = cortar_inicio(acumulado).reset_index()
    figura = px.area(acumulado, x="mes", y="gw", labels={"mes": "", "gw": "GW"})
    figura.update_traces(
        line_color=COR_DESTAQUE, fillcolor="rgba(245,158,11,0.18)",
        hovertemplate="%{x|%m/%Y}<br><b>%{y:,.2f} GW</b><extra></extra>",
    )
    if periodo_selecionado():
        figura.add_vrect(x0=periodo_selecionado()[0], x1=periodo_selecionado()[1],
                         fillcolor=COR_DESTAQUE, opacity=0.12, line_width=0)
    st.plotly_chart(estilizar(figura), alt="Área com a potência acumulada ao longo dos meses")

with coluna_dir.container(border=True, height="stretch"):
    st.subheader("Por região", icon=":material/map:")
    regioes = agrupar(filtrar(exceto="regiao"), "regiao").reset_index()
    regioes["fatia"] = regioes["potencia_kw"] / regioes["potencia_kw"].sum()
    figura = px.bar(
        regioes, x="potencia_mw", y="regiao", orientation="h",
        color="regiao", color_discrete_map=CORES_REGIAO, custom_data=["regiao", "fatia"],
        labels={"potencia_mw": "Potência (MW)", "regiao": ""},
    )
    figura.update_traces(hovertemplate="<b>%{y}</b><br>%{x:,.0f} MW · %{customdata[1]:.1%}<extra></extra>")
    figura.update_layout(showlegend=False)
    esmaecer_nao_selecionados(figura, "regiao")
    grafico_clicavel(figura, "regiao", "regiao", "Barras com a potência de cada região")

# ---------- Estados e distribuidoras ----------

indicadores = {
    "Potência": ("potencia_mw", "%{x:,.1f} MW"),
    "Usinas": ("quantidade", "%{x:,.0f} usinas"),
    "Tamanho médio": ("media_kw", "%{x:,.1f} kW por usina"),
}
indicador = st.segmented_control(
    "Indicador dos rankings", list(indicadores), default="Potência", required=True, key="indicador_ranking",
)
coluna_ind, formato_ind = indicadores[indicador]

coluna_esq, coluna_dir = st.columns(2)
for coluna, dim, nome, icone, limite in (
    (coluna_esq, "uf", "Estados", ":material/leaderboard:", None),
    (coluna_dir, "distribuidora", "Distribuidoras (15 maiores)", ":material/electrical_services:", 15),
):
    with coluna.container(border=True, height="stretch"):
        st.subheader(nome, icon=icone)
        grupos = agrupar(filtrar(exceto=dim), dim).reset_index()
        grupos["media_kw"] = grupos["potencia_kw"] / grupos["quantidade"]
        if dim == "uf":
            grupos = grupos.merge(cubo[["uf", "regiao"]].drop_duplicates(), on="uf")
        grupos = grupos.sort_values(coluna_ind, ascending=False)
        if limite:
            selecionados = st.session_state[f"filtro_{dim}"]
            grupos = pd.concat([grupos.head(limite), grupos[grupos[dim].isin(selecionados)]]).drop_duplicates(dim)
        grupos["nome"] = grupos[dim].map(NOMES_DISTRIBUIDORAS) if dim == "distribuidora" else grupos[dim]
        figura = px.bar(
            grupos.sort_values(coluna_ind), x=coluna_ind, y=dim, orientation="h",
            color="regiao" if dim == "uf" else None,
            color_discrete_map=CORES_REGIAO, custom_data=[dim, "nome"],
            labels={coluna_ind: {"Potência": "MW", "Usinas": "Usinas", "Tamanho médio": "kW por usina"}[indicador],
                    dim: "", "regiao": "Região"},
        )
        if dim != "uf":
            figura.update_traces(marker_color="#3B82F6")
        figura.update_traces(hovertemplate=f"<b>%{{customdata[1]}}</b><br>{formato_ind}<extra></extra>")
        if coluna_ind == "media_kw":
            media = grupos["potencia_kw"].sum() / grupos["quantidade"].sum()
            figura.add_vline(x=media, line_dash="dot", line_color="gray", line_width=2)
        esmaecer_nao_selecionados(figura, dim)
        grafico_clicavel(figura, dim, dim, f"Barras com {indicador.lower()} por {DIMENSOES[dim][0].lower()}",
                         altura=max(380, 22 * len(grupos)))
        if coluna_ind == "media_kw":
            st.caption("A linha pontilhada marca a média do recorte.")

# ---------- Fonte, classe, porte e modalidade ----------

def grafico_categoria(coluna, dim, icone, cor):
    with coluna.container(border=True, height="stretch"):
        singular, _ = DIMENSOES[dim]
        st.subheader(singular, icon=icone)
        grupos = agrupar(filtrar(exceto=dim), dim).reset_index()
        grupos["fatia"] = grupos["potencia_kw"] / grupos["potencia_kw"].sum()
        figura = px.bar(
            grupos, x="potencia_mw", y=dim, orientation="h",
            custom_data=[dim, "fatia", "quantidade"], labels={"potencia_mw": "Potência (MW)", dim: ""},
        )
        figura.update_traces(
            marker_color=cor,
            hovertemplate="<b>%{y}</b><br>%{x:,.2f} MW (%{customdata[1]:.2%})<br>%{customdata[2]:,.0f} usinas<extra></extra>",
        )
        # Escala logarítmica quando o maior valor é mil vezes o menor: assim as
        # categorias pequenas continuam visíveis ao lado da maior.
        positivos = grupos.loc[grupos["potencia_mw"] > 0, "potencia_mw"]
        escala_log = len(positivos) > 1 and positivos.max() / positivos.min() >= 1000
        if escala_log:
            figura.update_xaxes(type="log")
        esmaecer_nao_selecionados(figura, dim)
        grafico_clicavel(figura, dim, dim, f"Barras com a potência por {singular.lower()}",
                         altura=max(260, 26 * len(grupos)))
        if escala_log:
            st.caption("Escala logarítmica: cada marca do eixo vale 10 vezes a anterior.")


coluna_esq, coluna_dir = st.columns(2)
grafico_categoria(coluna_esq, "fonte", ":material/wb_sunny:", "#14B8A6")
grafico_categoria(coluna_dir, "classe", ":material/home:", "#8B5CF6")
coluna_esq, coluna_dir = st.columns(2)
grafico_categoria(coluna_esq, "porte", ":material/straighten:", "#F43F5E")
grafico_categoria(coluna_dir, "modalidade", ":material/share:", "#3B82F6")

# ---------- Rodapé ----------

st.caption(
    f":material/info: Fonte: [ANEEL – Relação de empreendimentos de Mini e Micro Geração Distribuída]({URL_DATASET}), "
    f"dados abertos sob a licença [ODbL]({URL_LICENCA}). "
    f"Download em {data_br(metadados['data_download_utc'])}."
)
