# 🐑 Carneiro Random Image Loader

Custom Node para ComfyUI - Seleção aleatória ou sequencial de imagens com rastreamento e cache inteligente.

## Versão: 2.1.0

## Nodes Incluídos

1. **🐑 Carneiro Random Image** - Seleciona imagem aleatória ou sequencial de uma pasta
2. **📊 Carneiro Cache Stats** - Monitora estatísticas de cache (opcional/debug)

## Instalação

Estrutura de arquivos:
```
ComfyUI/custom_nodes/ComfyUI-Carneiro/
├── __init__.py
└── random_image_loader.py
```

Após copiar os arquivos, reinicie o ComfyUI completamente.

## Inputs — Carneiro Random Image

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| `folder_path` | STRING | `""` | Caminho absoluto da pasta de imagens |
| `mode` | ENUM | `random` | `random` = aleatório, `sequential` = ordem alfabética |
| `delete_after_use` | BOOLEAN | `False` | Deleta o arquivo após ser selecionado |
| `force_rescan` | BOOLEAN | `False` | Ignora cache e rescaneia o disco |
| `include_subfolders` | BOOLEAN | `False` | Buscar recursivamente em subpastas |
| `seed` | INT | `-1` | `-1` = aleatório verdadeiro, ≥0 = reproduzível |
| `manual_image` | BOOLEAN | `False` | Ativa o carregamento manual em vez do modo aleatório |
| `image` | IMAGE | — | Imagem selecionada pelo botão `Carregar imagem do PC` ou pelo seletor do ComfyUI |

O botão `Carregar imagem do PC` envia a imagem para a pasta `input` do ComfyUI e ativa automaticamente `manual_image`.

## Outputs — Carneiro Random Image

| Nome | Tipo | Descrição |
|------|------|-----------|
| `image` | IMAGE | Tensor da imagem selecionada (BHWC, float32, RGB) |
| `image_path` | STRING | Caminho completo do arquivo selecionado |
| `filename` | STRING | Nome do arquivo |
| `total_files` | INT | Total de imagens encontradas na pasta |
| `processed_count` | INT | Quantas imagens já foram processadas nesta sessão |

## Rastreamento de Processados

O node salva um arquivo `.carneiro_img_processed.json` na pasta alvo para evitar repetir imagens entre execuções. Quando todas as imagens forem processadas, o rastreador reseta automaticamente e recomeça do início.

## Recomendação de Uso

Deixe `force_rescan: False` na maioria dos casos — o cache detecta
automaticamente mudanças na pasta (via mtime) e é ~100x mais rápido.
Use `force_rescan: True` apenas logo após adicionar/remover arquivos
e apenas na execução seguinte; depois volte para `False`.

## Formatos Suportados

`.png` `.jpg` `.jpeg` `.webp` `.bmp` `.gif` `.tiff` `.tif` `.svg` `.ico`

## Características Técnicas

- Saída `IMAGE` nativa: imagem carregada com PIL, corrigida por EXIF, convertida para tensor `BHWC float32 [0,1]`
- Rastreamento de arquivos processados via `.carneiro_img_processed.json` — evita repetição entre execuções
- Auto-reset do rastreador quando todas as imagens forem processadas
- Seed com múltiplas fontes de entropia (os.urandom + tempo em ns + id do objeto + hash do caminho + contador de execução) — garante aleatoriedade real mesmo na primeira execução de cada instância
- Cache LRU com limite de 50 entradas e TTL de 10 minutos — evita crescimento indefinido de memória
- Limpeza automática (cache expirado + garbage collection) a cada 100 execuções
- Scan de diretório em lotes de 1000 arquivos, com GC periódico — evita degradação em `force_rescan` repetido
- Limite de segurança de 50.000 arquivos por scan

## Changelog

- **v1.0**: Versão inicial com Reservoir Sampling
- **v1.1**: Corrigido bug de seed pouco aleatório na primeira execução
- **v1.2**: Adicionado cache LRU para evitar lentidão progressiva
- **v1.3**: Gestão otimizada de recursos para uso com `force_rescan=True`
- **v2.0**: Rastreamento de processados, modo sequencial e auto-delete
- **v2.1**: Output `IMAGE` nativo — tensor da imagem disponível diretamente no node
- **v2.2**: Adicionado carregamento manual opcional de imagem
