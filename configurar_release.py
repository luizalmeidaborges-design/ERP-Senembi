"""Prepara a versão digitada no GitHub Actions antes de compilar o EXE."""
import json
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Uso: python configurar_release.py usuario/repositorio 1.0.1')
    repo, version = sys.argv[1:]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise SystemExit('Repositório inválido: use usuario/repositorio.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise SystemExit('Versão inválida: use, por exemplo, 1.0.1.')
    settings = {
        'version': version,
        'manifest_url': f'https://github.com/{repo}/releases/latest/download/update.json',
    }
    path = Path(__file__).resolve().parent / 'assets' / 'update_config.json'
    path.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
    print(f'Versão {version} preparada para {repo}.')


if __name__ == '__main__':
    main()
