# ERP Senembi T-Labs

Aplicativo Windows local para filamentos, materiais eletrônicos, produtos, pedidos e projetos. Interface em português, banco SQLite em `%LOCALAPPDATA%\Senembi\ERP\senembi.db`. O arquivo de dados fica fora do executável e não é alterado pela atualização.

## Executar

Com Python 3.12 instalado, execute `python app.py`. No Windows, `build_windows.bat` instala PyInstaller, executa os testes e compila `dist\ERP_Senembi.exe`. O ícone de camaleão enviado para o projeto aparece na janela e no executável. O [workflow do GitHub Actions](https://github.com/luizalmeidaborges-design/ERP-Senembi/actions/workflows/windows-release.yml) funciona como o do Papéis de Marte: em **Actions → Compilar e publicar ERP Senembi → Run workflow**, o formulário pede o **número da versão** (por exemplo, `1.0.1`); também é possível publicar alterando somente `release-version.txt` na branch `main`. O workflow configura a versão interna do EXE, cria o manifesto com SHA-256 e publica a tag e os arquivos no release. Alterações nos demais arquivos não disparam a compilação. Para compilação local com `build_windows.bat`, a versão está em `assets/update_config.json` (atualmente `1.0.1`). Ao abrir uma versão anterior, o aplicativo executa a versão nova previamente verificada.

**Correção do atualizador:** a versão 1.1.0 rejeita o endereço do manifesto antes de tentar baixar uma atualização. Após publicar a versão corrigida, computadores com 1.1.0 ou anterior precisam baixar e abrir o novo EXE manualmente uma vez. As atualizações posteriores poderão usar o atualizador automático. Use uma nova versão (por exemplo, `1.1.1`) no próximo **Run workflow**; o workflow substituirá a versão do arquivo de configuração durante a compilação.

## Campos e fórmulas

- Filamento: `MATERIAL-DES-00001`, usando as três primeiras letras da descrição (por exemplo, `PLA-LAR-00002`). Ao abrir a nova versão, os códigos antigos são convertidos automaticamente, mantendo seus números e as referências nos produtos. O cadastro contém material, descrição, peso útil do carretel em gramas, valor total, densidade e fornecedor. A densidade é informação de catálogo; o orçamento utiliza o **peso informado pelo fatiador**.
- Componente: `ELE-00001`, nome, descrição, unidades do pacote, preço do pacote, fornecedor e link de datasheet. Custo unitário = preço do pacote / quantidade.
- Impresso: escolhe filamentos possíveis e usa o **maior preço por grama**, multiplicado pelo peso da peça. Energia = potência média em watts × horas de impressão / 1000 × tarifa por kWh. Horas de modelagem podem ser adicionadas.
- Eletrônico: soma quantidade × custo unitário de cada componente e horas de preparo × valor da hora técnica.
- Mecatrônico: soma os custos dos produtos impressos e eletrônicos escolhidos e horas de integração. Um conjunto representa uma unidade de cada produto escolhido.
- Preço sugerido de qualquer produto = custo × (1 + percentual de lucro / 100). É um acréscimo sobre o custo, não margem líquida contábil. Impostos, frete e taxas devem ser incluídos pelo usuário em um orçamento externo, caso aplicáveis.
- Pedido: `OP-00001`, cliente, itens e quantidades, prazo, valor sugerido, ajuste manual, status e pagamento. O preço de cada item é congelado na criação do pedido.
- Projeto: escopo, objetivo, restrições, qualidade/aceitação, riscos, prazo e orçamento por horas + materiais. Cria uma subtarefa inicial; o Kanban possui as colunas A fazer, Em andamento e Concluído.
- Calendário reúne entrega de pedidos e prazos das subtarefas; Pendências lista por prazo os eventos abertos.

Os preços por hora são **exemplos editáveis**, sem caráter de tabela oficial: a página Informações adicionais permite alterar cada especialidade, tarifa de energia, potência da impressora, lucro e valores gerais. Orçamentos existentes guardam os valores calculados no cadastro; para aplicar novos parâmetros, edite e salve cada produto/projeto.

## Backup

Uma cópia SQLite consistente é criada na pasta `backups` dos dados locais ao fechar e periodicamente enquanto o app está aberto. O botão no cabeçalho escolhe uma segunda pasta, inclusive uma pasta sincronizada por OneDrive ou Google Drive. Se a pasta selecionada estiver indisponível, a cópia local permanece. Ao fechar, uma janela sinaliza o backup até terminar.

## Referências dos valores iniciais

A calculadora de consumo segue [Adriano Aoli](https://adrianoaoli.com/eletronica/calculadora-consumo-eletrico.html). Os exemplos de hora são estimativas orientativas com base em [perfis brasileiros de modelagem 3D na Workana](https://www.workana.com/pt/freelancers/brasil/modelacao-3d) e em [orientação de precificação do Sebrae](https://rs.loja.sebrae.com.br/como-definir-preco-de-venda); especialidades de eletrônica e TI foram diferenciadas por complexidade como **estimativas do projeto**, não como uma pesquisa de preços específica para cada categoria.
