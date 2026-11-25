"""Atualiza os dados aqui no seu computador e envia os resumos novos ao GitHub.

Use quando o GitHub Actions não conseguir acessar o servidor da ANEEL (em
16/11, 23/11 e 25/11/2026 a conexão esgotou o tempo). Faz o mesmo que o workflow:
baixar -> gerar os resumos -> conferir -> enviar, só se os resumos mudaram.

Uso:  python atualizar_local.py     (no Windows, dê dois cliques em atualizar.bat)
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

PASTA_PROJETO = Path(__file__).resolve().parent

# O que conta como "os resumos mudaram" (igual ao workflow).
RESUMOS = ["dados/processados/*.csv", "dados/processados/processamento.json"]


def rodar(comando, pasta=PASTA_PROJETO):
    """Mostra o comando na tela e roda. Se der erro, o programa para (check=True)."""
    print(f"\n> {' '.join(comando)}", flush=True)
    subprocess.run(comando, cwd=pasta, check=True)


def resumos_mudaram(pasta=PASTA_PROJETO):
    """`git diff --quiet` termina com código 0 se nada mudou e 1 se algo mudou."""
    return subprocess.run(["git", "diff", "--quiet", "--", *RESUMOS], cwd=pasta).returncode != 0


def publicar(pasta=PASTA_PROJETO, hoje=None):
    """Faz o commit dos resumos e envia ao GitHub, se algo mudou. Devolve True se enviou."""
    if not resumos_mudaram(pasta):
        print("\nA base da ANEEL não mudou. Nada a publicar.")
        return False
    hoje = hoje or datetime.now()
    rodar(["git", "add", "dados/processados/"], pasta)
    rodar(["git", "commit", "-m", f"Atualiza dados da ANEEL ({hoje:%d/%m/%Y})"], pasta)
    rodar(["git", "push"], pasta)
    print("\nPronto: resumos enviados ao GitHub.")
    return True


def main():
    # Traz o que já está no GitHub antes de começar, para não dar conflito no envio.
    rodar(["git", "pull", "--ff-only"])
    # sys.executable é o Python que está rodando este arquivo (o do .venv, pelo .bat).
    rodar([sys.executable, "baixar_dados.py"])
    rodar([sys.executable, "processar_dados.py"])
    # Se os resumos não baterem com a base bruta, para aqui e nada é enviado.
    rodar([sys.executable, "checar_dados.py"])
    publicar()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as erro:
        # Código de saída 1 avisa que algo deu errado.
        print(f"\nErro: o comando terminou com falha (código {erro.returncode}). Nada foi enviado.", file=sys.stderr)
        sys.exit(1)
